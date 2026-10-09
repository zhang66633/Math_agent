"""知识库检索/上传/任务路由（god-files 拆分 #31：从 knowledge_routes.py 拆出）。"""

"""Knowledge base management API — browse, search, reindex, upload, and CRUD."""

import uuid
from pathlib import Path

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
    extract_docx_text,
    extract_pdf_text,
    parse_csv,
    parse_excel,
    pdf_to_images,
)
from ..services.knowledge_ingest import get_job, new_job, run_extraction
from .knowledge_shared import *  # noqa: F403
from .knowledge_shared import (  # noqa: F401
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
            new_job(
                job_id,
                "error",
                error=(
                    "上传内容为纯图片,当前未配置视觉模型。"
                    "请粘贴文字,或在 backend/.env 设置 KB_VISION_MODEL "
                    "为支持视觉的模型(如 qwen-vl-plus、gpt-4o)后重试。"
                ),
            )
            return KnowledgeUploadJob(job_id=job_id, status="error")
        raise HTTPException(status_code=400, detail="请提供文本内容或上传文件")

    job_id = str(uuid.uuid4())[:8]
    new_job(job_id, "processing")

    background_tasks.add_task(
        run_extraction,
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
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return KnowledgeUploadJob(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )
