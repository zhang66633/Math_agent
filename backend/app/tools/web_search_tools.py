"""Web 搜索工具 — 多后端，优先国内可达通道。

**为什么要改**：原实现只依赖 `duckduckgo-search`。实测（2026-10-13）该包已改名 `ddgs`，
且在本机网络下三个后端全部不可达（bing 返回 None、startpage / yahoo 连接超时 20s+），
联网搜索实际处于「必失败」状态，而 agent 只会看到一句笼统的「搜索失败」。

现在的顺序（先国内、后境外，任一个成功即返回）：

1. `cn.bing.com` —— 实测 0.4s 可达，HTML 结构稳定，作为主通道；
2. `www.so.com`（360）—— 实测 1.3s 可达，作为备用通道；
3. `ddgs` —— 境外服务，网络允许时提供更好的结果质量（可选依赖）。

全部失败时返回**可操作的降级提示**（建议改用平台知识库），而不是一句无信息量的失败。
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar
from urllib.parse import urlencode

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TIMEOUT = 12


class WebSearchInput(BaseModel):
    query: str = Field(
        description=(
            "搜索关键词。尽量具体，如'粒子群算法 数学建模 应用案例'、"
            "'2024 美赛 O 题 优秀论文'、'Python 时间序列预测 ARIMA 教程'。"
            "中英文均可。"
        )
    )
    max_results: int = Field(
        default=5,
        description="返回结果数量（1-10），默认 5。",
        ge=1,
        le=10,
    )


def _http_get(url: str, params: dict, timeout: int = _TIMEOUT) -> str:
    import urllib.request

    req = urllib.request.Request(
        f"{url}?{urlencode(params)}",
        headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — 仅访问固定搜索引擎
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, "replace")


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", text).replace("&nbsp;", " ").strip()


def search_bing_cn(query: str, limit: int) -> list[dict]:
    """主通道：cn.bing.com 结果页解析（结构：li.b_algo → h2>a[href] + p 摘要）。"""
    html = _http_get("https://cn.bing.com/search", {"q": query, "ensearch": "0"})
    items: list[dict] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', html, re.DOTALL):
        m = re.search(
            r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL
        )
        if not m:
            continue
        url, title = m.group(1), _strip_tags(m.group(2))
        if not url.startswith("http") or not title:
            continue
        body_m = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        items.append(
            {"title": title, "href": url, "body": _strip_tags(body_m.group(1)) if body_m else ""}
        )
        if len(items) >= limit:
            break
    return items


def search_360(query: str, limit: int) -> list[dict]:
    """备用通道：360 搜索（结果块结构：h3 > a[href]）。"""
    html = _http_get("https://www.so.com/s", {"q": query})
    items: list[dict] = []
    for m in re.finditer(
        r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL
    ):
        url, title = m.group(1), _strip_tags(m.group(2))
        if not url.startswith("http") or not title:
            continue
        items.append({"title": title, "href": url, "body": ""})
        if len(items) >= limit:
            break
    return items


def search_ddgs(query: str, limit: int) -> list[dict]:
    """可选通道：ddgs（境外服务，网络允许时结果质量更好）。"""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS  # type: ignore[no-redef]

    with DDGS() as ddgs:
        rows = list(ddgs.text(query, max_results=limit))
    return [
        {
            "title": r.get("title", ""),
            "href": r.get("href", ""),
            "body": r.get("body", ""),
        }
        for r in rows
    ]


class WebSearchTool(BaseTool):
    """搜索互联网获取最新信息、案例、论文和教程。"""

    name: ClassVar[str] = "web_search"
    description: ClassVar[str] = (
        "搜索互联网获取最新信息。适用场景：\n"
        "- 查找数学建模竞赛真题、优秀论文、获奖作品\n"
        "- 查找算法/方法的最新应用案例和教程\n"
        "- 查找特定数据集、开源工具、Python 库用法\n"
        "- 验证某个方法或公式的正确性\n"
        "返回标题、摘要和链接。注意：搜索结果可能包含过时或不准确信息，需甄别；"
        "若返回不可用提示，请改用平台知识库检索。"
    )
    args_schema: type[BaseModel] = WebSearchInput

    def _run(
        self,
        query: str,
        max_results: int = 5,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        attempts: list[str] = []
        # 国内可达通道优先：境外后端在受限网络下要等 20s+ 超时，会拖死整个回合
        for name, fetcher in (("bing-cn", search_bing_cn), ("360", search_360)):
            try:
                rows = fetcher(query, max_results)
                if rows:
                    return self._format(query, rows, name)
                attempts.append(f"{name}: 无结果")
            except Exception as exc:  # noqa: BLE001
                attempts.append(f"{name}: {type(exc).__name__}: {str(exc)[:80]}")
                logger.warning("搜索后端 %s 失败: %s", name, exc)

        try:
            rows = search_ddgs(query, max_results)
            if rows:
                return self._format(query, rows, "ddgs")
            attempts.append("ddgs: 无结果")
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"ddgs: {type(exc).__name__}: {str(exc)[:80]}")

        return (
            f"联网搜索当前不可用（已尝试 {len(attempts)} 个后端）：\n"
            + "\n".join(f"- {a}" for a in attempts)
            + "\n\n建议：改用平台知识库检索（kab_search / 知识库页面），"
            "其中的方法卡、优秀论文与真题已经过结构化整理。"
        )

    @staticmethod
    def _format(query: str, rows: list[dict], backend: str) -> str:
        parts = [f"搜索 '{query}' 找到 {len(rows)} 条结果（来源: {backend}）：\n"]
        for i, r in enumerate(rows, 1):
            title = r.get("title") or "无标题"
            body = (r.get("body") or "").strip() or "（无摘要）"
            parts.append(f"{i}. **{title}**\n   {body[:300]}\n   链接: {r.get('href', '')}")
        return "\n\n".join(parts)


def create_web_search_tools() -> list:
    """创建 Web 搜索工具列表。"""
    return [WebSearchTool()]
