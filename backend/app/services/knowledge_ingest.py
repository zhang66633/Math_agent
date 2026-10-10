"""知识库上传提取流水线 — LLM 提取 → 校验 → 写 YAML → 增量索引。

从 api/knowledge_search_routes.py 拆出：该路由文件曾把 440 行提取流水线
（含 4 个提取 prompt）塞在路由之间。job store（内存态，重启清空）也一并
收敛到本模块，路由只经 new_job/get_job 访问。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..config import get_settings
from ..knowledge.kb_files import _find_yaml_file, _get_embedder, _get_loader, _next_id
from .document_parsers import build_multimodal_message

# ── job store（内存态；进程重启即清空，进行中的 job 以前端轮询 404 收场）──

_extraction_jobs: dict[str, dict] = {}


def new_job(
    job_id: str, status: str, result: dict | None = None, error: str | None = None
) -> str:
    """登记/更新一个提取 job（status: processing | completed | error）。"""
    _extraction_jobs[job_id] = {"status": status, "result": result, "error": error}
    return job_id


def get_job(job_id: str) -> dict | None:
    """查询 job 状态；不存在返回 None（路由层转 404）。"""
    return _extraction_jobs.get(job_id)


def _unique_output_path(out_dir: Path, safe_name: str, entry_id: str) -> Path:
    """输出路径去重：同名文件已存在时追加 entry_id，避免同题多篇互相覆盖。

    2026-10 教训：批量导入同一赛题的多篇优秀论文时，各篇的输出文件名
    完全相同（如 2023研赛B.yaml），后导入的静默覆盖先导入的——导了三篇
    只剩一篇，且 job 状态全是 completed，无从察觉。追加 entry_id 后每篇
    独立落盘；重复导入同一来源时仍会更新同一文件（幂等）。
    """
    candidate = out_dir / f"{safe_name}.yaml"
    if not candidate.exists():
        return candidate
    return out_dir / f"{safe_name}_{entry_id}.yaml"


async def run_extraction(
    job_id: str,
    raw_text: str,
    text_parts: list[str],
    raw_images: list[str],
    raw_file_data: list[dict],
    kb_type: str,
    name_hint: str,
    problem_ref: str = "",
    user_login: str = "",
):
    """Background task: LLM extract → validate → write YAML → index.

    Accepts multiple file types assembled into a rich multimodal message:
      - raw_text:      user-written problem description
      - text_parts:    Excel/CSV/DOCX summaries, one per file
      - raw_images:    base64 images (standalone PNG/JPG/GIF + PDF pages)
      - raw_file_data: attachment metadata for persistence
    """
    try:
        settings = get_settings()
        from ..core.llm.factory import LLMFactory
        from ..knowledge.schemas import MethodCard, Paper, Problem, Template

        # 1. LLM extraction
        # 配置了 KB_VISION_MODEL 时用独立视觉模型(只用 .env key,不受活动 API Key 覆盖,
        # 避免被 DeepSeek key 覆盖回纯文本模型);否则走 analysis 角色(默认 deepseek-v4-flash)
        vision_model = settings.kb_vision_model.strip()
        vision_provider = ""
        if vision_model and raw_images:
            from ..core.llm.providers import classify_provider, get_provider

            vision_provider = classify_provider(vision_model)
            api_key = (
                settings.anthropic_api_key
                if vision_provider == "anthropic"
                else settings.openai_api_key
            )
            llm = get_provider(vision_model).create(
                model=vision_model,
                api_key=api_key,
                temperature=settings.default_temperature,
                max_tokens=settings.default_max_tokens,
                base_url=(
                    getattr(settings, "deepseek_base_url", None)
                    if "deepseek" in vision_model.lower()
                    else None
                ),
            )
        else:
            llm = LLMFactory().create("analysis")
            vision_model = ""

        prompt_map = {
            "method": _EXTRACT_METHOD_PROMPT,
            "paper": _EXTRACT_PAPER_PROMPT,
            "template": _EXTRACT_TEMPLATE_PROMPT,
            "problem": _EXTRACT_PROBLEM_PROMPT,
        }
        schema_map = {
            "method": MethodCard,
            "paper": Paper,
            "template": Template,
            "problem": Problem,
        }

        # Assemble full context: problem text + data summaries
        full_text = raw_text
        if text_parts:
            full_text += "\n\n--- 附件资料 ---\n\n" + "\n\n".join(text_parts)

        prompt = prompt_map[kb_type].format(raw_text=full_text)
        if kb_type == "paper" and not raw_images:
            # paper prompt 默认写死「你将看到每一页扫描图片」,纯文本路径需说明
            prompt += "\n\n注意: 本次输入不包含页面图片(未配置视觉模型或非 PDF),请仅依据文本内容提取。"

        # Multimodal if images available (PDF pages, standalone images, GIFs)
        msg = build_multimodal_message(prompt, raw_images, provider=vision_provider or "openai")
        try:
            response = llm.invoke([msg])
        except Exception as e:
            err_text = str(e)
            # 模型不支持 image_url 的典型报错 → 换成可操作的提示,不抛原始 400 JSON
            if "image_url" in err_text or "unknown variant" in err_text:
                _extraction_jobs[job_id] = {
                    "status": "error",
                    "result": None,
                    "error": (
                        f"模型 {vision_model or 'analysis'} 不支持图片输入。"
                        "请在 backend/.env 配置 KB_VISION_MODEL 为支持视觉的模型"
                        "(如 qwen-vl-plus、gpt-4o),或移除图片附件后重试。"
                    ),
                }
                return
            raise
        extracted = parse_llm_json(str(response.content))

        if not extracted:
            _extraction_jobs[job_id] = {
                "status": "error",
                "result": None,
                "error": "LLM 未能提取出有效内容，请检查输入文本",
            }
            return

        # 2. Generate ID and validate
        entry_id = _next_id(kb_type)
        schema_cls = schema_map[kb_type]
        extracted["id"] = entry_id
        try:
            validated = schema_cls(**extracted)
        except Exception as ve:
            _extraction_jobs[job_id] = {
                "status": "error",
                "result": None,
                "error": f"LLM 提取的内容格式有误: {ve}",
            }
            return

        # 2b. Link paper to problem
        if kb_type == "paper":
            target_problem_id = problem_ref  # 优先使用前端指定的关联
            if not target_problem_id:
                # 自动匹配：根据 year + competition + problem_id 查找
                year = extracted.get("year")
                competition = extracted.get("competition")
                pid = extracted.get("problem_id")
                if year and competition and pid:
                    loader = _get_loader()
                    matched = loader.get_problem_by_key(year, competition, pid)
                    if matched:
                        target_problem_id = matched.id

            if target_problem_id:
                validated.problem_ref = target_problem_id
                # 更新题目的 linked_papers
                prob_yf = _find_yaml_file("problem", target_problem_id)
                if prob_yf:
                    import yaml as _yaml

                    prob_data = _yaml.safe_load(prob_yf.read_text(encoding="utf-8"))
                    if prob_data and "problem" in prob_data:
                        linked = prob_data["problem"].get("linked_papers", [])
                        if validated.id not in linked:
                            linked.append(validated.id)
                            prob_data["problem"]["linked_papers"] = linked
                            prob_yf.write_text(
                                yaml.dump(
                                    prob_data,
                                    allow_unicode=True,
                                    default_flow_style=False,
                                    sort_keys=False,
                                    indent=2,
                                ),
                                encoding="utf-8",
                            )

        # 3. Build YAML and write file
        top_key_map = {
            "method": "method_card",
            "paper": "paper",
            "template": "template",
            "problem": "problem",
        }
        top_key = top_key_map[kb_type]
        yaml_str = yaml.dump(
            {top_key: validated.model_dump() if hasattr(validated, "model_dump") else extracted},
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
        )

        # Determine output path
        subdir_map = {
            "method": "methods",
            "paper": "papers",
            "template": "templates",
            "problem": "problems",
        }
        subdir = subdir_map[kb_type]
        if kb_type == "method":
            cat = (extracted.get("category") or ["other"])[0]
            safe_name = (extracted.get("name") or name_hint or entry_id).replace(" ", "_")
            out_dir = settings.kb_root / subdir / cat
        elif kb_type == "paper":
            competition = extracted.get("competition", "other")
            year = extracted.get("year", 2025)
            pid = extracted.get("problem_id", "X")
            safe_name = f"{year}{competition}{pid}"
            out_dir = settings.kb_root / subdir / competition
        elif kb_type == "problem":
            competition = extracted.get("competition", "other")
            year = extracted.get("year", 2025)
            pid = extracted.get("problem_id", "X")
            safe_name = f"{year}{pid}"
            out_dir = settings.kb_root / subdir / competition
        else:
            safe_name = (extracted.get("name") or name_hint or entry_id).replace(" ", "_")
            out_dir = settings.kb_root / subdir

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = _unique_output_path(out_dir, safe_name, entry_id)
        out_path.write_text(yaml_str, encoding="utf-8")

        # Save raw text alongside the YAML for dual-view
        raw_path = out_path.with_suffix(".raw.txt")
        raw_path.write_text(raw_text, encoding="utf-8")

        # Save attachment files in _attachments/ subdirectory
        if raw_file_data:
            attach_dir = out_path.parent / f"{out_path.stem}_attachments"
            attach_dir.mkdir(parents=True, exist_ok=True)
            for fd in raw_file_data:
                attach_path = attach_dir / (fd["name"] or "attachment")
                attach_path.write_bytes(fd["bytes"])

        # 4. Incremental index(无 embedding key 或索引失败时降级关键词检索,YAML 已落盘不受影响)
        embedder = _get_embedder(user_login)
        index_warning = ""
        if embedder.embeddings is None:
            from ..knowledge.retriever import invalidate_shared_retriever

            # 让共享检索器/loader 缓存失效,关键词检索能立刻看到新条目
            invalidate_shared_retriever()
            indexed = "keyword-only"
        else:
            try:
                embedder.add_document(out_path)
                indexed = "vector"
            except Exception as e:
                # 索引失败(典型:embedding 配额耗尽 403)不否定提取成果——YAML 已落盘,
                # loader/关键词检索立即可见;向量索引待配额恢复后 rebuild 即可。
                # 2026-10 教训:此前此处异常直接把 job 判 error,用户看到「导入失败」,
                # 但数据其实已进知识库,重试还会产生重复条目(本次实测踩中)。
                from ..knowledge.retriever import invalidate_shared_retriever

                invalidate_shared_retriever()
                indexed = "keyword-only"
                index_warning = f"向量索引失败({str(e)[:80]});条目已落盘,可关键词检索,配额恢复后重建索引即可"

        _extraction_jobs[job_id] = {
            "status": "completed",
            "result": {
                "entry_id": entry_id,
                "entry_type": kb_type,
                "file_path": str(out_path.relative_to(settings.project_root)),
                "yaml_content": yaml_str,
                "indexed": indexed,
                "warning": index_warning,
            },
            "error": None,
        }
    except Exception as e:
        _extraction_jobs[job_id] = {
            "status": "error",
            "result": None,
            "error": str(e),
        }


# ── extraction prompts ──────────────────────────────────────────

_EXTRACT_METHOD_PROMPT = """你是一个数学建模知识工程师。请从以下文本中提取方法卡片的结构化信息。

