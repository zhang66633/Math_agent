"""知识库检索工具集（LangChain BaseTool）。

供 chat/teach agent 通过 `llm.bind_tools()` 挂载，LLM 可自主决定何时调用。
检索结果通过 LangChain ToolMessage 反馈给 LLM，并行通过 SSE 推送给前端展示。

依赖入口：
    tools = create_kb_tools()  -> [search_method_cards, search_similar_papers, get_analysis_template]
    llm_with_tools = llm.bind_tools(tools)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from ..config import get_settings

logger = logging.getLogger(__name__)

_KB_ROOT: Path | None = None
_PERSIST_DIR: Path | None = None


def _resolve_kb_paths():
    """延迟解析 KB 路径，与 config 设置（settings.kb_root / chroma_dir）保持一致。

    注意：不能硬编码 data/knowledge_base —— 真实知识库在 settings.kb_root
    （默认 backend/knowledge_base），硬编码会导致在空目录上建检索器、
    搜索永远"未找到"。
    """
    global _KB_ROOT, _PERSIST_DIR
    if _KB_ROOT is None:
        settings = get_settings()
        _KB_ROOT = settings.kb_root
        _PERSIST_DIR = settings.chroma_dir
    return _KB_ROOT, _PERSIST_DIR


def get_retriever() -> BaseRetriever:
    """获取全局单例 retriever——与知识库 API 共用 knowledge.retriever.get_shared_retriever。

    历史教训：这里曾自建第二个 HybridRetriever 单例，invalidate_shared_retriever()
    只清知识库 API 那个。import/reindex/CRUD 后 chat/teach 工具路径的 BM25
    快照直到重启才可见新内容（正确性 bug），且双份索引 + 双份 Chroma 客户端
    白占内存与首调用延迟。两个入口必须同一个实例，失效逻辑才只有一处。
    """
    from ..knowledge.retriever import get_shared_retriever

    return get_shared_retriever()


def reset_retriever() -> None:
    """测试用：清空全局 retriever（含共享单例），下次重新加载。"""
    from ..knowledge.retriever import invalidate_shared_retriever

    invalidate_shared_retriever()


# ── Input Schemas ──────────────────────────────────────────────


class MethodSearchInput(BaseModel):
    query: str = Field(
        description="要搜索的关键词或问题描述，如 '线性规划求解' 或 '如何做层次分析'"
    )


class PaperSearchInput(BaseModel):
    query: str = Field(description="要搜索的论文主题或年份竞赛关键词，如 '2023 国赛 A 题'")


class TemplateSearchInput(BaseModel):
    query: str = Field(description="要搜索的模板/评价框架适用场景，如 '评价类问题模板'")


# ── Tool Implementations ───────────────────────────────────────


def _format_doc(d: Document, max_chars: int = 800) -> str:
    """截断 doc.page_content，给 LLM 简洁上下文。"""
    text = d.page_content or ""
    if len(text) > max_chars:
        text = text[:max_chars] + f"…(+{len(text) - max_chars} 字符)"
    return text


class SearchMethodCardsTool(BaseTool):
    name: ClassVar[str] = "search_method_cards"
    description: ClassVar[str] = (
        "搜索数学建模方法卡片（如线性规划、PSO、SVM、神经网络等）。"
        "当你需要介绍某类方法、判断方法适用场景、给出方法对比时调用。"
        "返回每张卡片的核心原理、公式、适用条件与典型场景摘要。"
    )
    args_schema: ClassVar[type[BaseModel]] = MethodSearchInput

    def _run(
        self,
        query: str,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        try:
            retriever = get_retriever()
            # 通过 invoke 的 metadata_filter 参数过滤（type 字段，方法卡片为 method_card）
            docs = retriever.invoke(query, metadata_filter={"type": "method_card"})
            if not docs:
                return "未找到相关方法卡片。"
            return "\n\n---\n\n".join(
                f"【{d.metadata.get('name', '未知方法')}】\n{_format_doc(d)}" for d in docs
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("search_method_cards failed")
            return f"工具执行失败: {e}"


class SearchSimilarPapersTool(BaseTool):
    name: ClassVar[str] = "search_similar_papers"
    description: ClassVar[str] = (
        "搜索数学建模竞赛真题与优秀论文（如国赛/美赛/华中赛等）。"
        "当你需要给出真实题目参考、论文结构示例、或历年案例时调用。"
        "返回题号、年份、问题摘要、方法概要与亮点摘要。"
    )
    args_schema: ClassVar[type[BaseModel]] = PaperSearchInput

    def _run(
        self,
        query: str,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        try:
            retriever = get_retriever()
            # 通过 invoke 的 metadata_filter 参数过滤（type 字段，论文/真题为 paper）
            docs = retriever.invoke(query, metadata_filter={"type": "paper"})
            if not docs:
                return "未找到相关论文/真题。"
            return "\n\n---\n\n".join(
                f"【{d.metadata.get('year', '?')} {d.metadata.get('competition', '')} "
                f"{d.metadata.get('problem_id', '')}】\n{_format_doc(d)}"
                for d in docs
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("search_similar_papers failed")
            return f"工具执行失败: {e}"


class GetAnalysisTemplateTool(BaseTool):
    name: ClassVar[str] = "get_analysis_template"
    description: ClassVar[str] = (
        "获取数学建模的解题模板/评价框架（如优化类/评价类/统计类问题的标准步骤）。"
        "当你需要给出解题思路框架、步骤清单、决策流程时调用。"
        "返回模板名、适用场景与标准步骤摘要。"
    )
    args_schema: ClassVar[type[BaseModel]] = TemplateSearchInput

    def _run(
        self,
        query: str,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        try:
            retriever = get_retriever()
            # 通过 invoke 的 metadata_filter 参数过滤（type 字段，模板为 template）。
            # 注意：不能用 search_kwargs —— 那是 VectorStoreRetriever 的字段，
            # 自定义 HybridRetriever（pydantic 模型）没有该字段，赋值会抛错。
            docs = retriever.invoke(query, metadata_filter={"type": "template"})
            if not docs:
                return "未找到相关模板。"
            return "\n\n---\n\n".join(
                f"【{d.metadata.get('name', '未知模板')}】\n{_format_doc(d)}" for d in docs
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("get_analysis_template failed")
            return f"工具执行失败: {e}"


def create_kb_tools() -> list[BaseTool]:
    """工厂：返回全部 KB 工具，供 llm.bind_tools() 使用。"""
    return [
        SearchMethodCardsTool(),
        SearchSimilarPapersTool(),
        GetAnalysisTemplateTool(),
    ]
