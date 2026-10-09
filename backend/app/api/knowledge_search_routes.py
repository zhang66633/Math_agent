"""知识库检索/上传/任务路由（god-files 拆分 #31：从 knowledge_routes.py 拆出）。"""

"""Knowledge base management API — browse, search, reindex, upload, and CRUD."""

import re
import uuid
from pathlib import Path

import yaml
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel

from ..auth.dependencies import require_contributor
from ..auth.schemas import GitHubUser
from ..config import get_settings
from ..services.document_parsers import (
    build_multimodal_message,
    extract_docx_text,
    extract_pdf_text,
    parse_csv,
    parse_excel,
    pdf_to_images,
)
from .knowledge_shared import *  # noqa: F403
from .knowledge_shared import (  # noqa: F401
    _extraction_jobs,
    _find_yaml_file,
    _get_embedder,
    _get_loader,
    _get_retriever,
    _next_id,
)

knowledge_router = APIRouter()


@knowledge_router.get("/stats", response_model=KBStats)
async def kb_stats():
    """Get KB statistics: counts per layer."""
    loader = _get_loader()
    methods = len(loader.load_all_methods())
    papers = len(loader.load_all_papers())
    templates = len(loader.load_all_templates())
    problems = len(loader.load_all_problems())
    return KBStats(
        methods_count=methods,
        papers_count=papers,
        templates_count=templates,
        problems_count=problems,
        total=methods + papers + templates + problems,
    )


# ── search ──────────────────────────────────────────────────────────────


@knowledge_router.get("/search", response_model=SearchResponse)
async def kb_search(
    q: str = Query(..., description="Search query string"),
    type: str | None = Query(
        None, description="Filter by doc type: method_card / paper / template"
    ),
    problem_type: str | None = Query(None, description="Filter by problem type tag"),
    k: int = Query(5, ge=1, le=20, description="Number of results"),
):
    """Semantic + tag-based hybrid search over the knowledge base."""
    try:
        retriever = _get_retriever()
        metadata_filter = {"type": type} if type else None
        # 结果缓存：该路径单次查询约 3 次额外 LLM 调用（expansion + HyDE + rerank），
        # 重复查询命中缓存直接跳过整条检索链；内容变更时 invalidate_shared_retriever
        # 会清空缓存，不会返回陈旧结果。
        from ..knowledge.search_cache import get_cached_docs, set_cached_docs

        cache_key = (q, type or "", problem_type or "", k)
        docs = get_cached_docs(cache_key)
        if docs is None:
            # /search 为交互式高精度路径：显式开启 query expansion 与 LLM rerank
            # （低延迟路径如 pipeline/RAG chat 走 retriever 默认的保守配置，二者解耦）。
            docs = retriever._get_relevant_documents(
                q,
                metadata_filter=metadata_filter,
                problem_type=problem_type,
                k=k,
                use_query_expansion=True,
                use_reranker=True,
            )
            set_cached_docs(cache_key, docs)

        results = []
        for doc in docs:
            meta = doc.metadata
            results.append(
                SearchResult(
                    id=meta.get("id", ""),
                    type=meta.get("type", "unknown"),
                    name=meta.get("name", ""),
                    title=meta.get("title", ""),
                    snippet=doc.page_content[:300] + ("..." if len(doc.page_content) > 300 else ""),
                    score=meta.get("score"),
                )
            )

        return SearchResponse(query=q, total=len(results), results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


# ── methods ─────────────────────────────────────────────────────────────


@knowledge_router.get("/methods", response_model=list[MethodCardSummary])
async def list_methods(
    category: str | None = Query(None, description="Filter by category tag"),
):
    """List all method cards, optionally filtered by category."""
    loader = _get_loader()
    if category:
        cards = loader.get_methods_by_category(category)
    else:
        cards = loader.load_all_methods()
    return [MethodCardSummary(**c.model_dump()) for c in cards]


@knowledge_router.get("/methods/{card_id}", response_model=MethodCardDetail)
async def get_method(card_id: str):
    """Get a single method card by ID."""
    loader = _get_loader()
    card = loader.get_method_by_id(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"方法卡片 {card_id} 不存在")
    return MethodCardDetail(**card.model_dump())


# ── papers ──────────────────────────────────────────────────────────────


@knowledge_router.get("/papers", response_model=list[PaperSummary])
async def list_papers(
    problem_type: str | None = Query(None, description="Filter by problem type tag"),
    competition: str | None = Query(None, description="Filter: 国赛/美赛/研赛"),
    year: int | None = Query(None, description="Filter by competition year"),
):
    """List all papers with optional filters."""
    loader = _get_loader()
    papers = loader.load_all_papers()

    if problem_type:
        papers = [p for p in papers if problem_type in p.tags.get("problem_type", [])]
    if competition:
        papers = [p for p in papers if p.competition == competition]
    if year:
        papers = [p for p in papers if p.year == year]

    return [PaperSummary(**p.model_dump()) for p in papers]


@knowledge_router.get("/papers/{paper_id}", response_model=PaperDetail)
async def get_paper(paper_id: str):
    """Get a single paper by ID."""
    loader = _get_loader()
    for paper in loader.load_all_papers():
        if paper.id == paper_id:
            return PaperDetail(**paper.model_dump())
    raise HTTPException(status_code=404, detail=f"论文 {paper_id} 不存在")


# ── templates ───────────────────────────────────────────────────────────


@knowledge_router.get("/templates", response_model=list[TemplateSummary])
async def list_templates(
    problem_type: str | None = Query(None, description="Filter by applicable problem type"),
):
    """List all templates, optionally filtered by problem type."""
    loader = _get_loader()
    if problem_type:
        templates = loader.get_templates_for_type(problem_type)
    else:
        templates = loader.load_all_templates()
    return [
        TemplateSummary(
            id=t.id,
            name=t.name,
            applicable_to=t.applicable_to,
            steps_count=len(t.steps),
        )
        for t in templates
    ]


@knowledge_router.get("/templates/{tpl_id}", response_model=TemplateDetail)
async def get_template(tpl_id: str):
    """Get a single template by ID with full steps."""
    loader = _get_loader()
    tpl = loader.get_template_by_id(tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"模板 {tpl_id} 不存在")
    return TemplateDetail(**tpl.model_dump())


# ── raw text (original material dual-view) ──────────────────────


class RawTextResponse(BaseModel):
    entry_id: str
    raw_text: str = ""


@knowledge_router.get("/methods/{card_id}/raw", response_model=RawTextResponse)
async def get_method_raw(card_id: str):
    """获取方法卡片的原始导入文本。"""
    yf = _find_yaml_file("method", card_id)
    if not yf:
        raise HTTPException(status_code=404, detail=f"方法卡片 {card_id} 不存在")
    raw_path = yf.with_suffix(".raw.txt")
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="该条目没有原始文本（可能不是通过导入创建的）")
    return RawTextResponse(entry_id=card_id, raw_text=raw_path.read_text(encoding="utf-8"))


