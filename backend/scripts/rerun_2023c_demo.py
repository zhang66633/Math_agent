"""重跑答辩演示用的 2023 国赛 C 题方案任务。

背景：原演示任务 `579b79d0` 已于 2026-10-14 被删除（删除功能上线后用户实测删除）。
原始竞赛数据未受影响（`data/problems/2023C/`），本脚本重新走一遍
「准备数据 → 上传 → 建任务 → 轮询到完成」。

与一次性探针的区别：这是可重复执行的正式脚本，数据准备、上传、轮询、落盘
结果摘要都在里面，不依赖任何临时状态。

用法：
    python scripts/rerun_2023c_demo.py                     # 匿名创建（owner=访客桶）
    python scripts/rerun_2023c_demo.py --as zhang66633     # 以该用户身份创建（推荐）
    python scripts/rerun_2023c_demo.py --no-poll           # 只建任务，不等待完成

> ⚠️ 用 `--as` 的原因：任务按属主过滤。匿名创建时 owner 落在访客桶
> （resolve_user_id → "default"），登录 zhang66633 后 `GET /api/tasks`
> 会返回空，前端「历史任务」面板看不到。以登录身份创建才能两边都对上。

产物：
    data/_last_rerun.json   — task_id / 状态 / 字数 / 图表数 / 耗时
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE = "http://127.0.0.1:8002"
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "problems" / "2023C"
STAGE = ROOT / "data" / "_demo_upload"
OUT = ROOT / "data" / "_last_rerun.json"

PROBLEM = """在生鲜超市中，蔬菜类商品的保鲜期较短，品相随销售时间增加而变差。超市通常采用动态定价策略和限时折扣来促进销售，同时需要根据历史销售数据制定合理的补货计划。

某超市拥有多家门店，经营各类蔬菜商品。蔬菜的采购成本相对稳定，但销售价格需要根据市场供求、品相变化和保质期动态调整。对于保鲜期临近的蔬菜，超市通常会采取限时折扣以促进销售、减少损耗。

请建立数学模型解决以下问题：
问题1：分析蔬菜各品类及单品的销售量分布规律及相互关系。
问题2：建立蔬菜品类的定价模型，给出各品类未来一周的日补货总量和定价策略。
问题3：在满足最小陈列量要求的前提下，确定单品补货量和定价策略。
问题4：收集更多数据，优化模型并给出改进建议。

附件数据（已上传）：
- attachment1_products.xlsx：单品分类信息（product_code, product_name, category_code, category_name）
- attachment3_wholesale.xlsx：批发价（date, product_code, wholesale_price）
- attachment4_loss.xlsx：损耗率（category_code, category_name, loss_rate）
- category_daily.csv / product_daily.csv：品类级/单品级日聚合（volume, revenue, transactions, avg_price）
- category_stats.csv / product_stats.csv：品类级/单品级汇总统计
- dow.csv：周内效应；wholesale.csv：批发价；loss.csv：损耗率
- DATA_README.md：各文件字段说明

