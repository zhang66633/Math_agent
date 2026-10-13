"""知识库完整性测试（审计 2026-10 深度审计固化）。

把一次性审计脚本的判定固化成 CI 不变量，防止数据腐化。分两类：

**硬不变量（必须为零，否则 FAIL）**
  - 每个 YAML 都能按 app.knowledge.schemas 的 Pydantic 模型校验通过
  - ID 全局唯一，且符合各自 pattern
  - 无悬空引用：related_cards / related_papers / linked_papers 都指向真实数据
  - problem_ref 使用 `prob_XXX` 约定（extractor prompt 与 ingest 代码的唯一口径），
    且能解析到真实题目
  - 方法卡名称不重复（重名会稀释检索结果）
  - LaTeX 括号成对、\\begin/\\end 环境匹配
  - 无乱码（U+FFFD / UTF-8 被按 GBK 读坏的痕迹）

**基线棘轮（只允许减少，不允许增加）**
  内容字段缺口（typical_scenarios / applicable_when / formulas / code_snippets）与
  文件名—ID 不对应属于既有数据债，用 baseline 锁住「不继续恶化」，补一个降一格。

运行: 在 backend/ 目录下 `python -m pytest tests/test_kb_integrity.py -q`
"""

import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge.schemas import (  # noqa: E402
    MethodCard,
    Paper,
    Problem,
    Template,
)

KB_ROOT = Path(__file__).resolve().parent.parent / "knowledge_base"

# ── 基线棘轮：当前实测值（2026-10 深度审计，86 张方法卡）。补全内容后应主动下调。──
# 2026-10-13 已用 scripts/fill_method_card_gaps.py 全部补齐（LLM 生成 + mc_037 手写），
# 四项缺口均已归零，故基线设 0——今后任何一张卡再缺字段都会直接失败。
BASELINE_MISSING_SCENARIOS = 0
BASELINE_MISSING_APPLICABLE = 0
BASELINE_MISSING_FORMULAS = 0
BASELINE_MISSING_CODE = 0
BASELINE_FILENAME_MISMATCH = 26
# 重名方法卡对数（5 对 = 10 个文件）。合并后下调。
BASELINE_DUPLICATE_NAMES = 0

_MOJIBAKE_MARKERS = ("锟斤拷", "å", "ã")


def _kb_files(subdir: str):
    """列出某类知识的 YAML 文件。

    目录不存在时直接抛错而不是返回空列表——空列表会让所有「无失败即通过」的
    断言变成空转（实测踩过：KB_ROOT 多上一级，10 个测试全绿但一个文件都没读）。
    """
    base = KB_ROOT / subdir
    if not base.is_dir():
        raise AssertionError(f"知识库目录不存在: {base}（KB_ROOT={KB_ROOT}）")
    return [
        f
        for f in sorted(base.rglob("*.yaml"))
        if "_source_skill_docs" not in str(f)
        and "_import_queue" not in str(f)
        and not f.name.startswith("_")
    ]


def _load(subdir: str, root_key: str):
    """返回 [(relpath, raw_dict, pydantic_obj_or_None, error_or_None)]"""
    out = []
    for f in _kb_files(subdir):
        rel = f.relative_to(KB_ROOT).as_posix()
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            out.append((rel, None, None, f"YAML 解析失败: {e}"))
            continue
        if not isinstance(data, dict) or root_key not in data:
            out.append((rel, data, None, f"缺少 {root_key} 根键"))
            continue
        model = {"method_card": MethodCard, "paper": Paper, "template": Template, "problem": Problem}[
            root_key
        ]
        try:
            out.append((rel, data, model(**(data[root_key] or {})), None))
        except Exception as e:  # noqa: BLE001
            out.append((rel, data, None, f"{model.__name__} 校验失败: {str(e)[:200]}"))
    return out


# ── 硬不变量 ───────────────────────────────────────────


def test_all_yaml_validate_against_schemas():
    """L1：结构完整性。这是最基础的一条——字段类型/范围/ID 格式全在这里兜底。"""
    failures = []
    for subdir, key in (
        ("methods", "method_card"),
        ("papers", "paper"),
        ("templates", "template"),
        ("problems", "problem"),
    ):
        for rel, _data, _obj, err in _load(subdir, key):
            if err:
                failures.append(f"{rel}: {err}")
    assert not failures, "以下知识库文件未通过 schema 校验:\n" + "\n".join(failures)