@knowledge_router.get("/papers/{paper_id}/raw", response_model=RawTextResponse)
async def get_paper_raw(paper_id: str):
    """获取论文的原始导入文本。"""
    yf = _find_yaml_file("paper", paper_id)
    if not yf:
        raise HTTPException(status_code=404, detail=f"论文 {paper_id} 不存在")
    raw_path = yf.with_suffix(".raw.txt")
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="该条目没有原始文本（可能不是通过导入创建的）")
    return RawTextResponse(entry_id=paper_id, raw_text=raw_path.read_text(encoding="utf-8"))


@knowledge_router.get("/templates/{tpl_id}/raw", response_model=RawTextResponse)
async def get_template_raw(tpl_id: str):
    """获取模板的原始导入文本。"""
    yf = _find_yaml_file("template", tpl_id)
    if not yf:
        raise HTTPException(status_code=404, detail=f"模板 {tpl_id} 不存在")
    raw_path = yf.with_suffix(".raw.txt")
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="该条目没有原始文本（可能不是通过导入创建的）")
    return RawTextResponse(entry_id=tpl_id, raw_text=raw_path.read_text(encoding="utf-8"))


# ── problems ───────────────────────────────────────────────────────────


@knowledge_router.get("/problems", response_model=list[ProblemSummary])
async def list_problems(
    competition: str | None = Query(None, description="Filter: 国赛/美赛/研赛"),
    year: int | None = Query(None, description="Filter by competition year"),
    problem_type: str | None = Query(None, description="Filter by problem type tag"),
):
    """List all problems with optional filters."""
    loader = _get_loader()
    problems = loader.load_all_problems()

    if competition:
        problems = [p for p in problems if p.competition == competition]
    if year:
        problems = [p for p in problems if p.year == year]
    if problem_type:
        problems = [p for p in problems if problem_type in p.tags.get("problem_type", [])]

    return [
        ProblemSummary(
            id=p.id,
            year=p.year,
            competition=p.competition,
            problem_id=p.problem_id,
            title=p.title,
            tags=p.tags,
            linked_papers_count=len(p.linked_papers),
        )
        for p in problems
    ]


