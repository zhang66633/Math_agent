"""知识库 YAML 文件系统助手 — loader/embedder 获取、ID 分配、按 id 定位文件。

从 api/knowledge_shared.py 提到 knowledge/ 层：services（如 knowledge_ingest）
需要这些助手，而不应反向 import api 模块。knowledge_shared 保留再导出供路由使用。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..config import get_settings


def _get_loader():
    settings = get_settings()
    from ..knowledge.loader import KnowledgeBaseLoader

    return KnowledgeBaseLoader(settings.kb_root)


def _get_embedder(user_id: str | None = None):
    settings = get_settings()
    from ..knowledge.embedder import KBEmbedder

    return KBEmbedder(
        kb_root=settings.kb_root,
        persist_dir=settings.chroma_dir,
        user_id=user_id,
    )


def _find_yaml_file(kb_type: str, entry_id: str) -> Path | None:
    """Scan knowledge_base/{subdir}/**/*.yaml for the file with matching id."""
    settings = get_settings()
    subdir_map = {
        "method": "methods",
        "paper": "papers",
        "template": "templates",
        "problem": "problems",
    }
    key_map = {
        "method": "method_card",
        "paper": "paper",
        "template": "template",
        "problem": "problem",
    }
    subdir = subdir_map.get(kb_type, kb_type)
    top_key = key_map.get(kb_type, "")
    search_dir = settings.kb_root / subdir
    if not search_dir.exists():
        return None
    for yf in search_dir.rglob("*.yaml"):
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
            if data and top_key in data and isinstance(data[top_key], dict):
                if data[top_key].get("id") == entry_id:
                    return yf
        except Exception:
            continue
    return None


def _next_id(kb_type: str) -> str:
    """Auto-generate the next sequential ID."""
    settings = get_settings()
    subdir_map = {
        "method": "methods",
        "paper": "papers",
        "template": "templates",
        "problem": "problems",
    }
    prefix_map = {
        "method": "mc_",
        "paper": "paper_",
        "template": "tpl_",
        "problem": "prob_",
    }
    subdir = subdir_map.get(kb_type, kb_type)
    prefix = prefix_map.get(kb_type, "id_")
    search_dir = settings.kb_root / subdir
    existing: list[int] = []
    if search_dir.exists():
        for yf in search_dir.rglob("*.yaml"):
            try:
                data = yaml.safe_load(yf.read_text(encoding="utf-8"))
                if not data:
                    continue
                key_map = {
                    "method": "method_card",
                    "paper": "paper",
                    "template": "template",
                    "problem": "problem",
                }
                top_key = key_map.get(kb_type, "")
                if top_key in data and isinstance(data[top_key], dict):
                    rid = data[top_key].get("id", "")
                    m = re.match(rf"^{re.escape(prefix)}(\d+)$", rid)
                    if m:
                        existing.append(int(m.group(1)))
            except Exception:
                continue
    val = max(existing) + 1 if existing else 1
    return f"{prefix}{val:03d}"
