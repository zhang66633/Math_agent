"""学习路径数据/逻辑拆分不变量测试(god-files 拆分 #31 + 内容文件化)。

运行: 在 backend/ 目录下 `python -m pytest tests/test_path_generator.py -q`
      或直接 `python tests/test_path_generator.py`。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.learning.path_generator import generate_learning_path, get_unit_detail  # noqa: E402
from app.learning.unit_content import ALL_MODELER, ALL_UNITS, CONTENT_DIR  # noqa: E402


def test_all_roles_have_units():
    for role in ("modeler", "programmer", "writer"):
        assert len(ALL_UNITS[role]) > 0, f"{role} 角色应有学习单元"


def test_every_unit_has_content():
    """每个单元都必须有正文——方案 C 后来源有二：卡片 content_md（已迁移）
    或 content/<role>/<unit_id>.md（保留文件形态的单元）。"""
    from app.learning.unit_content import _card_content_by_unit

    card_content = _card_content_by_unit()
    for role, units in ALL_UNITS.items():
        for u in units:
            has_file = (CONTENT_DIR / role / f"{u.unit_id}.md").exists()
            has_card = u.unit_id in card_content
            assert has_file or has_card, f"{u.unit_id} 既无内容文件也无卡片长文"


def test_unit_content_rich():
    """单元正文（无论来自卡片还是文件）应足够丰富，不得是占位文本。"""
    for role_units in ALL_UNITS.values():
        for u in role_units:
            assert len(u.content_md) >= 1000, f"{u.unit_id} 内容过于单薄({len(u.content_md)} 字符)"
            assert "内容正在编写中" not in u.content_md, f"{u.unit_id} 仍是占位内容"
            assert "学习资料正在准备中" not in u.content_md, f"{u.unit_id} 仍是占位内容"


def test_unit_content_backed():
    # 每个单元的 content_md 应从文件加载且非空
    for role_units in ALL_UNITS.values():
        for u in role_units:
            assert u.content_md and len(u.content_md) > 100, f"{u.unit_id} 内容为空"


def test_generate_and_lookup():
    p = generate_learning_path()
    assert len(p.phases) > 0
    total = sum(len(ph.units) for ph in p.phases)
    assert total >= len(ALL_MODELER) * 0.9, "默认路径应展示建模手绝大多数单元"
    u = get_unit_detail("modeler_lp_01")
    assert u is not None and u.title
    assert get_unit_detail("不存在的单元") is None


if __name__ == "__main__":
    test_all_roles_have_units()
    test_every_unit_has_content()
    test_unit_content_rich()
    test_unit_content_backed()
    test_generate_and_lookup()
    print("ALL TESTS PASSED")
