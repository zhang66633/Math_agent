"""整理答辩演示所需的全部文件到一个文件夹（可重复执行，幂等）。

产物：桌面 `答辩演示材料/`
  01_题目文本.txt      — 可直接复制粘贴进方案模式输入框
  02_数据文件/          — 方案模式要挂的附件（12 个，约 0.8 MB）
     可选_全量明细/     — attachment2_sales.parquet（11.5 MB，87.8 万行原始明细）
  03_演示稿/            — 完整底稿与速查卡
  04_备用素材/          — 断网/失败时的兜底展示物
  README.md            — 总说明与操作步骤

数据源：backend/data/problems/2023C/（原始竞赛数据，未受任务删除影响）
备用素材源：桌面 答辩备用/（上一次跑成的论文、图表、交付包）
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "problems" / "2023C"
DOCS = ROOT.parent / "docs"
DESKTOP = Path.home() / "Desktop"
KIT = DESKTOP / "答辩演示材料"
BACKUP = DESKTOP / "答辩备用"

# 方案模式要挂的附件（12 个）：3 个竞赛原样 xlsx + 7 个预计算聚合 + README
ATTACHMENTS = [
    "attachment1_products.xlsx",
    "attachment3_wholesale.xlsx",
    "attachment4_loss.xlsx",
    "_precomputed_category_stats.parquet",
    "_precomputed_product_stats.parquet",
    "_precomputed_category_daily.parquet",
    "_precomputed_product_daily.parquet",
    "_precomputed_dow.parquet",
    "_precomputed_wholesale.parquet",
    "_precomputed_loss.parquet",
    "DATA_README.md",
]
# 赛题原题 PDF：不用挂（是题目不是数据），但放进来便于核对
REFERENCE = ["C题.pdf"]
# 全量明细：可选，带上更完整但拖慢沙箱
OPTIONAL_FULL = ["attachment2_sales.parquet"]

PROBLEM_TEXT = """在生鲜超市中，蔬菜类商品的保鲜期较短，品相随销售时间增加而变差。超市通常采用动态定价策略和限时折扣来促进销售，同时需要根据历史销售数据制定合理的补货计划。

某超市拥有多家门店，经营各类蔬菜商品。蔬菜的采购成本相对稳定，但销售价格需要根据市场供求、品相变化和保质期动态调整。对于保鲜期临近的蔬菜，超市通常会采取限时折扣以促进销售、减少损耗。

请建立数学模型解决以下问题：
问题1：分析蔬菜各品类及单品的销售量分布规律及相互关系。
问题2：建立蔬菜品类的定价模型，给出各品类未来一周的日补货总量和定价策略。
问题3：在满足最小陈列量要求的前提下，确定单品补货量和定价策略。
问题4：收集更多数据，优化模型并给出改进建议。

【附件说明】已上传的附件如下，请用 pd.read_excel / pd.read_csv / pd.read_parquet 按扩展名读取（文件名即沙箱工作目录中的文件名）：
- attachment1_products.xlsx：单品分类信息（product_code, product_name, category_code, category_name）
- attachment3_wholesale.xlsx：批发价（date, product_code, wholesale_price）
- attachment4_loss.xlsx：损耗率（category_code, category_name, loss_rate）
- _precomputed_category_daily.parquet / _precomputed_product_daily.parquet：品类级/单品级日聚合（date, code, volume, revenue, transactions, avg_price）
- _precomputed_category_stats.parquet / _precomputed_product_stats.parquet：品类级/单品级汇总统计
- _precomputed_dow.parquet：周内效应（星期几的平均销量倍率）
- _precomputed_wholesale.parquet / _precomputed_loss.parquet：批发价与损耗率（整理版）
- DATA_README.md：各文件字段说明

原始销售明细共 87.8 万行，已预先聚合为上述日/统计文件。
"""

README = """# 答辩演示材料

> 生成于 2026-10-14。本文件夹是「方案模式演示」的完整自包含材料，
> 只要 `backend` 服务起着，用它就能跑出演示任务。

## 目录

| 路径 | 用途 |
|------|------|
| `01_题目文本.txt` | **直接全选复制**，粘进方案模式输入框 |
| `02_数据文件/` | 方案模式要挂的 **11 个附件**（约 0.8 MB） |
| `02_数据文件/可选_全量明细/` | `attachment2_sales.parquet`（11.5 MB，87.8 万行原始明细）。**可挂可不挂**——挂了更完整，但沙箱读取更慢 |
| `02_数据文件/参考_C题.pdf` | 赛题原题 PDF。**不用挂**，是题目不是数据，留着核对用 |
| `03_演示稿/` | 完整底稿（含 18 问专家问答预案）与一页速查卡 |
| `04_备用素材/` | 断网或跑挂时的兜底展示物：论文 Markdown、6 张图表、5.19 MB 交付 ZIP、粒子群动画 GIF |

## 怎么跑

### 路线 A：一条命令（推荐，不依赖前端）