@knowledge_router.get("/problems/{problem_id}", response_model=ProblemDetail)
async def get_problem(problem_id: str):
    """Get a single problem by ID."""
    loader = _get_loader()
    prob = loader.get_problem_by_id(problem_id)
    if not prob:
        raise HTTPException(status_code=404, detail=f"题目 {problem_id} 不存在")
    return ProblemDetail(**prob.model_dump())


@knowledge_router.get("/problems/{problem_id}/papers", response_model=list[PaperSummary])
async def get_problem_papers(problem_id: str):
    """Get all papers linked to a specific problem."""
    loader = _get_loader()
    prob = loader.get_problem_by_id(problem_id)
    if not prob:
        raise HTTPException(status_code=404, detail=f"题目 {problem_id} 不存在")
    papers = loader.get_papers_by_problem(problem_id)
    return [PaperSummary(**p.model_dump()) for p in papers]


@knowledge_router.get("/problems/{problem_id}/raw", response_model=RawTextResponse)
async def get_problem_raw(problem_id: str):
    """获取题目的原始导入文本。"""
    yf = _find_yaml_file("problem", problem_id)
    if not yf:
        raise HTTPException(status_code=404, detail=f"题目 {problem_id} 不存在")
    raw_path = yf.with_suffix(".raw.txt")
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="该条目没有原始文本（可能不是通过导入创建的）")
    return RawTextResponse(entry_id=problem_id, raw_text=raw_path.read_text(encoding="utf-8"))


# ── reindex (enhanced with incremental) ───────────────────────────


