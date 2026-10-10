"""方案 C 迁移不变量回归测试 — 学习单元长文与知识库卡片的单一真源。

锁死迁移后的数据形态，防止后续编辑卡片/单元时破坏对应关系：
- 每个带 unit_id 的卡片必须有 content_md（长文）
- 卡片上的 unit_id 必须对应真实存在的学习单元
- 迁移单元的正文必须来自卡片（而非占位/文件残留）
- 保留文件形态的单元必须仍有真实内容
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import get_settings  # noqa: E402
from app.knowledge.loader import KnowledgeBaseLoader  # noqa: E402
from app.learning.unit_content import ALL_MODELER  # noqa: E402

# 迁移时保留文件形态的 11 个单元（无对应卡片/practice 类/主题更宽）
KEPT_UNITS = {
    "modeler_lp_02", "modeler_ip_02", "modeler_heuristic_practice",
    "modeler_convex_opt", "modeler_reg_01", "modeler_rf_01",
    "modeler_ahp_02", "modeler_mle_01", "modeler_bayes_01",
    "modeler_game_01", "modeler_model_combo",
}


def _cards():
    loader = KnowledgeBaseLoader(get_settings().kb_root)
    return {c.id: c for c in loader.load_all_methods()}


def test_cards_with_unit_id_have_content():
    cards = _cards()
    linked = [(cid, c) for cid, c in cards.items() if c.unit_id]
    assert linked, "没有任何卡片带 unit_id——方案 C 迁移丢了？"
    for cid, card in linked:
        assert len(card.content_md) > 1000, f"{cid} 的 content_md 太短"


def test_card_unit_ids_map_to_real_units():
    cards = _cards()
    unit_ids = {u.unit_id for u in ALL_MODELER}
    for cid, card in cards.items():
        if card.unit_id:
            assert card.unit_id in unit_ids, f"{cid} 指向不存在的单元 {card.unit_id}"


def test_migrated_units_serve_card_content():
    """迁移单元的正文必须与卡片 content_md 一致（读取路径正确）。"""
    cards = _cards()
    by_unit = {c.unit_id: c for c in cards.values() if c.unit_id}
    assert by_unit, "没有迁移的单元"
    units = {u.unit_id: u for u in ALL_MODELER}
    for uid, card in by_unit.items():
        unit = units[uid]
        assert unit.content_md == card.content_md, f"单元 {uid} 正文与卡片不一致"
        assert not unit.content_md.startswith(f"# {uid}"), f"单元 {uid} 是占位内容"


def test_kept_units_still_have_real_content():
    units = {u.unit_id: u for u in ALL_MODELER}
    for uid in KEPT_UNITS:
        unit = units[uid]
        assert len(unit.content_md) > 200, f"保留单元 {uid} 内容异常（{len(unit.content_md)} chars）"
        assert not unit.content_md.startswith(f"# {uid}\n\n学习资料正在准备中"), (
            f"保留单元 {uid} 是占位内容"
        )


def test_no_unit_id_collision():
    """一个单元只能挂到一张卡片（一对一是映射的前提）。"""
    cards = _cards()
    seen: dict[str, str] = {}
    for cid, card in cards.items():
        if card.unit_id:
            assert card.unit_id not in seen, (
                f"单元 {card.unit_id} 同时挂在 {seen[card.unit_id]} 和 {cid}"
            )
            seen[card.unit_id] = cid


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
