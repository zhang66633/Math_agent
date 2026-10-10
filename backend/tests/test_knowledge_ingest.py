"""knowledge_ingest 回归测试 — 从 knowledge_search_routes.py 拆出的提取流水线。

覆盖不依赖 LLM 的部分：job store 契约（new_job/get_job）与 LLM JSON
解析（围栏/散文混排）。LLM 提取主路径需要真实模型调用，由上传链路实测。
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services import knowledge_ingest as ingest


def test_job_store_roundtrip():
    job_id = ingest.new_job("job_test_1", "processing")
    assert job_id == "job_test_1"
    job = ingest.get_job("job_test_1")
    assert job == {"status": "processing", "result": None, "error": None}

    ingest.new_job("job_test_1", "completed", result={"entry_id": "mc_001"})
    job = ingest.get_job("job_test_1")
    assert job["status"] == "completed"
    assert job["result"]["entry_id"] == "mc_001"
    assert job["error"] is None

    ingest.new_job("job_test_1", "error", error="boom")
    assert ingest.get_job("job_test_1")["error"] == "boom"


def test_get_job_missing_returns_none():
    assert ingest.get_job("job_does_not_exist") is None


def test_parse_llm_json_plain():
    assert ingest.parse_llm_json('{"name": "线性规划"}') == {"name": "线性规划"}


def test_parse_llm_json_fenced():
    out = ingest.parse_llm_json('```json\n{"name": "AHP"}\n```\n其他说明文字')
    assert out == {"name": "AHP"}


def test_parse_llm_json_among_prose():
    out = ingest.parse_llm_json('提取结果：{"year": 2024} 以上。')
    assert out == {"year": 2024}


def test_parse_llm_json_garbage_returns_empty():
    assert ingest.parse_llm_json("完全没有 JSON") == {}


def test_unique_output_path_no_collision(tmp_path):
    """无同名文件 → 基础名，不带 entry_id 后缀。"""
    p = ingest._unique_output_path(tmp_path, "2023研赛B", "paper_099")
    assert p.name == "2023研赛B.yaml"


def test_unique_output_path_collision_appends_entry_id(tmp_path):
    """同名已存在 → 追加 entry_id（同题多篇不再互相覆盖）。"""
    (tmp_path / "2023研赛B.yaml").write_text("existing", encoding="utf-8")
    p = ingest._unique_output_path(tmp_path, "2023研赛B", "paper_099")
    assert p.name == "2023研赛B_paper_099.yaml"


def test_unique_output_path_idempotent(tmp_path):
    """带后缀的文件也已存在 → 仍返回该路径（重复导入同一来源=幂等更新）。"""
    (tmp_path / "2023研赛B.yaml").write_text("a", encoding="utf-8")
    (tmp_path / "2023研赛B_paper_099.yaml").write_text("b", encoding="utf-8")
    p = ingest._unique_output_path(tmp_path, "2023研赛B", "paper_099")
    assert p.name == "2023研赛B_paper_099.yaml"


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
