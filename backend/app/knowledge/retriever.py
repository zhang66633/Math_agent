"""Hybrid retriever: multi-path recall (vector + BM25 + tag) → RRF fusion → MMR → LLM rerank → time decay."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import ClassVar

import numpy as np
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from rank_bm25 import BM25Okapi

from .embedder import KBEmbedder
from .loader import KnowledgeBaseLoader, invalidate_kb_cache
from .ranking import RRF_K, mmr_rerank, rrf_fusion  # 排序纯函数真源在 knowledge/ranking.py
from .schemas import MethodCard, Paper, Problem, Template


class HybridRetriever(BaseRetriever):
    """Combines tag-based filtering with vector similarity search and MMR reranking.

    Retrieval pipeline:
    1. Vector similarity search (with optional metadata filter)  → fetch_k candidates
    2. MMR rerank (diversity-aware)                              → deduplicate & diversify
    3. Tag-based filtering (complementary, for cold-start cases)  → merge & deduplicate
    4. Score normalization                                       → stable ordering
    """

    TAG_MATCH_SCORE: ClassVar[float] = 0.85  # fixed relevance score for tag-based matches
    RRF_K: ClassVar[int] = RRF_K  # 与模块级常量保持一致（向后兼容引用 self.RRF_K）

    # BaseRetriever 是 pydantic 模型，字段必须先声明才能赋值
    embedder: KBEmbedder
    loader: KnowledgeBaseLoader
    _vector_store: object | None = None
    _bm25: BM25Okapi | None = None
    _bm25_docs: list[Document] = []
    _bm25_tokens: list[list[str]] = []
    # query → (monotonic_ts, embedding)：实例级 TTL 缓存，随实例重建自动失效
    # （嵌入函数在实例生命周期内固定，不存在换 Key 后串味）
    _query_embeddings: dict = {}

    def __init__(
        self,
        kb_root: Path,
        persist_dir: Path,
        embedding_provider: str = "openai",
    ):
        super().__init__(
            embedder=KBEmbedder(kb_root, persist_dir, embedding_provider),
            loader=KnowledgeBaseLoader(kb_root),
        )

    # ── lazy init ──────────────────────────────────────────────────────

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = self.embedder.load_existing()
        return self._vector_store

    # ── public API ─────────────────────────────────────────────────────

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        metadata_filter: dict | None = None,
    ) -> list[tuple[Document, float]]:
        """Vector similarity search returning (document, distance_score) tuples.

        Lower distance = more relevant.  Scores are L2 distances from ChromaDB.
        """
        search_kwargs: dict = {"k": k}
        if metadata_filter:
            search_kwargs["filter"] = metadata_filter

        return self.vector_store.similarity_search_with_score(query, k=k, filter=metadata_filter)

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        metadata_filter: dict | None = None,
    ) -> list[Document]:
        """Vector similarity search without scores."""
        return self.vector_store.similarity_search(query, k=k, filter=metadata_filter)

    # ── BaseRetriever override ─────────────────────────────────────────

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
        **kwargs,
    ) -> list[Document]:
        """Multi-path retrieval: (vector + BM25 + query variants) → RRF → MMR → LLM rerank → time decay.

        Keyword Args:
            problem_type:       Tag filter (optimization / prediction / ...).
            metadata_filter:    ChromaDB where-clause dict, e.g. {"type": "paper"}.
            k:                  Final result count (default 5).
            fetch_k:            Candidates per path (default k*4, max 20).
            use_mmr:            Enable MMR diversification (default True).
            mmr_lambda:         Relevance-vs-diversity trade-off (default 0.5).
            use_reranker:       Enable LLM precision rerank (default False — 低延迟路径默认关).
            use_query_expansion: Enable query rewriting + HyDE (default False — 低延迟路径默认关).
        """
        k = kwargs.get("k", 5)
        fetch_k = kwargs.get("fetch_k", max(k * 4, 20))
        use_mmr = kwargs.get("use_mmr", True)
        mmr_lambda = kwargs.get("mmr_lambda", 0.5)
        use_reranker = kwargs.get("use_reranker", False)
        use_query_expansion = kwargs.get("use_query_expansion", False)
        problem_type = kwargs.get("problem_type")
        metadata_filter = kwargs.get("metadata_filter")

        # ── 0. Query expansion: generate variants for multi-angle retrieval ──
        queries = [query]
        if use_query_expansion:
            try:
                from ..core.llm.factory import get_llm
                from .query_expander import QueryExpander

                expander = QueryExpander(get_llm("analysis"))
                variants = expander.expand(query)
                if variants:
                    queries = [query] + [v for v in variants if v != query][:2]
                # HyDE: generate hypothetical answer for better embedding match
                hyde_text = expander.hyde(query)
                if hyde_text and hyde_text != query:
                    queries.append(hyde_text)
            except Exception:
                pass  # gracefully degrade to single query

        # ── 1. Multi-path recall per query ────────────────────────────────
        # Each query runs: vector search + BM25 search
        # Results from all queries merged via RRF
        all_vector_ranked: list[list[Document]] = []
        all_bm25_ranked: list[list[Document]] = []

        for q in queries[:3]:  # cap at 3 queries to limit latency
            # 1a. Vector search
            try:
                scored = self.similarity_search_with_score(
                    q, k=max(fetch_k, k), metadata_filter=metadata_filter
                )
                vec_docs = []
                for doc, distance in scored:
                    doc.metadata["score"] = self._normalize_chroma_score(distance)
                    vec_docs.append(doc)
                if vec_docs:
                    all_vector_ranked.append(vec_docs)
            except Exception:
                pass

            # 1b. BM25 keyword search
            try:
                bm25_docs = self._bm25_search(q, k=fetch_k)
                if bm25_docs:
                    all_bm25_ranked.append(bm25_docs)
            except Exception:
                pass

        # 1c. Tag-based exact match (deterministic, high-confidence)
        tag_docs = self._filter_by_tags(problem_type, k * 2)

        # ── 2. RRF fusion: merge all ranked lists ─────────────────────────
        # Separate vector and BM25 paths, then merge with tag results
        fused_docs: list[Document] = []
        seen: set[str] = set()

        # Vector + BM25 via RRF
        if all_vector_ranked or all_bm25_ranked:
            fused_docs = self._rrf_fusion(
                all_vector_ranked + all_bm25_ranked,
                k_constant=self.RRF_K,
                top_n=fetch_k,
            )

        # Tag results: prepend (highest confidence), deduplicate
        final_docs: list[Document] = []
        for doc in tag_docs:
            did = doc.metadata.get("id", "")
            if did not in seen:
                seen.add(did)
                final_docs.append(doc)

        # Fill remaining slots from fused results
        for doc in fused_docs:
            if len(final_docs) >= k * 2:
                break
            did = doc.metadata.get("id", "")
            if did not in seen:
                seen.add(did)
                final_docs.append(doc)

        # Fallback: keyword search if nothing found
        if not final_docs:
            final_docs = self._keyword_search(query, k)

        # ── 3. MMR diversity rerank ───────────────────────────────────────
        if use_mmr and len(final_docs) > k:
            # score 已是归一化相似度，直接喂给 MMR（不再做 1.0 - score 反转）
            scored_for_mmr = [(d, d.metadata.get("score", 0.0)) for d in final_docs]
            docs = self._mmr_rerank(query, scored_for_mmr, k=k, lam=mmr_lambda)
        else:
            docs = final_docs[:k]

        # ── 4. LLM precision rerank ───────────────────────────────────────
        if use_reranker and len(docs) > 1:
            try:
                from ..core.llm.factory import get_llm
                from .reranker import create_reranker

                reranker = create_reranker(llm=get_llm("analysis"), batch_size=10)
                docs = reranker.rerank(query, docs, top_k=k)
            except Exception:
                pass  # graceful degradation

        # ── 5. Time decay: newer papers rank higher ───────────────────────
        docs = self._apply_time_decay(docs)

        return docs[:k]

    # ── MMR ────────────────────────────────────────────────────────────

    def _mmr_rerank(
        self,
        query: str,
        scored_docs: list[tuple[Document, float]],
        k: int = 5,
        lam: float = 0.5,
    ) -> list[Document]:
        """Maximum Marginal Relevance reranking（委托 knowledge/ranking.mmr_rerank）。

        lam=1.0 → pure relevance;  lam=0.0 → pure diversity。
        向量从 vector store 注入纯函数：文档向量 + query 向量；取不到时
        纯函数内自动退化为字符 bigram 重叠（对中文更友好）。
        """
        docs = [d for d, _ in scored_docs]
        doc_embeddings = self._fetch_doc_embeddings(docs)
        # query 向量只在有文档向量时被 MMR 使用（见 ranking.mmr_rerank：
        # 拿不到文档向量就走字符 bigram 兜底，query_embedding 根本不参与）。
        # 所以文档向量缺失时算 query embedding 是纯浪费——默认 embedding 走
        # OpenAI 兼容 API，那是一次真实的延迟与费用。
        query_embedding = (
            self._embed_query(query) if doc_embeddings is not None else None
        )
        return mmr_rerank(
            query,
            scored_docs,
            k=k,
            lam=lam,
            doc_embeddings=doc_embeddings,
            query_embedding=query_embedding,
        )

    def _fetch_doc_embeddings(self, docs: list[Document]) -> np.ndarray | None:
        """从 vector store 取文档向量（N×d）；不可用或缺失返回 None。"""
        try:
            vs = self.vector_store
            ids = [d.metadata.get("id", "") for d in docs]
            if vs is None or not any(ids):
                return None
            got = vs.get(ids=ids, include=["embeddings"])
            embs = got.get("embeddings") if isinstance(got, dict) else None
            if not embs or len(embs) != len(docs):
                return None
            return np.asarray(embs, dtype=np.float64)
        except Exception:
            return None

    def _embed_query(self, query: str, ttl: float = 300.0) -> np.ndarray | None:
        """用 vector store 的 embedding function 嵌入 query；不可用返回 None。

        带实例级 TTL 缓存：同一查询会经 pipeline / chat 工具 / 搜索接口多条
        路径重复 embed（默认 embedding 走 OpenAI 兼容 API，是真实延迟与费用）。
        缓存随实例重建（invalidate_shared_retriever）自动失效——嵌入函数在
        实例生命周期内固定，不存在换 Key 后的串味问题。
        """
        cache = getattr(self, "_query_embeddings", None)
        if cache is None:  # object.__new__ 构造的测试实例没有私有槽位
            cache = {}
            try:
                object.__setattr__(self, "_query_embeddings", cache)
            except Exception:
                cache = None  # 极端环境退化为不缓存
        if cache is not None:
            hit = cache.get(query)
            if hit is not None:
                ts, emb = hit
                if time.monotonic() - ts <= ttl:
                    return emb
        try:
            if not query:
                return None
            vs = self.vector_store
            fn = getattr(vs, "_embedding_function", None) or getattr(
                vs, "embedding_function", None
            )
            if fn is None:
                return None
            emb = np.asarray(fn.embed_query(query), dtype=np.float64)
        except Exception:
            return None
        if cache is not None:
            if len(cache) >= 64:  # 简易容量上限，防无限增长
                cache.clear()
            cache[query] = (time.monotonic(), emb)
        return emb

    @staticmethod
    def _normalize_chroma_score(distance: float) -> float:
        """Convert ChromaDB L2 distance to a [0, 1] similarity score."""
        return round(1.0 / (1.0 + float(distance)), 4)

    # ── tag filtering ──────────────────────────────────────────────────

    def _filter_by_tags(self, problem_type: str | None, k: int) -> list[Document]:
        """Exact-match tag filtering: returns complete documents with scores."""
        if not problem_type:
            return []

        results: list[Document] = []

        # Method cards
        cards = self.loader.get_methods_by_category(problem_type)
        for card in cards[:k]:
            doc = self._card_to_document(card)
            doc.metadata["score"] = self.TAG_MATCH_SCORE
            results.append(doc)

        # Papers
        papers = self.loader.get_papers_by_type(problem_type)
        for paper in papers[:k]:
            doc = self._paper_to_document(paper)
            doc.metadata["score"] = self.TAG_MATCH_SCORE
            results.append(doc)

        # Templates
        templates = self.loader.get_templates_for_type(problem_type)
        for tpl in templates[:k]:
            doc = self._template_to_document(tpl)
            doc.metadata["score"] = self.TAG_MATCH_SCORE
            results.append(doc)

        # Problems
        problems = self.loader.get_problems_by_type(problem_type)
        for prob in problems[:k]:
            doc = self._problem_to_document(prob)
            doc.metadata["score"] = self.TAG_MATCH_SCORE
            results.append(doc)

        return results

    # ── keyword fallback (no embeddings required) ─────────────────────

    def _keyword_search(self, query: str, k: int) -> list[Document]:
        """关键词子串匹配兜底：向量索引不可用（未构建/无 Key）时保证基础可检索。"""
        q = query.strip().lower()
        if not q:
            return []
        terms = [t for t in q.split() if t] or [q]

        def score(text: str) -> float:
            t = text.lower()
            hits = sum(1 for term in terms if term in t)
            if hits == 0:
                return 0.0
            s = hits / len(terms)
            if q in t:
                s += 0.5
            return s

        candidates: list[tuple[Document, float]] = []

        for card in self.loader.load_all_methods():
            text = " ".join(
                [
                    card.name,
                    card.principle or "",
                    " ".join(card.category or []),
                    " ".join(card.applicable_when or []),
                    " ".join(card.typical_scenarios or []),
                ]
            )
            s = score(text)
            if s > 0:
                candidates.append((self._card_to_document(card), s))

        for paper in self.loader.load_all_papers():
            text = " ".join(
                [
                    paper.title or "",
                    str(paper.year),
                    paper.competition or "",
                    (
                        paper.analysis.get("problem_summary") or ""
                        if isinstance(paper.analysis, dict)
                        else getattr(paper.analysis, "problem_summary", "")
                        if paper.analysis
                        else ""
                    ),
                    " ".join(paper.tags.get("problem_type", []) or []),
                    " ".join(paper.tags.get("core_models", []) or []),
                ]
            )
            s = score(text)
            if s > 0:
                candidates.append((self._paper_to_document(paper), s))

        for tpl in self.loader.load_all_templates():
            text = " ".join(
                [
                    tpl.name,
                    " ".join(tpl.applicable_to or []),
                    " ".join(step.name for step in (tpl.steps or [])),
                ]
            )
            s = score(text)
            if s > 0:
                candidates.append((self._template_to_document(tpl), s))

        for prob in self.loader.load_all_problems():
            text = " ".join(
                [
                    prob.title,
                    str(prob.year),
                    prob.competition or "",
                    prob.background or "",
                    " ".join(prob.objectives or []),
                    " ".join(prob.tags.get("problem_type", []) or []),
                ]
            )
            s = score(text)
            if s > 0:
                candidates.append((self._problem_to_document(prob), s))

        candidates.sort(key=lambda x: x[1], reverse=True)
        out: list[Document] = []
        for doc, s in candidates[:k]:
            # 关键词匹配置信度低于 tag(0.85) 与向量，但保证可用
            doc.metadata["score"] = min(0.5 + 0.3 * s, 0.9)
            out.append(doc)
        return out

    # ── BM25 keyword search ──────────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Simple Chinese-friendly tokenizer (character bigrams + words)."""
        tokens = []
        # Split on whitespace for pre-segmented text
        words = text.lower().split()
        tokens.extend(words)
        # For Chinese text without spaces: use character bigrams
        for word in words:
            if len(word) > 2 and all("一" <= c <= "鿿" for c in word):
                for i in range(len(word) - 1):
                    tokens.append(word[i : i + 2])
        if not tokens:
            tokens = [text.lower()[:100]]
        return tokens

    def _ensure_bm25(self) -> None:
        """Lazy-build BM25 index from all knowledge base documents."""
        if self._bm25 is not None:
            return
        self._bm25_docs = []
        all_tokens: list[list[str]] = []

        for card in self.loader.load_all_methods():
            doc = self._card_to_document(card)
            self._bm25_docs.append(doc)
            all_tokens.append(self._tokenize(doc.page_content))

        for paper in self.loader.load_all_papers():
            doc = self._paper_to_document(paper)
            self._bm25_docs.append(doc)
            all_tokens.append(self._tokenize(doc.page_content))

        for tpl in self.loader.load_all_templates():
            doc = self._template_to_document(tpl)
            self._bm25_docs.append(doc)
            all_tokens.append(self._tokenize(doc.page_content))

        for prob in self.loader.load_all_problems():
            doc = self._problem_to_document(prob)
            self._bm25_docs.append(doc)
            all_tokens.append(self._tokenize(doc.page_content))

        if all_tokens:
            self._bm25 = BM25Okapi(all_tokens)
            self._bm25_tokens = all_tokens

    def _bm25_search(self, query: str, k: int) -> list[Document]:
        """BM25 keyword search, returns ranked documents with normalized scores."""
        self._ensure_bm25()
        if not self._bm25 or not self._bm25_docs:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        if scores is None or len(scores) == 0:
            return []

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:k]

        result: list[Document] = []
        max_score = float(scores[top_indices[0]]) if len(top_indices) > 0 else 1.0
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            doc = self._bm25_docs[idx]
            # Copy metadata to avoid mutating original
            doc.metadata = {**doc.metadata}
            doc.metadata["score"] = round(float(scores[idx]) / max(max_score, 1e-8), 4)
            result.append(doc)

        return result

    # ── RRF fusion ───────────────────────────────────────────────────────

    @staticmethod
    def _rrf_fusion(
        ranked_lists: list[list[Document]],
        k_constant: int = RRF_K,
        top_n: int | None = None,
    ) -> list[Document]:
        """Reciprocal Rank Fusion（委托 knowledge/ranking.rrf_fusion）。"""
        return rrf_fusion(ranked_lists, k_constant=k_constant, top_n=top_n)

    # ── time decay ───────────────────────────────────────────────────────

    @staticmethod
    def _apply_time_decay(docs: list[Document], decay: float = 0.95) -> list[Document]:
        """Apply time-based score decay for papers and problems.

        Newer documents get a boost: score *= decay^(current_year - doc_year).
        Only applies to documents with a 'year' in metadata.
        """
        from datetime import datetime

        current_year = datetime.now().year

        for doc in docs:
            year = doc.metadata.get("year")
            doc_type = doc.metadata.get("type", "")
            if year and doc_type in ("paper", "problem"):
                age = max(0, current_year - int(year))
                current_score = doc.metadata.get("score", 1.0)
                doc.metadata["score"] = current_score * (decay**age)

        # Re-sort by adjusted score
        docs.sort(key=lambda d: d.metadata.get("score", 0.0), reverse=True)
        return docs

    # ── document builders (rich page_content for tag results) ──────────

    @staticmethod
    def _fmt_str_or_obj(val, attr="mistake"):
        """兼容 Union[str, Object]：str 直接返回，对象取 .attr 属性。"""
        if isinstance(val, str):
            return val
        return getattr(val, attr, str(val))

    @staticmethod
    def _card_to_document(card: MethodCard) -> Document:
        parts = [card.principle]
        if card.formulas:
            parts.append(
                "公式: "
                + "; ".join(
                    f.latex if hasattr(f, "latex") and f.latex else str(f) for f in card.formulas
                )
            )
        if card.typical_scenarios:
            parts.append("适用场景: " + "; ".join(card.typical_scenarios))
        if card.applicable_when:
            parts.append("适用条件: " + "; ".join(card.applicable_when))
        if card.not_applicable_when:
            parts.append("不适用条件: " + "; ".join(card.not_applicable_when))
        if card.common_mistakes:
            parts.append(
                "常见误用: "
                + "; ".join(
                    HybridRetriever._fmt_str_or_obj(m, "mistake") for m in card.common_mistakes
                )
            )
        if card.code_snippets:
            parts.append(
                "代码示例: "
                + "\n---\n".join(
                    cs if isinstance(cs, str) else f"```{cs.language}\n{cs.code}\n```"
                    for cs in card.code_snippets
                )
            )
        # 追加新字段到 page_content（提升向量检索命中率）
        extra = []
        for tag_key, tag_val in (card.tags or {}).items():
            if isinstance(tag_val, list):
                extra.append(f"{tag_key}: " + ", ".join(tag_val))
        if extra:
            parts.append("标签: " + "; ".join(extra))
        return Document(
            page_content="\n".join(parts),
            metadata={
                "type": "method_card",
                "id": card.id,
                "name": card.name,
                "name_en": card.name_en or "",
                "categories": card.category,
                "related_cards": card.related_cards,
                "related_papers": card.related_papers,
                "difficulty": card.difficulty,
                "quality_rating": card.quality_rating,
            },
        )

    @staticmethod
    def _paper_to_document(paper: Paper) -> Document:
        a = paper.analysis
        m = paper.model
        e = paper.evaluation
        parts = [
            f"题目: {paper.title}",
            f"年份: {paper.year} | 竞赛: {paper.competition} | 赛题: {paper.problem_id}",
            f"问题类型: {paper.tags.get('problem_type', [])}",
            f"核心模型: {paper.tags.get('core_models', [])}",
        ]
        # 兼容 union 类型：dict 用 .get()，Pydantic 对象用属性
        if isinstance(a, dict):
            parts.append(f"问题概述: {a.get('problem_summary', '')}")
            if a.get("background"):
                parts.append(f"背景: {a.get('background')}")
            if a.get("key_insights"):
                parts.append(f"关键洞察: {'; '.join(a.get('key_insights', []))}")
            if a.get("solution_framework"):
                parts.append(f"求解框架: {a.get('solution_framework')}")
        else:
            parts.append(f"问题概述: {a.problem_summary or ''}")
            if a.key_assumptions:
                parts.append("关键假设: " + "; ".join(a.key_assumptions))

        if isinstance(m, dict):
            parts.append(f"建模思路: {m.get('methodology', '')}")
            parts.append(f"创新点: {m.get('innovations', '') or ''}")
        else:
            parts.append(f"建模思路: {m.approach or ''}")
            parts.append(f"创新点: {m.innovation or ''}")

        if isinstance(e, dict):
            if e.get("strengths"):
                parts.append("优点: " + "; ".join(e["strengths"]))
            if e.get("weaknesses"):
                parts.append("不足: " + "; ".join(e["weaknesses"]))
        else:
            if e.strengths:
                parts.append("优点: " + "; ".join(e.strengths))
            if e.weaknesses:
                parts.append("不足: " + "; ".join(e.weaknesses))

        if paper.takeaways:
            parts.append("核心经验: " + "; ".join(paper.takeaways))

        return Document(
            page_content="\n".join(parts),
            metadata={
                "type": "paper",
                "id": paper.id,
                "title": paper.title,
                "year": paper.year,
                "competition": paper.competition,
                "problem_id": paper.problem_id,
                "difficulty": paper.difficulty,
                "quality_rating": paper.quality_rating,
            },
        )

    @staticmethod
    def _template_to_document(tpl: Template) -> Document:
        parts = [f"框架名称: {tpl.name}"]
        for step in tpl.steps:
            parts.append(f"\n步骤{step.step}: {step.name}")
            if step.guiding_questions:
                parts.append("引导问题:")
                parts.extend(f"  - {q}" for q in step.guiding_questions)
            if step.decision_tree:
                parts.append("决策路径:")
                parts.extend(f"  - {d}" for d in step.decision_tree)
            if step.checklist:
                parts.append("检查清单:")
                parts.extend(f"  - {c}" for c in step.checklist)

        return Document(
            page_content="\n".join(parts),
            metadata={
                "type": "template",
                "id": tpl.id,
                "name": tpl.name,
                "applicable_to": tpl.applicable_to,
            },
        )

    @staticmethod
    def _problem_to_document(prob: Problem) -> Document:
        parts = [
            f"赛题: {prob.title}",
            f"年份: {prob.year} | 竞赛: {prob.competition} | 题号: {prob.problem_id}",
            f"问题类型: {prob.tags.get('problem_type', [])}",
        ]
        if prob.background:
            parts.append(f"背景: {prob.background}")
        if prob.objectives:
            parts.append("求解目标:")
            parts.extend(f"  - {o}" for o in prob.objectives)
        if prob.data_description:
            parts.append(f"数据描述: {prob.data_description}")
        if prob.data_files:
            parts.append("附件数据文件:")
            for df in prob.data_files:
                parts.append(
                    f"  - {df.get('filename', '?')} "
                    f"({df.get('rows', '?')}行, 列: {', '.join(df.get('columns', []))})"
                )
        if prob.deliverables:
            parts.append("提交要求:")
            parts.extend(f"  - {d}" for d in prob.deliverables)
        if prob.full_text:
            parts.append(f"完整题目: {prob.full_text[:1500]}")

        return Document(
            page_content="\n".join(parts),
            metadata={
                "type": "problem",
                "id": prob.id,
                "year": prob.year,
                "competition": prob.competition,
                "problem_id": prob.problem_id,
                "title": prob.title,
                "linked_papers": prob.linked_papers,
                "data_description": prob.data_description,
                "data_files": prob.data_files,
            },
        )

    # ── merge & dedup ──────────────────────────────────────────────────

    @staticmethod
    def _merge_results(
        tag_docs: list[Document],
        vector_docs: list[Document],
        k: int,
    ) -> list[Document]:
        """Merge tag and vector results, deduplicating by ID.

        Tag results come first (deterministic, high-confidence matches),
        then vector results fill remaining slots.
        """
        seen_ids: set[str] = set()
        merged: list[Document] = []

        for doc in tag_docs + vector_docs:
            doc_id = doc.metadata.get("id")
            if doc_id and doc_id in seen_ids:
                continue
            if doc_id:
                seen_ids.add(doc_id)
            merged.append(doc)
            if len(merged) >= k:
                break

        return merged

    # ── convenience factory ────────────────────────────────────────────

    def as_langchain_retriever(
        self,
        search_kwargs: dict | None = None,
    ):
        """Return self as a LangChain-compatible retriever (already is one).

        Provided for API parity with vectorstore.as_retriever().
        """
        if search_kwargs:
            # Wrap to inject default kwargs
            original = self._get_relevant_documents

            def with_kwargs(query, *, run_manager=None, **kw):
                merged = {**search_kwargs, **kw}
                return original(query, run_manager=run_manager, **merged)

            self._get_relevant_documents = with_kwargs  # type: ignore[method-assign]

        return self


# ── 共享单例（跨 pipeline / search / chat 复用，避免每请求重建 BM25 + 重载 Chroma）──

_shared_retriever: HybridRetriever | None = None
_shared_retriever_lock = threading.Lock()


def get_shared_retriever() -> HybridRetriever:
    """返回进程级共享的 HybridRetriever 单例（懒加载，BM25/Chroma 只建一次）。"""
    global _shared_retriever
    if _shared_retriever is None:
        with _shared_retriever_lock:
            if _shared_retriever is None:
                from ..config import get_settings

                settings = get_settings()
                _shared_retriever = HybridRetriever(
                    kb_root=settings.kb_root,
                    persist_dir=settings.chroma_dir,
                    embedding_provider=settings.kb_embedding_provider,
                )
    return _shared_retriever


def invalidate_shared_retriever() -> None:
    """失效共享单例并清空 loader 解析缓存（reindex/import 后调用）。

    同时清空搜索接口的结果缓存——否则内容已更新、/api/knowledge/search
    还会返回旧的缓存结果（TTL 最长 120s）。
    """
    global _shared_retriever
    _shared_retriever = None
    invalidate_kb_cache()
    from .search_cache import clear_search_cache

    clear_search_cache()
