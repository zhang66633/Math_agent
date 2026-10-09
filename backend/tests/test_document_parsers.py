"""document_parsers 回归测试 — 从 knowledge_search_routes.py 拆出的解析器。

覆盖无外部依赖的路径：CSV 多编码解析、多模态消息的 openai/anthropic 两种
图片块格式。PDF/Excel/DOCX 依赖重库，由上传链路实测覆盖，不在此单测。
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.document_parsers import build_multimodal_message, parse_csv


def test_parse_csv_utf8():
    text = parse_csv(b"a,b\n1,2\n", "t.csv")
    assert "[CSV: t.csv]" in text
    assert "维度: 1 行 × 2 列" in text
    assert "['a', 'b']" in text


def test_parse_csv_gbk_fallback():
    """GBK 编码的中文 CSV 不能乱码（常见于用户从 Excel 另存的文件）。"""
    text = parse_csv("姓名,分数\n甲,90\n".encode("gbk"), "g.csv")
    assert "姓名" in text
    assert "甲" in text


def test_multimodal_message_text_only():
    msg = build_multimodal_message("hello", [])
    assert msg.content == "hello"


def test_multimodal_message_openai_format():
    msg = build_multimodal_message("hi", ["data:image/png;base64,AAAA"])
    assert msg.content[0] == {"type": "text", "text": "hi"}
    assert msg.content[1]["type"] == "image_url"
    assert msg.content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_multimodal_message_bare_base64_gets_prefix():
    """旧调用方传裸 base64（无 data: 前缀）→ 自动补 PNG data URI。"""
    msg = build_multimodal_message("hi", ["AAAA"])
    assert msg.content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_multimodal_message_anthropic_format():
    msg = build_multimodal_message("hi", ["data:image/jpeg;base64,BBBB"], provider="anthropic")
    block = msg.content[1]
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/jpeg"
    assert block["source"]["data"] == "BBBB"


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