def test_ids_are_unique_and_match_pattern():
    """ID 唯一 + 符合 pattern（MethodCard 要求 mc_\\d+，Problem 要求 prob_\\d+）。"""
    seen: dict[str, list[str]] = defaultdict(list)
    for subdir, key, pattern in (
        ("methods", "method_card", r"^mc_\d+$"),
        ("papers", "paper", r"^paper_.+$"),
        ("problems", "problem", r"^prob_\d+$"),
        ("templates", "template", r"^tpl_.+$"),
    ):
        for rel, _data, obj, err in _load(subdir, key):
            if err:
                continue
            seen[obj.id].append(rel)
            assert re.match(pattern, obj.id), f"{rel}: id {obj.id!r} 不符合 {pattern}"
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dups, f"重复 ID: {dups}"


def test_no_dangling_cross_references():
    """L2：related_cards / related_papers / linked_papers 不得指向不存在的数据。"""
    method_ids = {o.id for _, _, o, e in _load("methods", "method_card") if not e}
    paper_ids = {o.id for _, _, o, e in _load("papers", "paper") if not e}

    dangling = []
    for rel, _d, card, err in _load("methods", "method_card"):
        if err:
            continue
        for rc in card.related_cards:
            if rc not in method_ids:
                dangling.append(f"{rel}: related_cards → {rc}")
        for rp in card.related_papers:
            if rp not in paper_ids:
                dangling.append(f"{rel}: related_papers → {rp}")
    for rel, _d, prob, err in _load("problems", "problem"):
        if err:
            continue
        for lp in prob.linked_papers:
            if lp not in paper_ids:
                dangling.append(f"{rel}: linked_papers → {lp}")
    assert not dangling, "悬空引用:\n" + "\n".join(dangling)


def test_problem_ref_uses_documented_convention():
    """problem_ref 必须是 prob_XXX 且能解析到真实题目。

    唯一口径来源：kb_extractor 的 prompt 明写「填写对应的 prob_ 编号（如 prob_001）」，
    knowledge_ingest 也把它当 problem id 用。曾有一篇写成 '2023C'，导致
    get_papers_by_problem() 精确匹配查不到、linked_papers 也写成悬空的 paper_2023C_01。
    """
    problem_ids = {o.id for _, _, o, e in _load("problems", "problem") if not e}
    bad = []
    for rel, _d, paper, err in _load("papers", "paper"):
        if err or not paper.problem_ref:
            continue
        ref = paper.problem_ref.strip()
        if not re.fullmatch(r"prob_\d+", ref):
            bad.append(f"{rel}: problem_ref={ref!r} 不是 prob_XXX 形式")
        elif ref not in problem_ids:
            bad.append(f"{rel}: problem_ref={ref!r} 在题库中不存在")
    assert not bad, "problem_ref 约定违规:\n" + "\n".join(bad)


def test_duplicate_method_names_do_not_regress():
    """重名卡片必须为零——2026-10 已合并 5 对（86 → 81 张卡）。

    重名会让同一方法在检索结果里出现两遍、稀释 k 个名额。合并时保留内容更丰富的
    一份，并把 unit_id/content_md 等独有字段迁过去（见 scripts/merge_duplicate_method_cards.py）。
    """
    names: dict[str, list[str]] = defaultdict(list)
    for rel, _d, card, err in _load("methods", "method_card"):
        if err:
            continue
        names[card.name.strip().lower()].append(rel)
    dups = {k: v for k, v in names.items() if len(v) > 1}
    assert not dups, f"方法卡重名（需按 scripts/merge_duplicate_method_cards.py 合并）:\n{dups}"


def test_no_duplicate_principle_text():
    """归一化后 principle 完全相同 → 内容重复。"""
    import hashlib

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s or "")
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"[，。、；：？！,.;:?!\-—\(\)（）\[\]【】]", "", s)
        return s.lower()

    buckets: dict[str, list[str]] = defaultdict(list)
    for rel, _d, card, err in _load("methods", "method_card"):
        if err:
            continue
        buckets[hashlib.md5(norm(card.principle).encode()).hexdigest()].append(rel)
    dups = {k: v for k, v in buckets.items() if len(v) > 1}
    assert not dups, f"principle 完全重复: {dups}"


def test_latex_is_balanced():
    """$ 必须成对；\\begin/\\end 环境必须匹配。"""
    problems = []

    def check(text: str, where: str):
        if not text or "$" not in text:
            return
        if text.count("$") % 2:
            problems.append(f"{where}: $ 奇数个（{text.count('$')}）")
        b = Counter(re.findall(r"\\begin\{([^}]+)\}", text))
        e = Counter(re.findall(r"\\end\{([^}]+)\}", text))
        for env, n in b.items():
            if e.get(env, 0) != n:
                problems.append(f"{where}: {env} begin={n} end={e.get(env, 0)}")

    for rel, _d, card, err in _load("methods", "method_card"):
        if err:
            continue
        for fl in card.formulas:
            check(fl if isinstance(fl, str) else fl.latex, f"{rel} formulas")
    for rel, _d, paper, err in _load("papers", "paper"):
        if err:
            continue
        for fl in paper.key_formulas:
            check(fl.latex, f"{rel} key_formulas")
    assert not problems, "LaTeX 不配平:\n" + "\n".join(problems)