原始销售明细共 87.8 万行，已预先聚合为上述日/统计文件（parquet 原始文件沙箱无法直接读取）。
"""

# 竞赛原样的 xlsx 附件
XLSX = [
    "attachment1_products.xlsx",
    "attachment3_wholesale.xlsx",
    "attachment4_loss.xlsx",
]

# 预计算聚合（parquet → csv）。parquet 虽已入上传白名单，但转成 CSV 更稳：
# 附件摘要分支对两者都支持，而 CSV 不依赖 pyarrow 版本差异。
PARQUET_TO_CSV = [
    "_precomputed_category_stats.parquet",
    "_precomputed_product_stats.parquet",
    "_precomputed_category_daily.parquet",
    "_precomputed_product_daily.parquet",
    "_precomputed_dow.parquet",
    "_precomputed_wholesale.parquet",
    "_precomputed_loss.parquet",
]


def prepare_data() -> list[Path]:
    """把 2023C 数据准备成可上传的文件集合，返回文件路径列表。"""
    import pandas as pd

    STAGE.mkdir(parents=True, exist_ok=True)
    for stale in STAGE.iterdir():
        if stale.is_file():
            stale.unlink()

    files: list[Path] = []
    for name in XLSX:
        src = SRC / name
        if not src.exists():
            print(f"  !! 缺 {name}")
            continue
        dst = STAGE / name
        shutil.copy2(src, dst)
        files.append(dst)

    for name in PARQUET_TO_CSV:
        src = SRC / name
        if not src.exists():
            print(f"  !! 缺 {name}")
            continue
        df = pd.read_parquet(src)
        out = STAGE / (name.replace("_precomputed_", "").replace(".parquet", ".csv"))
        df.to_csv(out, index=False, encoding="utf-8")
        files.append(out)

    readme = SRC / "DATA_README.md"
    if readme.exists():
        dst = STAGE / "DATA_README.md"
        shutil.copy2(readme, dst)
        files.append(dst)

    print(f"数据准备完成：{len(files)} 个文件 / "
          f"{sum(f.stat().st_size for f in files)/1e6:.2f} MB")
    return sorted(files)


def upload(c: httpx.Client, files: list[Path]) -> list[dict]:
    refs = []
    for f in files:
        with f.open("rb") as fh:
            r = c.post(
                "/api/files/upload",
                files={"file": (f.name, fh, "application/octet-stream")},
                timeout=300,
            )
        r.raise_for_status()
        d = r.json()
        refs.append({"file_id": d["file_id"], "filename": d["filename"]})
        print(f"  上传 {f.name:<26} → {d['file_id']}")
    return refs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-poll", action="store_true", help="只建任务，不等待完成")
    ap.add_argument(
        "--as",
        dest="as_login",
        default="",
        metavar="LOGIN",
        help="以该 GitHub 用户身份创建任务（置 owner，避免落在访客桶看不见）",
    )
    args = ap.parse_args()

    headers: dict[str, str] = {}
    if args.as_login:
        # 本地签一枚 JWT：与 .env 里同一份 secret，服务端认
        from app.auth import create_jwt
        from app.auth.schemas import GitHubUser

        headers["Authorization"] = f"Bearer {create_jwt(GitHubUser(id=1, login=args.as_login))}"
        print(f"以 {args.as_login} 身份创建任务（owner 会对上，登录后可见）")

    files = prepare_data()

    with httpx.Client(base_url=BASE, timeout=600) as c:
        print("\n=== 上传附件 ===")
        refs = upload(c, files)

        print(f"\n=== 创建方案任务（{len(refs)} 个附件）===")
        r = c.post(
            "/api/tasks",
            json={"problem": PROBLEM, "mode": "execute", "files": refs},
            headers=headers,
        )
        r.raise_for_status()
        tid = r.json()["task_id"]
        print(f"task_id = {tid}")

        summary = {
            "task_id": tid,
            "status": "running",
            "seconds": 0,
            "owner": args.as_login or "guest(访客桶)",
        }
        if args.no_poll:
            print("\n（--no-poll：任务在后台跑，稍后自行查询）")
            OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"task_id 已写入 {OUT}")
            return 0

        print("\n=== 轮询（每 20 秒）===")
        t0 = time.time()
        last = None
        st = {}
        while time.time() - t0 < 2400:
            time.sleep(20)
            st = c.get(f"/api/tasks/{tid}", headers=headers).json()
            cur = st.get("status")
            msgs = c.get(f"/api/tasks/{tid}/messages", headers=headers).json()
            if cur != last:
                print(f"  [{time.time()-t0:6.0f}s] status={cur}  messages={len(msgs)}")
            last = cur
            if cur in ("completed", "failed", "cancelled"):
                break

        arts = st.get("artifacts") or []
        figs = [a for a in arts if a.get("type") == "figure"]
        summary = {
            "task_id": tid,
            "status": st.get("status"),
            "owner": args.as_login or "guest(访客桶)",
            "final_len": len(st.get("final_response") or ""),
            "figures": len(figs),
            "messages": len(c.get(f"/api/tasks/{tid}/messages", headers=headers).json()),
            "events": c.get(f"/api/tasks/{tid}/events", headers=headers).json().get("total"),
            "seconds": round(time.time() - t0),
        }
        OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        print("\n=== 结果 ===")
        for k, v in summary.items():
            print(f"  {k:<10} {v}")
        print(f"\n已写入 {OUT}")
        print(f"\n前端打开：方案模式 → 右栏「历史任务」→ 选 {tid}")
        if not args.as_login:
            print(
                "⚠️ 本次匿名创建（owner=访客桶）。若你登录着，前端看不到它——"
                "建议加 `--as zhang66633` 重跑。"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
