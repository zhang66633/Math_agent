"""知识库详情接口契约回归测试（审计 2026-10-14 P0）。

背景：
    YAML 里 formulas / common_mistakes / code_snippets 允许两种历史格式——
    结构化对象（{name, latex, description}）与纯字符串（"0-1背包: dp[i][w] = ..."）。
    加载器 knowledge/schemas.py 的 MethodCard 两种都收，而 API 响应模型
    MethodCardDetail 只收 list[dict]。修复前 get_method 直接
    MethodCardDetail(**card.model_dump())，字符串条目触发 pydantic
    ValidationError → 22/86 张卡片详情接口 500；前端编辑保存还会顺着这条
    失败路径把整张卡的公式/错误/代码抹成空（PUT 用表单整体覆写 YAML 真源）。

    上一轮全量测试报告称「方法卡详情全部 200」——只抽到了未受影响的卡片。
    所以本文件的核心用例是**全量枚举**：86 张卡片逐一构造响应模型 + 逐一打
    HTTP，不允许再靠抽样过关。

运行: 在 backend/ 目录下 `python -m pytest tests/test_kb_detail_contract.py -q`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.knowledge_shared import method_card_detail, normalize_entries  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.knowledge.loader import KnowledgeBaseLoader  # noqa: E402
from app.main import app  # noqa: E402


def _cards():
    return KnowledgeBaseLoader(get_settings().kb_root).load_all_methods()


# ── 归一化单元测试 ──────────────────────────────────────────


def test_normalize_entries_string_is_lossless():
    """字符串条目必须整体进主字段，不丢内容、不乱拆。"""
    out = normalize_entries(["0-1背包: dp[i][w] = max(...)"], "latex", ("name", "description"))
    assert out == [{"name": "", "latex": "0-1背包: dp[i][w] = max(...)", "description": ""}]


def test_normalize_entries_dict_passthrough_with_defaults():
    out = normalize_entries(
        [{"name": "目标函数", "latex": "\\min Z"}], "latex", ("name", "description")
    )
    assert out == [{"name": "目标函数", "latex": "\\min Z", "description": ""}]


def test_normalize_entries_mixed_and_empty():
    out = normalize_entries([{"latex": "x"}, "plain", None], "latex", ())
    assert out == [{"latex": "x"}, {"latex": "plain"}, {"latex": ""}]


# ── 全量枚举：响应模型可序列化 ─────────────────────────────


def test_every_method_card_builds_response_model():
    """86/86 张卡片都必须能构造 MethodCardDetail——修复前 22 张抛 ValidationError。"""
    cards = _cards()
    assert cards, "知识库里一张方法卡都没有——测试前提不成立"
    failures = []
    for c in cards:
        try:
            detail = method_card_detail(c)
            # 三个易漂移字段必须是 list[dict]，且条目数不得少于原始条目数
            for field in ("formulas", "common_mistakes", "code_snippets"):
                raw = getattr(c, field)
                got = getattr(detail, field)
                assert len(got) == len(raw), f"{c.id}.{field} 条目数变了"
                assert all(isinstance(x, dict) for x in got), f"{c.id}.{field} 含非 dict"
        except Exception as e:  # noqa: BLE001
            failures.append(f"{c.id}: {type(e).__name__}: {e}")
    assert not failures, "以下卡片无法构造响应模型:\n" + "\n".join(failures)


def test_string_entries_land_in_main_field():
    """抽一张已知含字符串的卡片，确认内容进了主字段（前端 ArrayEditor 能显示）。"""
    dp = next((c for c in _cards() if c.id == "mc_007"), None)
    assert dp is not None, "mc_007（动态规划）不存在——测试前提不成立"
    detail = method_card_detail(dp)
    assert detail.formulas and detail.formulas[0]["latex"].startswith("0-1背包")
    assert detail.common_mistakes and "重叠子问题" in detail.common_mistakes[0]["mistake"]
    assert detail.code_snippets and "knapsack" in detail.code_snippets[0]["code"]


# ── 全量枚举：HTTP 层 200 ───────────────────────────────────


def test_every_method_card_detail_endpoint_returns_200():
    """逐一打 GET /api/knowledge/methods/{id}，86/86 必须 200（修复前 22 个 500）。"""
    cards = _cards()
    bad = []
    with TestClient(app) as client:
        for c in cards:
            r = client.get(f"/api/knowledge/methods/{c.id}")
            if r.status_code != 200:
                bad.append(f"{c.id} -> {r.status_code}")
    assert not bad, "详情接口非 200:\n" + "\n".join(bad)


def test_unknown_method_card_still_404():
    with TestClient(app) as client:
        assert client.get("/api/knowledge/methods/mc_nope").status_code == 404
