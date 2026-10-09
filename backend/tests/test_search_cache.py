"""搜索结果缓存回归测试 — 副本隔离 / 清理 / 与 invalidate 联动 / 接口接线。

背景：`/api/knowledge/search` 是交互式高精度路径，单次查询约 3 次额外
LLM 调用（query expansion + HyDE + rerank）。缓存让重复查询跳过整条
检索链；内容变更必须随 invalidate_shared_retriever 一并失效。
"""

from __future__ import annotations

import asyncio

from langchain_core.documents import Document

from app.knowledge import search_cache


def test_cache_stores_copies():
    """缓存存副本：检索链就地改写 metadata 不污染缓存内容。"""
    search_cache.clear_search_cache()
    docs = [
        Document(page_content="线性规划", metadata={"id": "mc_001", "score": 0.9})
    ]
    search_cache.set_cached_docs(("q", "", "", 5), docs)

    # 模拟检索链内部对原对象的就地改写
    docs[0].metadata["score"] = 0.1
    docs[0].page_content = "被污染"

    hit = search_cache.get_cached_docs(("q", "", "", 5))
    assert hit is not None
    assert hit[0].metadata["score"] == 0.9
    assert hit[0].page_content == "线性规划"


def test_cache_miss_after_clear():
    search_cache.clear_search_cache()
    search_cache.set_cached_docs(("q2", "", "", 5), [Document(page_content="x")])
    assert search_cache.get_cached_docs(("q2", "", "", 5)) is not None

    search_cache.clear_search_cache()
    assert search_cache.get_cached_docs(("q2", "", "", 5)) is None


def test_invalidate_shared_retriever_clears_search_cache():
    """回归：内容变更的唯一失效点必须同时清搜索结果缓存（防陈旧结果）。"""
    from app.knowledge import retriever as retriever_mod

    search_cache.clear_search_cache()
    search_cache.set_cached_docs(("q3", "", "", 5), [Document(page_content="y")])

    retriever_mod.invalidate_shared_retriever()

    assert search_cache.get_cached_docs(("q3", "", "", 5)) is None


def test_kb_search_uses_cache(monkeypatch):
    """回归：相同参数的重复查询只走一次检索链（缓存接线正确）。"""
    from app.api import knowledge_search_routes as ks

    class FakeRetriever:
        def __init__(self):
            self.calls = 0

        def _get_relevant_documents(self, q, **kwargs):
            self.calls += 1
            return [
                Document(
                    page_content="线性规划原理与适用条件",
                    metadata={
                        "id": "mc_001",
                        "type": "method_card",
                        "name": "线性规划",
                    },
                )
            ]

    fake = FakeRetriever()
    monkeypatch.setattr(ks, "_get_retriever", lambda: fake)
    search_cache.clear_search_cache()

    async def _call():
        r1 = await ks.kb_search(q="线性规划", type=None, problem_type=None, k=5)
        r2 = await ks.kb_search(q="线性规划", type=None, problem_type=None, k=5)
        return r1, r2

    r1, r2 = asyncio.run(_call())

    assert fake.calls == 1  # 第二次命中缓存，没有再次调用检索链
    assert r1.total == r2.total == 1
    assert r2.results[0].name == "线性规划"
    assert r2.results[0].id == "mc_001"
