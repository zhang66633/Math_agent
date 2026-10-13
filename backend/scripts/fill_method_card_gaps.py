"""补全方法卡缺失字段（幂等；默认 dry-run，--apply 才落盘）。

与 kb_extractor.extract_method 的区别：那个从自由文本提取**新**卡片；
本脚本只给**已有**卡片补缺失字段，绝不覆盖作者已写的内容。

设计要点：
  - 只补缺的：typical_scenarios / applicable_when / formulas / code_snippets
  - 一张卡一次 LLM 调用，把该卡所有缺失字段一起要回来（省调用次数）
  - prompt 里带上卡片已有的 name/principle/category，要求 LLM 只依据这些推断，
    不允许编造与该方法的适用性矛盾的内容
  - 落盘前过 Pydantic schema 校验，不合格就跳过该卡并记录
  - 外科式写入：块列表追加 / 空列表展开，不动其他任何字节

用法：
    python scripts/fill_method_card_gaps.py --limit 1     # 冒烟：只跑一张
    python scripts/fill_method_card_gaps.py               # dry-run 全量，只看会改什么
    python scripts/fill_method_card_gaps.py --apply       # 落盘
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from app.core.llm.factory import get_llm
from app.knowledge.schemas import MethodCard

KB = Path(__file__).resolve().parent.parent / "knowledge_base"
METHODS = KB / "methods"

# 要补的字段 →（是否列表、说明）
GAP_FIELDS = {
    "typical_scenarios": "典型适用场景（3-5 条，每条一句话，说明什么情况下该用这个方法）",
    "applicable_when": "适用条件（3-5 条，说明数据/问题特征满足什么时用它）",
    "formulas": "核心公式（2-5 条，LaTeX 或纯文本，写清符号含义）",
    "code_snippets": "可运行代码示例（1 段，Python，能体现该方法的核心用法）",
}

PROMPT = """你是数学建模知识工程师。下面是一张**已有**方法卡的部分内容，
其中某些字段为空。请**只依据给定内容**补全这些空字段，不要与已有内容矛盾，
不要编造与该数学方法无关的信息。

方法名：{name}
英文名：{name_en}
类别：{category}
原理：
{principle}

已有字段（不要重复输出，也不要修改）：
{existing}

请为以下空字段各补上内容，返回严格 JSON（不要 Markdown 代码块标记）：
{fields_spec}

要求：
- typical_scenarios / applicable_when：3-5 条中文短句
- formulas：2-5 条，LaTeX 写法，符号要有说明
- code_snippets：1 段简洁可运行的 Python（numpy/scipy/sympy 级别），不要依赖不存在的数据文件
- 全部用中文（公式与代码除外）
- 某个字段确实无法从给定内容合理推断时，返回空列表，不要硬编
"""


def card_files():
    for f in sorted(METHODS.rglob("*.yaml")):
        if "_source_skill_docs" in str(f) or f.name.startswith("_"):
            continue
        yield f


def load_card(f: Path) -> tuple[dict, MethodCard]:
    raw = yaml.safe_load(f.read_text(encoding="utf-8"))["method_card"]
    return raw, MethodCard(**raw)


def gaps_of(card: MethodCard) -> list[str]:
    out = []
    for field in GAP_FIELDS:
        if not getattr(card, field):
            out.append(field)
    return out


# ── 外科式写入（与 merge_duplicate_method_cards 同源思路）────────


def _find_key_line(lines, key):
    for i, ln in enumerate(lines):
        if ln.rstrip() == f"  {key}:":
            return i
    return -1


def _block_end(lines, start):
    end = start + 1
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1
    return end


def append_list_items(path: Path, key: str, items) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    ki = _find_key_line(lines, key)
    if ki < 0:
        raise RuntimeError(f"{path.name}: 找不到 {key} 块")
    end = _block_end(lines, ki)
    dumped = yaml.safe_dump(list(items), allow_unicode=True, sort_keys=False, width=100)
    body = "".join(("  " + line if line.strip() else line) for line in dumped.splitlines(keepends=True))
    lines[end:end] = [body]
    path.write_text("".join(lines), encoding="utf-8")


def expand_empty_list(path: Path, key: str, items) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.rstrip() == f"  {key}: []":
            dumped = yaml.safe_dump(list(items), allow_unicode=True, sort_keys=False, width=100)
            body = "".join(("  " + line if line.strip() else line) for line in dumped.splitlines(keepends=True))
            lines[i] = f"  {key}:\n" + body
            path.write_text("".join(lines), encoding="utf-8")
            return
    # 没有显式空列表 → 退化为追加
    append_list_items(path, key, items)


def apply_gap(path: Path, field: str, items) -> None:
    """把 items 写进 path 的 field。items 为 str 或 dict 的列表。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    has_block = _find_key_line(lines, field) >= 0
    has_empty = any(ln.rstrip() == f"  {field}: []" for ln in lines)
    if has_block:
        append_list_items(path, field, items)
    elif has_empty:
        expand_empty_list(path, field, items)
    else:
        # 字段整行都没有 → 追加到文件末尾
        dumped = yaml.safe_dump(list(items), allow_unicode=True, sort_keys=False, width=100)
        body = "".join(("  " + line if line.strip() else line) for line in dumped.splitlines(keepends=True))
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"  {field}:\n")
        lines.append(body)
        path.write_text("".join(lines), encoding="utf-8")


