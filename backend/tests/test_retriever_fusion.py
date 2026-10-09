"""HybridRetriever 融合/重排单元测试（无网络、无 LLM，纯合成数据）。

覆盖 007 计划 §2 的两处数学修正：
  - `_rrf_fusion`：RRF 分数随 rank 递减，且 top_n 截断与 k_constant 解耦；
  - `_mmr_rerank`：入参直接为归一化相似度（无双重反转），相同文档不产生 NaN/负值。

既可用 `python -m pytest backend/tests/test_retriever_fusion.py -q` 运行，
也可直接 `python backend/tests/test_retriever_fusion.py` 跑（`__main__` 自执行）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让 `app` 包在「backend 目录」与「项目根目录」两种 cwd 下都可导入
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import math

from langchain_core.documents import Document

from app.knowledge.retriever import HybridRetriever


def _doc(doc_id: str, content: str) -> Document:
    return Document(page_content=content, metadata={"id": doc_id})


# ── 假 vector store：用于把 _mmr_rerank 逼入 fallback 或注入已知向量 ──


class _RaisingStore:
    """`.get` 抛异常 → 强制走字符 bigram fallback。"""

    def get(self, *args, **kwargs):
        raise RuntimeError("no vectors")


class _FakeEmbeddingFn:
    def __init__(self, query_vec):
        self._query_vec = query_vec

    def embed_query(self, query):
        return self._query_vec


class _FakeVectorStore:
    """返回已知向量，用于验证 embedding 余弦 diversity 与 query 向量路径。"""

    def __init__(self, embeddings, query_vec=None):
        self._embeddings = embeddings  # {doc_id: vector}
        if query_vec is not None:
            self._embedding_function = _FakeEmbeddingFn(query_vec)

    def get(self, ids=None, include=None):
        embs = [self._embeddings.get(i) for i in (ids or [])]
        return {"ids": ids, "embeddings": embs}


def _bare_retriever(vector_store) -> HybridRetriever:
    """构造无真实依赖的 retriever 实例（绕过 pydantic 初始化与 config 解析）。"""
    r = object.__new__(HybridRetriever)
    object.__setattr__(r, "_vector_store", vector_store)
    return r


# ── RRF ────────────────────────────────────────────────────────────────


def test_rrf_scores_decrease_with_rank():
    ranked = [[_doc("d1", "a"), _doc("d2", "b"), _doc("d3", "c")]]
    fused = HybridRetriever._rrf_fusion(ranked)
    assert [d.metadata["id"] for d in fused] == ["d1", "d2", "d3"]
    s1 = fused[0].metadata["score"]
    s2 = fused[1].metadata["score"]
    s3 = fused[2].metadata["score"]
    assert s1 > s2 > s3


def test_rrf_top_n_truncation_decoupled_from_k():
    ranked = [[_doc("d1", "a"), _doc("d2", "b"), _doc("d3", "c")]]

    # 无 top_n：不截断
    all_docs = HybridRetriever._rrf_fusion(ranked)
    assert len(all_docs) == 3

    # top_n=2：截断到 2，且与 k_constant 取值无关
    top2 = HybridRetriever._rrf_fusion(ranked, k_constant=60, top_n=2)
    assert len(top2) == 2
    assert [d.metadata["id"] for d in top2] == ["d1", "d2"]

    top2_small_k = HybridRetriever._rrf_fusion(ranked, k_constant=5, top_n=2)
    assert len(top2_small_k) == 2
    assert [d.metadata["id"] for d in top2_small_k] == ["d1", "d2"]

    # k_constant 变化只改分数、不改顺序
    big_k = HybridRetriever._rrf_fusion(ranked, k_constant=1000)
    assert [d.metadata["id"] for d in big_k] == ["d1", "d2", "d3"]


def test_rrf_accumulates_across_lists():
    # d1 同时出现在两个列表的 rank0，d2 只在一个列表 rank0
    ranked = [
        [_doc("d1", "a"), _doc("d2", "b")],
        [_doc("d1", "a"), _doc("d3", "c")],
    ]
    fused = HybridRetriever._rrf_fusion(ranked)
    ids = [d.metadata["id"] for d in fused]
    assert ids[0] == "d1"
    d1_score = fused[0].metadata["score"]
    d2_score = next(d.metadata["score"] for d in fused if d.metadata["id"] == "d2")
    assert d1_score > d2_score


# ── MMR ────────────────────────────────────────────────────────────────


def test_mmr_no_nan_negative_on_identical_docs():
    r = _bare_retriever(_RaisingStore())
    docs = [
        _doc("d1", "linear programming optimization"),
        _doc("d2", "linear programming optimization"),
        _doc("d3", "linear programming optimization"),
    ]
    scored = [(d, s) for d, s in zip(docs, [0.9, 0.8, 0.7], strict=False)]
    out = r._mmr_rerank("optimization", scored, k=3, lam=0.5)
    assert len(out) == 3
    for d in out:
        s = d.metadata["score"]
        assert isinstance(s, float)
        assert not math.isnan(s)
        assert s >= 0.0


def test_mmr_pure_relevance_keeps_order():
    r = _bare_retriever(_RaisingStore())
    docs = [_doc("d1", "aaa"), _doc("d2", "bbb"), _doc("d3", "ccc")]
    scored = [(d, s) for d, s in zip(docs, [0.9, 0.8, 0.7], strict=False)]
    out = r._mmr_rerank("x", scored, k=3, lam=1.0)
    assert [d.metadata["id"] for d in out] == ["d1", "d2", "d3"]


def test_mmr_diversity_selects_distinct_doc():
    # d1 与 d2 内容相同（bigram 重叠=1），d3 内容差异大；lam=0.0 纯 diversity
    r = _bare_retriever(_RaisingStore())
    docs = [
        _doc("d1", "linear programming optimization"),
        _doc("d2", "linear programming optimization"),
        _doc("d3", "neural network deep learning"),
    ]
    scored = [(d, s) for d, s in zip(docs, [0.9, 0.8, 0.7], strict=False)]
    out = r._mmr_rerank("x", scored, k=3, lam=0.0)
    ids = [d.metadata["id"] for d in out]
    # d3 应在 d2 之前被选中（避免与已选 d1 重复）
    assert ids.index("d3") < ids.index("d2")


def test_mmr_embedding_cosine_and_query_path():
    # 注入已知向量：d1/d2 相同、d3 正交；query 向量偏向 d1/d2
    store = _FakeVectorStore(
        embeddings={
            "d1": [1.0, 0.0],
            "d2": [1.0, 0.0],
            "d3": [0.0, 1.0],
        },
        query_vec=[1.0, 0.0],
    )
    r = _bare_retriever(store)
    docs = [
        _doc("d1", "linear programming optimization"),
        _doc("d2", "linear programming optimization"),
        _doc("d3", "neural network deep learning"),
    ]
    scored = [(d, s) for d, s in zip(docs, [0.9, 0.8, 0.7], strict=False)]
    out = r._mmr_rerank("linear programming", scored, k=3, lam=0.5)
    ids = [d.metadata["id"] for d in out]
    assert len(ids) == 3
    assert ids[0] == "d1"  # 相关性最高 + query 向量同向
    # d2 与 d1 余弦=1 被 diversity 惩罚，d3 先于 d2
    assert ids.index("d3") < ids.index("d2")
    for d in out:
        assert not math.isnan(d.metadata["score"])
        assert d.metadata["score"] >= 0.0


def test_singleton_symbols_importable():
    from app.knowledge.retriever import get_shared_retriever, invalidate_shared_retriever

    assert callable(get_shared_retriever)
    assert callable(invalidate_shared_retriever)


def test_ranking_module_pure_functions():
    """god-files 拆分后的纯函数模块直接可用（ranking.py）。"""
    from app.knowledge import ranking

    docs = [
        Document(page_content="线性规划", metadata={"id": "a"}),
        Document(page_content="整数规划", metadata={"id": "b"}),
        Document(page_content="时间序列", metadata={"id": "c"}),
    ]
    # rrf_fusion: rank 递减 + top_n 独立于 k_constant
    fused = ranking.rrf_fusion([docs, list(reversed(docs))], k_constant=60, top_n=2)
    assert len(fused) == 2 and fused[0].metadata["id"] == "a"
    assert abs(fused[0].metadata["score"] - (1 / 61 + 1 / 63)) < 1e-6

    # char bigram 对中文有效
    assert "线性" in ranking.char_bigrams("线性规划")

    # mmr_rerank 无向量时走 bigram 兜底，不产生 NaN
    out = ranking.mmr_rerank("q", [(d, 0.9 - i * 0.1) for i, d in enumerate(docs)], k=3, lam=0.5)
    assert len(out) == 3
    for d in out:
        assert not math.isnan(d.metadata["score"])
        assert d.metadata["score"] >= 0.0


# ── query embedding 缓存与按需计算（优化 ④）─────────────────────────


class _CountingEmbeddingFn:
    def __init__(self, query_vec):
        self._query_vec = query_vec
        self.calls = 0

    def embed_query(self, query):
        self.calls += 1
        return self._query_vec


def test_embed_query_caches_per_instance():
    """同一 query 二次 embed 命中实例级缓存（embedding 走 API 时是真实费用）。"""
    fn = _CountingEmbeddingFn([1.0, 0.0])
    store = _FakeVectorStore(embeddings={})
    store._embedding_function = fn
    r = _bare_retriever(store)

    v1 = r._embed_query("线性规划")
    v2 = r._embed_query("线性规划")

    assert fn.calls == 1
    assert v1 is not None and v2 is not None

    # 新实例（模拟 invalidate_shared_retriever 后重建）不共享缓存
    r2 = _bare_retriever(store)
    r2._embed_query("线性规划")
    assert fn.calls == 2


def test_mmr_skips_query_embedding_without_doc_embeddings(monkeypatch):
    """无文档向量时 MMR 走 bigram 兜底，query embedding 算了也白算 → 不算。"""
    r = _bare_retriever(_RaisingStore())  # .get 抛异常 → 文档向量 None

    calls = {"n": 0}

    def _counting_embed(query, ttl=300.0):
        calls["n"] += 1
        return None

    monkeypatch.setattr(r, "_embed_query", _counting_embed)
    r._mmr_rerank(
        "查询",
        [(_doc("a", "线性规划"), 0.9), (_doc("b", "整数规划"), 0.8)],
        k=1,
    )
    assert calls["n"] == 0


def test_mmr_computes_query_embedding_with_doc_embeddings(monkeypatch):
    """有文档向量时 query 向量正常参与（相关性修正路径不回归）。"""
    store = _FakeVectorStore(
        embeddings={"a": [1.0, 0.0], "b": [0.9, 0.1]},
        query_vec=[1.0, 0.0],
    )
    r = _bare_retriever(store)
    calls = {"n": 0}
    orig = HybridRetriever._embed_query

    def _counting(self, query, ttl=300.0):
        calls["n"] += 1
        return orig(self, query, ttl)

    monkeypatch.setattr(HybridRetriever, "_embed_query", _counting)
    docs = r._mmr_rerank(
        "查询",
        [(_doc("a", "线性规划"), 0.9), (_doc("b", "整数规划"), 0.8)],
        k=1,
    )
    assert calls["n"] == 1
    assert len(docs) == 1


# ── 直接以脚本运行时自执行全部 test_* ────────────────────────────────

if __name__ == "__main__":
    failures = []
    for name in sorted(globals()):
        if name.startswith("test_") and callable(globals()[name]):
            fn = globals()[name]
            try:
                fn()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                failures.append((name, e))
                print(f"FAIL {name}: {e!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nALL TESTS PASSED")