def test_no_mojibake():
    """U+FFFD 与 UTF-8 被按 GBK 读坏的典型痕迹。"""
    bad = []

    def check(text: str, where: str):
        if not text:
            return
        if "\ufffd" in text:
            bad.append(f"{where}: 含 U+FFFD")
        for m in _MOJIBAKE_MARKERS:
            if m in text:
                bad.append(f"{where}: 乱码片段 {m!r}")
                break

    for rel, _d, card, err in _load("methods", "method_card"):
        if err:
            continue
        check(card.principle, f"{rel} principle")
        check(card.name, f"{rel} name")
    for rel, _d, paper, err in _load("papers", "paper"):
        if err:
            continue
        check(paper.title, f"{rel} title")
    assert not bad, "疑似编码损坏:\n" + "\n".join(bad)


# ── 基线棘轮 ───────────────────────────────────────────


def _missing_field_counts():
    sc = ap = fm = cd = 0
    for _rel, _d, card, err in _load("methods", "method_card"):
        if err:
            continue
        sc += not card.typical_scenarios
        ap += not card.applicable_when
        fm += not card.formulas
        cd += not card.code_snippets
    return sc, ap, fm, cd


def test_content_gaps_do_not_regress():
    """四项核心内容字段必须全部非空——2026-10 已补齐，基线为 0。

    曾缺口 32/31/33/2（typical_scenarios / applicable_when / formulas / code_snippets），
    用 scripts/fill_method_card_gaps.py 经 LLM 补齐（mc_037 的代码示例为手写，
    因 LLM 认为仅凭原理无法合理推断——这个「不硬编」的判断是对的）。
    """
    sc, ap, fm, cd = _missing_field_counts()
    msgs = []
    if sc > BASELINE_MISSING_SCENARIOS:
        msgs.append(f"缺 typical_scenarios: {sc} > 基线 {BASELINE_MISSING_SCENARIOS}")
    if ap > BASELINE_MISSING_APPLICABLE:
        msgs.append(f"缺 applicable_when: {ap} > 基线 {BASELINE_MISSING_APPLICABLE}")
    if fm > BASELINE_MISSING_FORMULAS:
        msgs.append(f"缺 formulas: {fm} > 基线 {BASELINE_MISSING_FORMULAS}")
    if cd > BASELINE_MISSING_CODE:
        msgs.append(f"缺 code_snippets: {cd} > 基线 {BASELINE_MISSING_CODE}")
    assert not msgs, "内容字段又出现缺口:\n" + "\n".join(msgs)


def test_filename_id_mismatch_does_not_regress():
    """文件名与 id/name 不对应只是观感问题，同样用棘轮锁住不恶化。"""
    mismatch = 0
    for f in _kb_files("methods"):
        rel = f.relative_to(KB_ROOT).as_posix()
        for r2, _d, card, err in _load("methods", "method_card"):
            if r2 != rel or err:
                continue
            if card.id not in f.name and card.name[:6] not in f.name:
                mismatch += 1
    assert mismatch <= BASELINE_FILENAME_MISMATCH, (
        f"文件名不对应从 {BASELINE_FILENAME_MISMATCH} 涨到 {mismatch}"
    )


def test_knowledge_base_is_not_empty():
    """防误删：四类数据的规模下限。

    2026-10 补入 2024 国赛 C、2025 国赛 C、2023 华数杯 C 后 problems 38 → 41；
    合并 5 对重名方法卡后 methods 86 → 81，下限随之上调。
    """
    assert len(_kb_files("methods")) >= 81, "方法卡片数量异常偏少"
    assert len(_kb_files("papers")) >= 30, "论文数量异常偏少"
    assert len(_kb_files("problems")) >= 41, "真题数量异常偏少"
    assert len(_kb_files("templates")) >= 3, "模板数量异常偏少"


def test_newest_problems_are_covered():
    """KB 真题必须覆盖到 2025——曾长期停在 2023（2026-10 补齐）。

    这不是「越多越好」的指标，而是防止再次出现「最新三年空缺」的腐化。
    """
    from app.knowledge.loader import KnowledgeBaseLoader

    probs = KnowledgeBaseLoader(KB_ROOT).load_all_problems()
    years = {p.year for p in probs}
    assert 2024 in years, "缺 2024 年真题"
    assert 2025 in years, "缺 2025 年真题"
    # 华数杯是独立赛事（中国未来研究会大数据与数学模型专业委员会主办），
    # 不应与国赛(CUMCM)混为一谈
    comps = {p.competition for p in probs}
    assert "华数杯" in comps, "缺华数杯赛题（2023 C 已入库）"
    assert "国赛" in comps