# ── 主流程 ───────────────────────────────────────────


def build_prompt(card: MethodCard, raw: dict, gaps: list[str]) -> str:
    """raw 是 YAML 原始 dict——不要用 card（Pydantic 对象），否则 json.dumps
    会遇到 Formula/CodeSnippet 实例而炸。"""
    existing = []
    for field in GAP_FIELDS:
        if field in gaps:
            continue
        val = raw.get(field) or []
        existing.append(f"- {field}: {yaml.safe_dump(val, allow_unicode=True, width=100).strip()[:600]}")
    fields_spec = "\n".join(f'  "{f}": <{GAP_FIELDS[f]}>' for f in gaps)
    return PROMPT.format(
        name=card.name,
        name_en=card.name_en or "（无）",
        category=", ".join(card.category),
        principle=card.principle[:2500],
        existing="\n".join(existing) or "（无）",
        fields_spec=fields_spec,
    )


def parse_llm_json(raw: str) -> dict:
    raw = str(raw).strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 张有缺口的卡（0=全部）")
    ap.add_argument("--only", default="", help="只处理指定卡片 id")
    args = ap.parse_args()

    targets = []
    for f in card_files():
        raw, card = load_card(f)
        gaps = gaps_of(card)
        if not gaps:
            continue
        if args.only and card.id != args.only:
            continue
        targets.append((f, raw, card, gaps))
        if args.limit and len(targets) >= args.limit:
            break

    print(f"有字段缺口的方法卡：{len(targets)} 张")
    if not targets:
        return 0

    llm = get_llm("analysis")
    ok = fail = skip = 0

    for f, raw, card, gaps in targets:
        prompt = build_prompt(card, raw, gaps)
        try:
            resp = llm.invoke(prompt)
            data = parse_llm_json(resp.content)
        except Exception as e:  # noqa: BLE001
            print(f"  [{card.id}] LLM 调用/解析失败: {str(e)[:120]}")
            fail += 1
            continue

        # 只取缺口字段，且必须非空
        picked = {}
        for field in gaps:
            val = data.get(field)
            if isinstance(val, list) and val:
                picked[field] = val
        if not picked:
            print(f"  [{card.id}] LLM 未返回可用内容，跳过")
            skip += 1
            continue

        # 过 schema 校验（用补全后的完整卡片验，不合格就跳过）
        merged = dict(raw)
        merged.update(picked)
        try:
            MethodCard(**merged)
        except Exception as e:  # noqa: BLE001
            print(f"  [{card.id}] 补全后 schema 校验失败，跳过: {str(e)[:120]}")
            skip += 1
            continue

        summary = ", ".join(f"{k}×{len(v)}" for k, v in picked.items())
        print(f"  [{card.id}] {card.name}：{summary}")
        ok += 1

        if args.apply:
            for field, val in picked.items():
                apply_gap(f, field, val)

    print(f"\n{'已落盘' if args.apply else '待落盘'}：可用 {ok}，跳过 {skip}，失败 {fail}")
    if not args.apply:
        print("（dry-run，加 --apply 落盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
