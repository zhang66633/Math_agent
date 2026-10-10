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
