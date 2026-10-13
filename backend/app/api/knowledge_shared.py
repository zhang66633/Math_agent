"""知识库路由共享层 — Pydantic 响应模型 + 路由辅助函数（god-files 拆分 #31）。

KB 文件系统助手已移到 knowledge/kb_files.py（services 需要且不应反向 import
api 模块），此处再导出保持既有路由 import 不变。
"""

from pathlib import Path

from pydantic import BaseModel

from ..knowledge.kb_files import (  # noqa: F401  (再导出供路由 import)
    _find_yaml_file,
    _get_embedder,
    _get_loader,
    _next_id,
)

# ── response models ────────────────────────────────────────────────────


class KBStats(BaseModel):
    methods_count: int = 0
    papers_count: int = 0
    templates_count: int = 0
    problems_count: int = 0
    total: int = 0


class MethodCardSummary(BaseModel):
    id: str
    name: str
    category: list[str]
    applicable_when: list[str]
    typical_scenarios: list[str]


class MethodCardDetail(BaseModel):
    id: str
    name: str
    category: list[str]
    principle: str
    formulas: list[dict]
    applicable_when: list[str]
    not_applicable_when: list[str]
    typical_scenarios: list[str]
    common_mistakes: list[dict]
    code_snippets: list[dict]
    related_cards: list[str]
    related_papers: list[str]
    # 方案 C：关联的学习单元 id（前端可跳转 /learn/<unit_id>）；空串表示无关联
    unit_id: str = ""


def normalize_entries(values, main_key: str, extra_keys: tuple[str, ...]) -> list[dict]:
    """把加载器宽容的 ``str | dict`` 列表归一化成响应模型要的 ``list[dict]``。

    背景（审计 2026-10-14 P0）：知识库 YAML 有两种历史格式——结构化对象
    （``{name, latex, description}`` 等）与纯字符串（``"0-1背包: dp[i][w] = ..."``）。
    加载器 ``knowledge/schemas.py`` 的 MethodCard 明确两种都收，而本模块的
    ``MethodCardDetail`` 只收 dict。此前 ``get_method`` 直接
    ``MethodCardDetail(**card.model_dump())``，字符串条目触发 pydantic
    ValidationError → **22/86 张卡片的详情接口返回 500**，且前端编辑保存会
    顺着这条失败路径把整张卡的公式/代码抹成空（PUT 用表单整体覆写 YAML 真源）。

    归一化策略是**无损收纳**而非猜测式拆分：字符串整体进主字段（公式进
    ``latex``、错误进 ``mistake``、代码进 ``code``），其余字段留空串；
    结构化对象原样通过并补齐缺失字段，保证响应形状稳定。
    """
    keys = (main_key, *extra_keys)
    out: list[dict] = []
    for v in values or []:
        if isinstance(v, dict):
            out.append({k: ("" if v.get(k) is None else str(v.get(k) or "")) for k in keys})
        else:
            entry = dict.fromkeys(keys, "")
            entry[main_key] = "" if v is None else str(v)
            out.append(entry)
    return out


def method_card_detail(card) -> MethodCardDetail:
    """从加载器的 MethodCard 构造 API 响应模型（含 str→dict 归一化）。"""
    data = card.model_dump()
    data["formulas"] = normalize_entries(data.get("formulas"), "latex", ("name", "description"))
    data["common_mistakes"] = normalize_entries(
        data.get("common_mistakes"), "mistake", ("solution",)
    )
    data["code_snippets"] = normalize_entries(
        data.get("code_snippets"), "code", ("language", "description")
    )
    return MethodCardDetail(**data)


class PaperSummary(BaseModel):
    id: str
    year: int
    competition: str
    problem_id: str
    title: str
    tags: dict
    quality_rating: int
    problem_ref: str = ""


class PaperDetail(BaseModel):
    id: str
    year: int
    competition: str
    problem_id: str
    title: str
    tags: dict
    problem_ref: str = ""
    problem_context: str = ""
    methodology_chain: list[str] = []
    key_formulas: list[dict] = []
    algorithm_outline: list[dict] = []
    assumption_analysis: list[str] = []
    reusable_patterns: list[str] = []
    common_pitfalls: list[dict] = []
    difficulty_level: str = "medium"
    analysis: dict
    model: dict
    evaluation: dict
    source: str
    quality_rating: int


class TemplateSummary(BaseModel):
    id: str
    name: str
    applicable_to: list[str]
    steps_count: int


class TemplateDetail(BaseModel):
    id: str
    name: str
    applicable_to: list[str]
    steps: list[dict]


class ProblemSummary(BaseModel):
    id: str
    year: int
    competition: str
    problem_id: str
    title: str
    tags: dict
    linked_papers_count: int = 0


class ProblemDetail(BaseModel):
    id: str
    year: int
    competition: str
    problem_id: str
    title: str
    full_text: str = ""
    background: str = ""
    objectives: list[str] = []
    data_description: str = ""
    deliverables: list[str] = []
    tags: dict
    linked_papers: list[str] = []
    source_url: str = ""


class SearchResult(BaseModel):
    id: str
    type: str
    name: str = ""
    title: str = ""
    snippet: str
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


class ReindexResponse(BaseModel):
    success: bool
    indexed_count: int
    message: str


# ── CRUD response models ─────────────────────────────────────────────


class KnowledgeCrudResponse(BaseModel):
    success: bool
    entry_id: str = ""
    message: str = ""


class KnowledgeUploadJob(BaseModel):
    job_id: str
    status: str  # "processing" | "completed" | "error"
    result: dict | None = None
    error: str | None = None


# ── helpers ─────────────────────────────────────────────────────────


def _get_retriever():
    """返回进程级共享 retriever 单例（复用 BM25 与 Chroma，避免每请求重建）。"""
    from ..knowledge.retriever import get_shared_retriever

    return get_shared_retriever()


def _sync_kb_index(
    remove_ids: list[str], add_path: Path | None, user_id: str | None = None
) -> str:
    """CRUD 后的向量索引同步(无 embedding key 时降级关键词索引)。

    - 有向量 key: 执行 remove/add,embedder 内部会失效检索器缓存,返回 "vector"
    - 无向量 key: 跳过向量操作,仅失效共享检索器缓存(关键词检索立刻可见),
      返回 "keyword-only" —— 与导入流水线同一降级策略
    """
    from ..knowledge.retriever import invalidate_shared_retriever

    embedder = _get_embedder(user_id)
    if embedder.embeddings is None:
        invalidate_shared_retriever()
        return "keyword-only"
    for rid in remove_ids:
        embedder.remove_document(rid)
    if add_path is not None:
        embedder.add_document(add_path)
    return "vector"


# ── stats ───────────────────────────────────────────────────────────────