@knowledge_router.post("/reindex", response_model=ReindexResponse)
async def kb_reindex(
    incremental: bool = Query(False, description="Incremental mode: only changed files"),
    user: GitHubUser = Depends(require_contributor),
):
    """Trigger a rebuild of the ChromaDB vector index from YAML files."""
    try:
        settings = get_settings()
        from ..knowledge.embedder import KBEmbedder

        embedder = KBEmbedder(
            kb_root=settings.kb_root,
            persist_dir=settings.chroma_dir,
            user_id=user.login or None,
        )
        count = embedder.build_index(incremental=incremental)
        # 索引重建后失效共享 retriever + loader 缓存，避免下一次检索命中旧 Chroma 集合
        from ..knowledge.retriever import invalidate_shared_retriever

        invalidate_shared_retriever()
        mode = "增量" if incremental else "全量"
        return ReindexResponse(
            success=True,
            indexed_count=count,
            message=f"{mode}索引完成，共 {count} 篇文档",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重建索引失败: {str(e)}")


# ── upload + LLM extraction ──────────────────────────────────────


@knowledge_router.post("/upload")
async def upload_knowledge(
    background_tasks: BackgroundTasks,
    text: str = Form("", description="题目描述/论文文本"),
    files: list[UploadFile] = File(
        [], description="附件文件（Excel/CSV/图片/PDF/DOCX/TXT等，可多选）"
    ),
    kb_type: str = Form(..., description="method / paper / template / problem"),
    name: str = Form("", description="名称提示"),
    problem_ref: str = Form("", description="上传论文时指定关联的题目 ID，跳过自动匹配"),
    user: GitHubUser = Depends(require_contributor),
):
    """上传题目/论文文本及附件，LLM 自动提取结构化知识。

    支持多文件上传：Excel 数据表格、CSV、图片 (.png/.jpg/.gif)、PDF、DOCX 等。
    每种文件类型有对应的解析策略，最终汇总为一条多模态消息送给 LLM。
    返回 job_id，前端轮询 GET /knowledge/jobs/{job_id} 获取结果。
    """
    if kb_type not in ("method", "paper", "template", "problem"):
        raise HTTPException(
            status_code=400, detail="kb_type 必须为 method / paper / template / problem"
        )

    raw_text = text.strip()
    text_parts: list[str] = []  # 各文件解析后的文本片段
    raw_images: list[str] = []  # base64 图片 (PNG/JPG/GIF/PDF页)
    raw_file_data: list[dict] = []  # 附件元数据（文件名+内容）用于持久化
    # 视觉模型配置(可选): 不填则图片/扫描 PDF 降级为纯文本路径
    vision_model = get_settings().kb_vision_model.strip()
    has_image_files = False

    for f in files:
        try:
            content = await f.read()
            filename = (f.filename or "").lower()
            ext = Path(filename).suffix

            if not name and f.filename:
                name = Path(f.filename).stem

            if ext in (".xlsx", ".xls"):
                summary = parse_excel(content, f.filename or "")
                text_parts.append(summary)
                raw_file_data.append({"name": f.filename, "bytes": content})

            elif ext == ".csv":
                summary = parse_csv(content, f.filename or "")
                text_parts.append(summary)
                raw_file_data.append({"name": f.filename, "bytes": content})

            elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
                has_image_files = True
                raw_file_data.append({"name": f.filename, "bytes": content})
                if vision_model:
                    import base64

                    mime_map = {
                        ".png": "png",
                        ".jpg": "jpeg",
                        ".jpeg": "jpeg",
                        ".gif": "gif",
                        ".webp": "webp",
                        ".bmp": "bmp",
                    }
                    mime = mime_map.get(ext, "png")
                    img_b64 = base64.b64encode(content).decode()
                    raw_images.append(f"data:image/{mime};base64,{img_b64}")
                    text_parts.append(f"[图片附件] {f.filename}: 内容见视觉分析")
                else:
                    # 未配置视觉模型(默认模型不支持 image_url),跳过图片
                    text_parts.append(
                        f"[图片附件] {f.filename}: 已跳过(未配置 KB_VISION_MODEL,模型不支持读图)"
                    )

            elif ext == ".pdf":
                pdf_text = extract_pdf_text(content)
                text_parts.append(pdf_text)
                # PDF 页渲染仅视觉模型需要;纯文本模型会把 image_url 消息拒掉
                if vision_model:
                    try:
                        pdf_imgs = pdf_to_images(content)
                        raw_images.extend(f"data:image/png;base64,{i}" for i in pdf_imgs)
                    except Exception:
                        pass
                raw_file_data.append({"name": f.filename, "bytes": content})

            elif ext == ".docx":
                docx_text = extract_docx_text(content)
                text_parts.append(docx_text)
                raw_file_data.append({"name": f.filename, "bytes": content})

            else:
                # Plain text
                decoded = ""
                for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
                    try:
                        decoded = content.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if not decoded:
                    decoded = content.decode("utf-8", errors="replace")
                text_parts.append(f"[文件: {f.filename}]\n{decoded}")
                raw_file_data.append({"name": f.filename, "bytes": content})

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"文件 {f.filename} 处理失败: {e}")

    # 有意义内容 = 用户文本 | 视觉图片 | 非「图片跳过」提示的文本片段
    meaningful = (
        bool(raw_text)
        or bool(raw_images)
        or any(not p.startswith("[图片附件]") for p in text_parts)
    )
    if not meaningful:
        if has_image_files and not vision_model:
            # 纯图片且无视觉模型: 直接给出可操作的错误,不浪费一次 LLM 调用
            job_id = str(uuid.uuid4())[:8]
            _extraction_jobs[job_id] = {
                "status": "error",
                "result": None,
                "error": (
                    "上传内容为纯图片,当前未配置视觉模型。"
                    "请粘贴文字,或在 backend/.env 设置 KB_VISION_MODEL "
                    "为支持视觉的模型(如 qwen-vl-plus、gpt-4o)后重试。"
                ),
            }
            return KnowledgeUploadJob(job_id=job_id, status="error")
        raise HTTPException(status_code=400, detail="请提供文本内容或上传文件")

    job_id = str(uuid.uuid4())[:8]
    _extraction_jobs[job_id] = {"status": "processing", "result": None, "error": None}

    background_tasks.add_task(
        _run_extraction,
        job_id,
        raw_text,
        text_parts,
        raw_images,
        raw_file_data,
        kb_type,
        name,
        problem_ref,
        user.login or "",
    )
    return KnowledgeUploadJob(job_id=job_id, status="processing")


@knowledge_router.get("/jobs/{job_id}", response_model=KnowledgeUploadJob)
async def get_extraction_job(job_id: str):
    """查询 LLM 提取任务状态。"""
    job = _extraction_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return KnowledgeUploadJob(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )


async def _run_extraction(
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
        extracted = _parse_llm_json(str(response.content))

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
        out_path = out_dir / f"{safe_name}.yaml"
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

        # 4. Incremental index(无 embedding key 时跳过向量索引,BM25/关键词检索仍可用)
        embedder = _get_embedder(user_login)
        if embedder.embeddings is None:
            from ..knowledge.retriever import invalidate_shared_retriever

            # 让共享检索器/loader 缓存失效,关键词检索能立刻看到新条目
            invalidate_shared_retriever()
            indexed = "keyword-only"
        else:
            embedder.add_document(out_path)
            indexed = "vector"

        _extraction_jobs[job_id] = {
            "status": "completed",
            "result": {
                "entry_id": entry_id,
                "entry_type": kb_type,
                "file_path": str(out_path.relative_to(settings.project_root)),
                "yaml_content": yaml_str,
                "indexed": indexed,
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


def _parse_llm_json(text: str) -> dict:
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
