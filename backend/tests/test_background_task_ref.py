"""后台任务强引用回归测试（2026-10-14 实测故障）。

故障现象：服务跑一段时间后，新建的方案任务全部卡在 status=running、
messages=0，编排器线程从未启动。根因是路由里
`asyncio.create_task(asyncio.to_thread(...))` 的返回值没有任何地方持有——
asyncio 事件循环只持弱引用，fire-and-forget 的 Task 会在开始执行前被 GC 回收
（Python 官方文档明确警告过这一点）。

本测试锁两件事：
  ① create_task 路由必须通过 _spawn_background 派发（强引用被持有）；
  ② _spawn_background 本身要真的能跑完、且完成后自动清理引用。
"""

import asyncio
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api import tasks as tasks_mod  # noqa: E402


def _bare_create_task_calls(func) -> list[str]:
    """用 AST 找出函数体内真实的 asyncio.create_task(...) 调用（忽略注释/字符串）。"""
    import ast

    tree = ast.parse(inspect.getsource(func))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # asyncio.create_task(...)
        if isinstance(f, ast.Attribute) and f.attr == "create_task":
            base = f.value
            if isinstance(base, ast.Name) and base.id == "asyncio":
                hits.append(f"L{node.lineno}")
        # create_task(...)（from asyncio import create_task 的形式）
        elif isinstance(f, ast.Name) and f.id == "create_task":
            hits.append(f"L{node.lineno}")
    return hits


def test_create_task_route_uses_spawn_background():
    """路由源码里不许再出现裸 asyncio.create_task 调用（必须走 _spawn_background）。"""
    hits = _bare_create_task_calls(tasks_mod.create_task)
    assert not hits, (
        f"create_task 路由在 {hits} 处出现裸 asyncio.create_task 调用——"
        "Task 会被 GC 回收，表现为任务永远 running、0 条消息"
    )
    src = inspect.getsource(tasks_mod.create_task)
    assert "_spawn_background" in src, "create_task 路由应通过 _spawn_background 派发编排器"


def test_spawn_background_holds_strong_reference():
    """_spawn_background 必须把 Task 存进 _background_tasks（强引用）。"""

    async def scenario():
        ran = {"v": False}

        async def coro():
            await asyncio.sleep(0.05)
            ran["v"] = True

        task = tasks_mod._spawn_background(coro())
        # 派发后应立刻进入强引用集合
        assert task in tasks_mod._background_tasks, "Task 未被持有强引用"
        await task
        assert ran["v"], "协程没跑完"
        # 完成后应自动移出集合（否则无限增长）
        assert task not in tasks_mod._background_tasks, "完成后未自动清理引用"

    asyncio.run(scenario())


def test_spawn_background_survives_gc_pressure():
    """即便在 GC 压力下，已派发的任务也必须跑完。

    这是本次故障的核心：裸 create_task 的 Task 在 GC 后消失。
    这里显式 gc.collect() 制造压力来验证强引用真的顶用。
    """
    import gc

    async def scenario():
        done = {"v": False}

        async def coro():
            for _ in range(5):
                await asyncio.sleep(0.01)
            done["v"] = True

        task = tasks_mod._spawn_background(coro())
        gc.collect()
        await asyncio.sleep(0.05)
        gc.collect()
        await task
        assert done["v"], "GC 压力下任务被回收了"

    asyncio.run(scenario())


def test_background_tasks_set_is_bounded():
    """强引用集合不能无限增长——完成即 discard。"""

    async def scenario():
        for _ in range(20):
            await tasks_mod._spawn_background(asyncio.sleep(0))
        # 全部完成后集合应为空
        assert not tasks_mod._background_tasks, (
            f"集合未清空，残留 {len(tasks_mod._background_tasks)} 个"
        )

    asyncio.run(scenario())


if __name__ == "__main__":
    for _fn in [
        test_create_task_route_uses_spawn_background,
        test_spawn_background_holds_strong_reference,
        test_spawn_background_survives_gc_pressure,
        test_background_tasks_set_is_bounded,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    print("ALL TESTS PASSED")