```powershell
cd D:\\_Projects\\math_agent\\backend
..\\.venv\\Scripts\\python.exe scripts\\rerun_2023c_demo.py
```

脚本会自己准备数据、上传 11 个附件、建任务、每 20 秒打印进度，跑完把
task_id 与统计写到 `data/_last_rerun.json`。约 10–15 分钟。

### 路线 B：前端手动

1. **先登录**（右上有头像）。不登录的话任务落在访客桶，登录后反而看不见。
2. 左侧进「方案模式」。
3. 把 `01_题目文本.txt` 全文粘贴进输入框。
4. 把 `02_数据文件/` 里的 **11 个文件**全部选中挂上（`参考_C题.pdf` 不要挂）。
5. 发送，等它跑完。
6. 跑完后在**右栏「历史任务」**里能找到这条任务（按 task_id）。

> ⚠️ 2026-10-14 修复了一个缺陷：此前上传的附件**从未真正进入流水线**
> （`create_initial_state` 不收 `data_files`），数据预处理 agent 因「无数据文件」
> 被恒跳过，而求解 agent 被告知「没有预挂载数据文件」转而**构造模拟数据**。
> 也就是说，修复前的「真实数据分析」其实是在合成数据上做的。
> 现在附件会被复制到任务的 `_inputs/` 目录并自动挂载进沙箱，可直接按文件名读取。

## 演示时怎么用

- 主演示（方案模式）用**提前跑好的任务**，不要现场等 10 分钟——见 `03_演示稿/` 的两段式节奏说明。
- 现场「证明它真在跑」用轻量题（无附件、走快路径），90 秒内可看到前几个节点。
- 粒子群动画：对话模式输入 `粒子群优化算法动画演示`，约 33 秒出 GIF；
  出不来就打开 `04_备用素材/pso_demo.gif`。

## 实测参考数据（2026-10-14）

| 项 | 值 |
|----|----|
| 论文 | 43,052 字符 / 10 章节 / 351 处行内公式 / 123 行表格 |
| 事件 | 920 条落盘 |
| 图表 | 6 张 PNG + 大量中间 CSV + results_summary.xlsx |
| 交付包 | 5.19 MB ZIP |
| 知识库 | 81 方法卡 / 32 论文 / 41 真题 / 3 模板 = 154 条目 |
"""


def main() -> int:
    if not SRC.exists():
        print(f"!! 数据源不存在: {SRC}")
        return 1

    data_dir = KIT / "02_数据文件"
    optional_dir = data_dir / "可选_全量明细"
    script_dir = KIT / "03_演示稿"
    backup_dir = KIT / "04_备用素材"
    charts_dir = backup_dir / "图表"
    for d in (data_dir, optional_dir, script_dir, backup_dir, charts_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 01 题目文本
    (KIT / "01_题目文本.txt").write_text(PROBLEM_TEXT, encoding="utf-8")
    (KIT / "README.md").write_text(README, encoding="utf-8")

    n = 0
    for name in ATTACHMENTS:
        src = SRC / name
        if src.exists():
            shutil.copy2(src, data_dir / name)
            n += 1
        else:
            print(f"  !! 缺 {name}")
    for name in REFERENCE:
        src = SRC / name
        if src.exists():
            shutil.copy2(src, data_dir / f"参考_{name}")
        else:
            print(f"  !! 缺 {name}")
    for name in OPTIONAL_FULL:
        src = SRC / name
        if src.exists():
            shutil.copy2(src, optional_dir / name)
        else:
            print(f"  !! 缺 {name}")

    # 03 演示稿
    for name in ("defense-demo.md", "答辩速查卡.md"):
        src = DOCS / name
        if src.exists():
            shutil.copy2(src, script_dir / name)
        else:
            print(f"  !! 缺 docs/{name}")

    # 04 备用素材：从旧任务备份里搬
    if BACKUP.exists():
        for name in ("pso_demo.gif", "2023C_论文.md", "results_summary.xlsx"):
            src = BACKUP / name
            if src.exists():
                shutil.copy2(src, backup_dir / name)
        for z in BACKUP.glob("*_results.zip"):
            shutil.copy2(z, backup_dir / z.name)
        for png in (BACKUP / "图表").glob("*.png"):
            shutil.copy2(png, charts_dir / png.name)
    else:
        print(f"  !! 备用素材源不存在: {BACKUP}")

    print("=== 答辩演示材料/ 整理完成 ===")
    print(f"位置: {KIT}\n")
    total = 0
    for p in sorted(KIT.rglob("*")):
        rel = p.relative_to(KIT)
        if p.is_dir():
            print(f"  [目录] {rel}/")
        else:
            sz = p.stat().st_size
            total += sz
            print(f"  {sz:>12,}  {rel}")
    print(f"\n合计 {total:,} B（{total/1e6:.2f} MB）")
    print(f"\n要挂的附件在 02_数据文件/（{n} 个）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