文本内容:
```
{raw_text}
```

请返回严格的 JSON 格式（不要有任何额外文本），结构如下:
{{
  "name": "方法名称",
  "category": ["分类1", "分类2"],
  "principle": "核心原理的详细描述",
  "formulas": [{{"name": "公式名", "latex": "LaTeX表达式", "description": "含义"}}],
  "applicable_when": ["适用条件1"],
  "not_applicable_when": ["不适用条件1"],
  "typical_scenarios": ["典型场景1"],
  "common_mistakes": [{{"mistake": "常见错误", "solution": "正确做法"}}],
  "code_snippets": [{{"language": "python", "description": "功能", "code": "代码内容"}}],
  "related_cards": [],
  "related_papers": []
}}

如果文本中没有某项信息，使用空数组 [] 代替。只返回 JSON。"""

_EXTRACT_PAPER_PROMPT = """你是一个数学建模竞赛论文深度分析专家。你的任务不是简单摘要，而是以建模教学者的视角，
将这篇论文拆解为可复用的结构化知识。每一个字段都要为后续读者提供真正有用的指导。

你将看到论文的每一页扫描图片（以及可选的 OCR 文本参考）。请逐页仔细阅读所有内容：

视觉解读要求:
- **数学公式**: 识别并转换为标准 LaTeX 格式
- **图表**: 理解图表展示的趋势和结论,在 problem_context 和 approach 中描述
- **表格数据**: 提取关键数值和结构
- **代码**: 完整保留代码片段
- **图片中的文字**: 一并提取