# ── 类别归一化（审计 2026-10）──────────────────────────

# 细分类别 → 必须同时出现的规范父类。与 scripts/_audit_category_migrate.py 同源。
_SYNONYM_TO_CANONICAL = {
    "优化算法": ["优化"], "数学规划": ["优化"], "启发式算法": ["优化"],
    "元启发式": ["优化"], "群体智能": ["优化"],
    "时间序列": ["预测"], "时间序列分析": ["预测"],
    "预测与分类": ["预测", "机器学习"],
    "统计": ["统计分析"], "信息论": ["统计分析"], "小样本": ["统计分析"],
    "数据降维": ["统计分析", "机器学习"],
    "图论与网络": ["图论"],
    "分类": ["机器学习"], "分类与聚类": ["机器学习"], "无监督学习": ["机器学习"],
    "评价决策": ["评价"], "综合评价": ["评价"], "多准则决策": ["评价"],
    "主观赋权": ["评价"], "客观赋权": ["评价"], "效率分析": ["评价"], "模糊数学": ["评价"],
    "随机模拟": ["随机过程"], "排队论": ["随机过程"],
}


def test_canonical_categories_cover_synonyms():
    """类别归一化棘轮：标了细分类别的卡必须同时带规范父类。

    为什么重要：loader.get_methods_by_category 与 knowledge_graph.get_nodes_by_category
    都是**精确匹配**，不同时带父类的话传「优化」找不到标「优化算法」的卡。
    """
    missing = []
    for rel, _d, card, err in _load("methods", "method_card"):
        if err:
            continue
        for c in card.category:
            for canon in _SYNONYM_TO_CANONICAL.get(c, []):
                if canon not in card.category:
                    missing.append(f"{rel}: 有 {c!r} 但缺 {canon!r}")
    assert not missing, "类别归一化回退:\n" + "\n".join(missing)


def test_get_methods_by_category_exact_match_works():
    """规范类别名必须能精确检索到对应卡片（归一化的实际收益）。"""
    from app.knowledge.loader import KnowledgeBaseLoader

    loader = KnowledgeBaseLoader(KB_ROOT)
    for canon in ("优化", "预测", "评价", "统计分析", "图论", "机器学习"):
        found = loader.get_methods_by_category(canon)
        assert found, f"get_methods_by_category({canon!r}) 返回空——精确匹配失效"
        # 每张命中的卡都得真的带这个类别
        assert all(canon in c.category for c in found)


def test_knowledge_graph_builds_non_empty():
    """技能树图谱不得为空。

    曾因 methods_path.glob("*.yaml") 非递归而一张卡都读不到——卡片全在
    methods/<类别>/ 子目录里，根目录下 0 个 yaml。该缺陷长期无人调用所以没暴露。
    """
    from app.learning.knowledge_graph import build_graph_from_method_cards

    # 参数名 kb_dir 有点误导：它实际是「知识库根」（函数内部拼 <kb_dir>/methods），
    # 即 backend/knowledge_base，不是 backend/。
    kb_dir = KB_ROOT
    assert (kb_dir / "methods").is_dir(), f"{kb_dir}/methods 不是目录"
    graph = build_graph_from_method_cards(str(kb_dir))
    assert graph.nodes, "知识图谱为空——glob 可能又变成了非递归"
    assert len(graph.nodes) == len(_kb_files("methods")), (
        f"节点数 {len(graph.nodes)} != 卡片数 {len(_kb_files('methods'))}"
    )
    assert graph.edges, "图谱没有任何边（related_cards 应产出横向关联）"

    # 难度不得全是 1：MethodCard.difficulty 是 int 1-5，_difficulty_from_tags 曾只认
    # 字符串，导致 int 全落进 mapping.get(d, 1) → 每张卡都显示「入门」。
    diffs = {n.difficulty for n in graph.nodes.values()}
    assert diffs != {1}, f"所有节点难度都是 1，难度映射可能又坏了: {sorted(diffs)}"
    assert all(1 <= d <= 3 for d in diffs), f"难度越界: {sorted(diffs)}"


if __name__ == "__main__":
    for _fn in [
        test_all_yaml_validate_against_schemas,
        test_ids_are_unique_and_match_pattern,
        test_no_dangling_cross_references,
        test_problem_ref_uses_documented_convention,
        test_duplicate_method_names_do_not_regress,
        test_no_duplicate_principle_text,
        test_latex_is_balanced,
        test_no_mojibake,
        test_content_gaps_do_not_regress,
        test_filename_id_mismatch_does_not_regress,
        test_knowledge_base_is_not_empty,
        test_newest_problems_are_covered,
        test_canonical_categories_cover_synonyms,
        test_get_methods_by_category_exact_match_works,
        test_knowledge_graph_builds_non_empty,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    print("ALL TESTS PASSED")
