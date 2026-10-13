"""学习事件与成就持久化测试(阶段 0)。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.learning_store import LearningStore  # noqa: E402


def test_event_persistence(tmp_path):
    store = LearningStore(db_path=tmp_path / "learning.db")
    store.add_event("modeler_lp_01", "learn", 1.0)
    store.add_event("modeler_lp_02", "practice", 0.0)
    events = store.list_events()
    assert len(events) == 2
    assert events[0]["unit_id"] == "modeler_lp_01"
    assert events[1]["event_type"] == "practice"

    # 重新打开(模拟重启)→ 数据仍在
    store2 = LearningStore(db_path=tmp_path / "learning.db")
    assert store2.count_events() == 2


def test_active_dates(tmp_path):
    store = LearningStore(db_path=tmp_path / "learning.db")
    store.add_event("u1", "learn", 1.0, created_at="2026-08-14T10:00:00")
    store.add_event("u2", "practice", 0.0, created_at="2026-08-14T22:00:00")
    store.add_event("u3", "learn", 1.0, created_at="2026-08-13T09:00:00")
    assert store.active_dates() == {"2026-08-14", "2026-08-13"}


def test_achievement_unlock_and_ack(tmp_path):
    store = LearningStore(db_path=tmp_path / "learning.db")

    assert store.unlock_achievement("quiz_10") is True  # 新解锁
    assert store.unlock_achievement("quiz_10") is False  # 幂等
    assert store.unlocked_ids()["quiz_10"]["acknowledged"] is False

    store.ack_all()
    assert store.unlocked_ids()["quiz_10"]["acknowledged"] is True

    # 重启后仍解锁
    store2 = LearningStore(db_path=tmp_path / "learning.db")
    assert "quiz_10" in store2.unlocked_ids()


if __name__ == "__main__":
    # 直跑入口也走系统临时目录：曾经写死 Path("data")，每次直跑都在运行数据目录
    # 留一堆 test_learning*.db（审计 2026-10-14 点名的测试残渣，与真实
    # learning.db / practice.db 混放，排查时极易看错）。
    import tempfile
    from pathlib import Path as _Path

    with tempfile.TemporaryDirectory(prefix="mma_test_learning_") as _td:
        base = _Path(_td)
        test_event_persistence(base / "learning.db")
        test_active_dates(base / "learning2.db")
        test_achievement_unlock_and_ack(base / "learning3.db")
    print("ALL TESTS PASSED")