以下是 OCR 提取的文本参考（可能不完整或有错误，以图片为准）:
```
{raw_text}
```

请返回严格的 JSON 格式（不要有任何额外文本），按照以下结构:

{{
  "year": 年份数字,
  "competition": "国赛/美赛/研赛",
  "problem_id": "题号A/B/C/D/E",
  "title": "论文标题",

  "tags": {{
    "problem_type": ["优化", "预测", "评价", "分类", "综合"],
    "core_models": ["使用的核心模型名称"],
    "techniques": ["使用的技术/工具"]
  }},

  "problem_context": "问题背景的详细复述（300-800字）。要写清楚：实际场景是什么、为什么要解决这个问题、输入数据是什么、期望输出是什么。让没有看过原题的人也能完全理解。",

  "methodology_chain": ["步骤1: 简述", "步骤2: 简述", "..."],
  "说明": "methodology_chain 是按时间顺序排列的建模全流程，每一步用一句话概括做了什么。例如: ['数据预处理: 对缺失值用均值填充，异常值用3σ准则剔除', '特征工程: 构建滞后特征和滑动窗口统计量', '时序预测: 使用ARIMA(2,1,2)对各品类分别建模', '优化决策: 建立多目标规划模型，以预测销量为输入，求解最优定价']",

  "key_formulas": [
    {{
      "name": "公式名称（如: ARIMA模型表达式）",
      "latex": "完整的LaTeX公式",
      "description": "公式在论文中的作用和含义"
    }}
  ],

  "algorithm_outline": [
    {{
      "language": "python 或 pseudocode",
      "description": "算法用途",
      "code": "算法的伪代码或关键步骤（用Python风格伪代码）"
    }}
  ],

  "assumption_analysis": [
    "假设1: 原文怎么说的 → 这条假设合理吗？如果放松会怎样？",
    "假设2: ..."
  ],

  "reusable_patterns": [
    "可复用的模式1: 描述一种可以迁移到其他问题的方法组合或分析思路",
    "可复用的模式2: ..."
  ],

  "common_pitfalls": [
    {{
      "mistake": "模仿这篇论文时容易犯的错误",
      "solution": "如何避免或纠正"
    }}
  ],

  "difficulty_level": "easy / medium / hard",

  "analysis": {{
    "problem_summary": "问题本质的一句话概括",
    "key_assumptions": ["假设1", "假设2"],
    "decision_variables": "决策变量的符号和含义",
    "objective": "目标函数的文字描述",
    "constraints": "主要约束条件的文字描述"
  }},

  "model": {{
    "approach": "整体建模思路的概述（200-400字）",
    "innovation": "这篇论文最突出的创新点是什么",
    "solution_method": "具体用什么方法/软件/库求解的"
  }},

  "evaluation": {{
    "strengths": ["这篇论文做得好的地方"],
    "weaknesses": ["可以改进的地方"],
    "lessons": "读者从这篇论文中能学到的最重要的东西（100-200字）"
  }},

  "source": "论文来源（如有）",
  "quality_rating": 3,
  "problem_ref": "如果这篇论文解答的题目已经导入到知识库中（可通过年份+赛事+题号匹配），填写对应的 prob_ 编号（如 prob_001），否则留空字符串"
}}

