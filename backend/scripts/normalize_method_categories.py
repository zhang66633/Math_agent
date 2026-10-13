"""方法卡类别归一化（幂等，可重复运行）。

问题（审计 2026-10）：86 张卡用了 34 个不同 category 标签，其中大量是同义词：
  统计 / 统计分析、优化 / 优化算法 / 数学规划 / 启发式算法 / 元启发式 / 群体智能、
  图论 / 图论与网络、时间序列 / 时间序列分析、分类 / 分类与聚类 / 无监督学习、
  评价 / 评价决策 / 综合评价 / 多准则决策 / 主观赋权 / 客观赋权、预测 / 预测与分类 …
而消费方多处按**精确匹配**过滤：
  - loader.get_methods_by_category(category) → `category in card.category`
  - knowledge_graph.get_nodes_by_category(category) → `n.category == category`
于是传 "优化" 找不到标 "优化算法" 的卡，传 "统计" 找不到 "统计分析" 的卡。

策略：**只追加、不替换**。把规范父类加到 category 列表末尾。
  - 不丢信息：细分类别（如「启发式算法」）仍在列表里，前端展示与 cats[0] 不变
  - 精确匹配立即可用：传规范名能命中所有子类
  - knowledge_graph 的 category=cats[0] 行为完全不变（追加在末尾）
  - 检索侧：retriever 把 category join 进 embedding 文本，多一个正确的父类名有益无害

规范集取自 methods/ 的 11 个目录（项目自己对卡片的组织方式）：
  优化 预测 评价 统计分析 图论 微分方程 数值方法 机器学习 博弈论 随机过程 其他

用法：
    python scripts/normalize_method_categories.py          # dry-run，只看会改什么
    python scripts/normalize_method_categories.py --apply  # 实际改写

同源判定已固化到 tests/test_kb_integrity.py::test_canonical_categories_cover_synonyms，
新增卡片若只标了细分类别，该测试会直接失败提示。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from app.knowledge.schemas import MethodCard

KB = Path(__file__).resolve().parent.parent / "knowledge_base"

# 细分类别 → 规范父类（可一对多；追加而非替换）
SYNONYM_TO_CANONICAL = {
    # 优化家族
    "优化算法": ["优化"],
    "数学规划": ["优化"],
    "启发式算法": ["优化"],
    "元启发式": ["优化"],
    "群体智能": ["优化"],
    # 预测家族
    "时间序列": ["预测"],
    "时间序列分析": ["预测"],
    "预测与分类": ["预测", "机器学习"],
    # 统计家族
    "统计": ["统计分析"],
    "信息论": ["统计分析"],
    "小样本": ["统计分析"],
    "数据降维": ["统计分析", "机器学习"],
    # 图论家族
    "图论与网络": ["图论"],
    # 机器学习家族
    "分类": ["机器学习"],
    "分类与聚类": ["机器学习"],
    "无监督学习": ["机器学习"],
    # 评价家族
    "评价决策": ["评价"],
    "综合评价": ["评价"],
    "多准则决策": ["评价"],
    "主观赋权": ["评价"],
    "客观赋权": ["评价"],
    "效率分析": ["评价"],
    "模糊数学": ["评价"],
    # 随机过程家族
    "随机模拟": ["随机过程"],
    "排队论": ["随机过程"],
}

# 规范集（= methods/ 的 11 个目录名）
CANONICAL = {
    "优化", "预测", "评价", "统计分析", "图论", "微分方程",
    "数值方法", "机器学习", "博弈论", "随机过程", "其他",
}


def _append_category_lines(path: Path, additions: list[str]) -> None:
    """把规范父类追加到 YAML 的 category 块末尾——只插行，不动其他任何字节。

    为什么不能 yaml.safe_dump  round-trip：这些文件是手写的，principle 等长字段
    用带续行的双引号字符串，round-trip 会重新加引号/改折行，把可读性弄坏，
    还会抹掉注释。这里按行文本操作，保证 diff 只有新增的几行。
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    # 定位 method_card 下的 category: 键（缩进 2）
    key_idx = None
    for i, ln in enumerate(lines):
        if ln.rstrip("\n").rstrip() == "  category:":
            key_idx = i
            break
    if key_idx is None:
        raise RuntimeError(f"{path}: 找不到 '  category:' 键")

    # 收集其后连续的 '  - xxx' 条目，找到块尾
    end = key_idx + 1
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1

    insert_at = end
    # 若块为空（category: 后直接是下一个键），仍插在键后一行
    new_lines = lines[:insert_at] + [f"  - {a}\n" for a in additions] + lines[insert_at:]
    path.write_text("".join(new_lines), encoding="utf-8")


def main(apply: bool) -> int:
    changed = []
    unmatched = []
    for f in sorted((KB / "methods").rglob("*.yaml")):
        if "_source_skill_docs" in str(f) or f.name.startswith("_"):
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        raw = data.get("method_card")
        if not isinstance(raw, dict):
            continue
        card = MethodCard(**raw)
        cats = list(card.category)

        # 只归一化明确的同义词，不按目录名推断——目录名在这条链路上没有代码语义
        additions = []
        for c in cats:
            for canon in SYNONYM_TO_CANONICAL.get(c, []):
                if canon not in cats and canon not in additions:
                    additions.append(canon)

        if not additions:
            continue

        new_cats = cats + additions
        # 记录未被映射表覆盖、也不在规范集里的标签（供人工复核）
        for c in cats:
            if c not in CANONICAL and c not in SYNONYM_TO_CANONICAL:
                unmatched.append((f.name, c))

        changed.append((f, cats, new_cats))
        if apply:
            _append_category_lines(f, additions)

    print(f"{'已改写' if apply else '待改写'} {len(changed)} 个文件\n")
    for f, old, new in changed:
        print(f"  {f.parent.name}/{f.name}")
        print(f"      {old}  →  {new}")

    if unmatched:
        print(f"\n未映射标签 {len(unmatched)} 个（请人工确认）：")
        for fn, c in unmatched:
            print(f"    {fn}: {c}")

    return len(changed)


if __name__ == "__main__":
    main("--apply" in sys.argv)
