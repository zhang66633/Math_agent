"""知识库搜索结果缓存 — LRU + TTL，供 `/api/knowledge/search` 使用。

背景：该接口是交互式高精度路径，显式开启 query expansion + HyDE + LLM
rerank，单次查询约 3 次额外 LLM round trip（无缓存时搜索框重复查询/多人
同时查询会把 analysis 模型打满）。此处对最终文档列表做短 TTL 缓存，
重复查询直接跳过整条检索链。

一致性：缓存必须在知识库内容变更时失效——`invalidate_shared_retriever()`
（import / reindex / CRUD 的唯一失效点）会一并调用 `clear_search_cache()`，
不会出现「内容已更新、搜索结果还是旧的」。

存储的是 Document 副本（metadata 浅拷贝）：检索链内部会就地改写
doc.metadata["score"]，若缓存原对象会被后续检索污染。
"""

from __future__ import annotations

import threading
import time

from langchain_core.documents import Document

_TTL_SECONDS = 120.0
_MAX_ENTRIES = 128

_lock = threading.Lock()
# key → (monotonic 时间戳, Document 副本列表)
_store: dict[tuple, tuple[float, list[Document]]] = {}


def get_cached_docs(key: tuple) -> list[Document] | None:
    """命中且未过期返回副本列表，否则 None。"""
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is None:
            return None
        ts, docs = hit
        if now - ts > _TTL_SECONDS:
            del _store[key]
            return None
        return docs


def set_cached_docs(key: tuple, docs: list[Document]) -> None:
    """写入缓存（存副本，隔离检索链对 metadata 的就地改写）。"""
    copies = [
        Document(page_content=d.page_content, metadata=dict(d.metadata))
        for d in docs
    ]
    with _lock:
        if len(_store) >= _MAX_ENTRIES and key not in _store:
            # 简易 LRU：淘汰最旧一条
            oldest = min(_store.items(), key=lambda kv: kv[1][0])[0]
            del _store[oldest]
        _store[key] = (time.monotonic(), copies)


def clear_search_cache() -> None:
    """清空全部缓存（知识库内容变更时调用）。"""
    with _lock:
        _store.clear()