重要提醒:
- 每个字段都要认真填写，不要留空。如果原文没有明确提到某项，基于你的数学建模知识合理推断并标注"(推断)"。
- methodology_chain 是最关键的字段，它展示了完整的建模思路链路，要让读者一目了然。
- reusable_patterns 要提炼出高于具体问题的、可以迁移的方法论。
- problem_ref 会自动匹配: 系统会根据 year+competition+problem_id 找到对应题目，LLM 也可以直接填写确认。
- 只返回 JSON，不要有任何其他文字。"""

_EXTRACT_PROBLEM_PROMPT = r"""你是一个数学建模竞赛题目提取专家。请从以下文本中提取竞赛真题的结构化信息。

文本内容:
```
{raw_text}
```

请返回严格的 JSON 格式（不要有任何额外文本），结构如下:
{{
  "year": 年份数字（如 2023）,
  "competition": "国赛" 或 "美赛" 或 "研赛",
  "problem_id": "题号（A/B/C/D/E 等单个字母）",
  "title": "题目名称",
  "full_text": "完整题目原文，尽量保留原文内容，不超过5000字",
  "background": "问题背景的简要概述（100-200字）",
  "objectives": ["求解目标1", "求解目标2"],
  "data_description": "题目附带的数据说明（如有）",
  "deliverables": ["需要提交的内容1", "需要提交的内容2"],
  "tags": {{
    "problem_type": ["从以下选择: optimization/prediction/evaluation/statistics/classification/clustering/综合"],
    "difficulty": "easy/medium/hard"
  }},
  "source_url": ""
}}

重要提醒:
- year 必须是整数，直接从题目头部年份提取
- competition 从题目来源判断：全国大学生数学建模竞赛→国赛，美国大学生数学建模竞赛→美赛
- problem_id 是单个大写字母
- 如果文本中没有明确某项信息，使用空字符串 "" 或空数组 []
- 只返回 JSON，不要有任何其他文字。"""

_EXTRACT_TEMPLATE_PROMPT = """你是一个数学建模教学专家。请从以下文本中提取问题分析框架模板。

文本内容:
```
{raw_text}
```

请返回严格的 JSON 格式:
{{
  "name": "框架名称",
  "applicable_to": ["适用类型1"],
  "steps": [{{"step": 1, "name": "步骤名", "guiding_questions": ["问题1"], "decision_tree": ["若A则X"], "checklist": ["检查项1"]}}]
}}

只返回 JSON。"""


def parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response (handles markdown fences)."""
    import json

    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            text = obj_match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
