"""合并 5 对重名方法卡（幂等；默认 dry-run，--apply 才落地）。

保留策略（依据 2026-10 审计的逐字段对比）：
  模拟退火   保留 mc_006（principle 445>146、mistakes 5>3、有 tags 与 3 个 related_cards），
             迁入 mc_040 的 unit_id + content_md（7390 字学习长文，删了会断学习单元）
  变分法     保留 mc_091（principle 257>209、formulas 10>4），迁入 mc_035 的 code_snippets
  零和对策   保留 mc_092（formulas 5>4、mistakes 3>2），迁入 mc_028 独有的 typical_scenarios
  马尔可夫链 保留 mc_096（每一项都更丰富），无需迁入
  灰色关联   保留 mc_097（principle 242>158、formulas 5>2），迁入 mc_045 的 unit_id + content_md

为什么保留 mc_006 特别重要：它是唯一被其他卡片引用的（mc_003/mc_001/mc_020/mc_011 的
related_cards 都指向它），保留它就完全不需要改任何交叉引用。

写入一律用行级外科插入，不用 yaml.safe_dump round-trip——那会重排手写的长引号
principle 并抹掉注释。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from app.knowledge.schemas import MethodCard

KB = Path(__file__).resolve().parent.parent / "knowledge_base"
METHODS = KB / "methods"

# (保留, 删除, 要从删除者迁入的字段)
PLAN = [
    ("mc_006", "mc_040", ["unit_id", "content_md"]),
    ("mc_091", "mc_035", ["code_snippets"]),
    ("mc_092", "mc_028", ["typical_scenarios_dedup"]),
    ("mc_096", "mc_034", []),
    ("mc_097", "mc_045", ["unit_id", "content_md"]),
]


def card_file(cid: str) -> Path:
    for f in sorted(METHODS.rglob("*.yaml")):
        if "_source_skill_docs" in str(f) or f.name.startswith("_"):
            continue
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("method_card", {}).get("id") == cid:
            return f
    raise KeyError(cid)


def load(cid: str) -> MethodCard:
    return MethodCard(
        **(yaml.safe_load(card_file(cid).read_text(encoding="utf-8"))["method_card"])
    )


# ── 行级外科写入 ───────────────────────────────────────


def _find_key_line(lines: list[str], key: str) -> int:
    for i, ln in enumerate(lines):
        if ln.rstrip() == f"  {key}:":
            return i
    return -1


def _block_end(lines: list[str], start: int) -> int:
    """从 key 行之后，连续的 '  - ' 条目的结束位置（不含）。"""
    end = start + 1
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1
    return end


def append_list_items(path: Path, key: str, items: list[str]) -> None:
    """往已存在的块列表末尾追加字符串条目。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    ki = _find_key_line(lines, key)
    if ki < 0:
        raise RuntimeError(f"{path.name}: 找不到 {key} 块")
    end = _block_end(lines, ki)
    lines[end:end] = [f"  - {it}\n" for it in items]
    path.write_text("".join(lines), encoding="utf-8")


def replace_inline_empty_list(path: Path, key: str, items: list[dict]) -> None:
    """把 `  key: []` 展开成块列表（items 为 dict，按 YAML 映射序列写）。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.rstrip() == f"  {key}: []":
            dumped = yaml.safe_dump(items, allow_unicode=True, sort_keys=False, width=100)
            # safe_dump 产出顶层序列；改成缩进 2 的子条目
            body = "".join(
                ("  " + line if line.strip() else line)
                for line in dumped.splitlines(keepends=True)
            )
            lines[i] = f"  {key}:\n" + body
            path.write_text("".join(lines), encoding="utf-8")
            return
    raise RuntimeError(f"{path.name}: 找不到 {key}: []")


def append_scalar_and_block(path: Path, unit_id: str, content_md: str) -> None:
    """在文件末尾追加 unit_id 标量与 content_md 块标量。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.append(f"  unit_id: {unit_id}\n")
    lines.append("  content_md: |\n")
    for ln in content_md.splitlines():
        lines.append(("    " + ln if ln.strip() else "") + "\n")
    path.write_text("".join(lines), encoding="utf-8")


# ── 主流程 ─────────────────────────────────────────────


def main(apply: bool) -> None:
    total_ops = 0
    for keep_id, drop_id, fields in PLAN:
        keep_f, drop_f = card_file(keep_id), card_file(drop_id)
        keep, drop = load(keep_id), load(drop_id)
        print("=" * 74)
        print(f"### {keep.name}：保留 {keep_id}（{keep_f.name}）  删除 {drop_id}（{drop_f.name}）")
        print("=" * 74)

        ops = []
        if "unit_id" in fields and drop.unit_id:
            ops.append(f"迁入 unit_id={drop.unit_id!r} + content_md（{len(drop.content_md)} 字）")
        if "code_snippets" in fields and drop.code_snippets:
            ops.append(f"迁入 code_snippets（{len(drop.code_snippets)} 段）")
        if "typical_scenarios_dedup" in fields:
            uniq = [s for s in drop.typical_scenarios if s not in keep.typical_scenarios]
            ops.append(f"迁入独有 typical_scenarios（{len(uniq)} 条）：{uniq}")
        if not ops:
            ops.append("无需迁入字段（保留方已全面更丰富）")

        for o in ops:
            print("   -", o)
        total_ops += len(ops)

        if apply:
            if "unit_id" in fields and drop.unit_id:
                append_scalar_and_block(keep_f, drop.unit_id, drop.content_md)
            if "code_snippets" in fields and drop.code_snippets:
                snippets = [
                    s if isinstance(s, str) else s.model_dump() for s in drop.code_snippets
                ]
                replace_inline_empty_list(keep_f, "code_snippets", snippets)
            if "typical_scenarios_dedup" in fields:
                uniq = [s for s in drop.typical_scenarios if s not in keep.typical_scenarios]
                if uniq:
                    append_list_items(keep_f, "typical_scenarios", uniq)
            drop_f.unlink()
            print(f"   ✅ 已改写 {keep_f.name}，已删除 {drop_f.name}")
        print()

    print(f"{'已执行' if apply else '待执行'} {total_ops} 项迁移操作")
    if not apply:
        print("（dry-run，加 --apply 落地）")


if __name__ == "__main__":
    main("--apply" in sys.argv)
