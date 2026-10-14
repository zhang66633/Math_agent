"""重做演示文件夹为「可直接全选拖进前端」的扁平结构（幂等，可重复执行）。

用户诉求：一个文件夹，打开 → Ctrl+A → 拖进前端上传框，不要分类归档。
所以把附件单独放一个 `上传这些文件/`，里面**只有要上传的文件、无子目录、无杂项**
（不放参考 PDF——它不是数据，混进去会被误上传）。

结构：
    答辩演示材料/
      上传这些文件/       ← Ctrl+A 拖进前端（12 个文件，扁平）
      题目.txt            ← 全选复制粘贴进输入框
      演示稿/
      备用素材/
      README.md
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "problems" / "2023C"
DOCS = ROOT.parent / "docs"
DESKTOP = Path.home() / "Desktop"
KIT = DESKTOP / "答辩演示材料"

UPLOAD_DIR = KIT / "上传这些文件"
SCRIPT_DIR = KIT / "演示稿"
BACKUP_DIR = KIT / "备用素材"
CHARTS_DIR = BACKUP_DIR / "图表"

# 要上传的 12 个文件。全量明细放进来是有意的：2023C 问题 3 要「单品级」补货与
# 定价，只有聚合表做不了单项分析；且 .parquet 现已支持（pyarrow 进依赖 + 白名单）。
# 想跑快一点就把它移出去——11 个聚合文件已能覆盖问题 1/2 的主要分析。
UPLOAD_FILES = [
    # 竞赛原样附件
    "attachment1_products.xlsx",
    "attachment2_sales.parquet",
    "attachment3_wholesale.xlsx",
    "attachment4_loss.xlsx",
    # 预计算聚合（沙箱读取快，适合预算紧时）
    "_precomputed_category_daily.parquet",
    "_precomputed_category_stats.parquet",
    "_precomputed_product_daily.parquet",
    "_precomputed_product_stats.parquet",
    "_precomputed_dow.parquet",
    "_precomputed_wholesale.parquet",
    "_precomputed_loss.parquet",
    # 字段说明：agent 靠它知道每列是什么
    "DATA_README.md",
]

PROBLEM = """在生鲜超市中，蔬菜类商品的保鲜期较短，品相随销售时间增加而变差。超市通常采用动态定价策略和限时折扣来促进销售，同时需要根据历史销售数据制定合理的补货计划。

某超市拥有多家门店，经营各类蔬菜商品。蔬菜的采购成本相对稳定，但销售价格需要根据市场供求、品相变化和保质期动态调整。对于保鲜期临近的蔬菜，超市通常会采取限时折扣以促进销售、减少损耗。

请建立数学模型解决以下问题：
问题1：分析蔬菜各品类及单品的销售量分布规律及相互关系。
问题2：建立蔬菜品类的定价模型，给出各品类未来一周的日补货总量和定价策略。
问题3：在满足最小陈列量要求的前提下，确定单品补货量和定价策略。
问题4：收集更多数据，优化模型并给出改进建议。

【附件】已上传到沙箱工作目录，直接用文件名读取：
- attachment1_products.xlsx：单品分类（product_code, product_name, category_code, category_name）
- attachment2_sales.parquet：销售明细流水（销售日期、扫码销售时间、单品编码、销量、销售单价、销售类型、是否打折）
- attachment3_wholesale.xlsx：批发价（date, product_code, wholesale_price）
- attachment4_loss.xlsx：损耗率（category_code, category_name, loss_rate）
- _precomputed_category_daily.parquet / _precomputed_product_daily.parquet：品类级/单品级日聚合（date, code, volume, revenue, transactions, avg_price）
- _precomputed_category_stats.parquet / _precomputed_product_stats.parquet：品类级/单品级汇总统计
- _precomputed_dow.parquet：周内效应；_precomputed_wholesale.parquet / _precomputed_loss.parquet：批发价与损耗率（整理版）
- DATA_README.md：各文件字段说明

明细流水约 87.8 万行，聚合表已预先算好，优先用聚合表；需要单品级明细时再读 attachment2_sales.parquet。
"""

README = """# 答辩演示材料

打开 `上传这些文件/` → **Ctrl+A** → 拖进前端上传框。题目在 `题目.txt`，复制粘贴。

## 三步跑起来

1. **先登录**（右上有头像）。不登录任务会落在访客桶，登录后反而看不见。
2. 进「方案模式」→ 把 `题目.txt` 全文粘进输入框 → 把 `上传这些文件/` 里
   **12 个文件全选拖进去** → 发送。
3. 等它跑完（约 10–15 分钟）。之后在**右栏「历史任务」**里能找到这条任务。

> 主演示不要现场等 10 分钟。演示时先提一道**轻量题**证明「它真在跑」
> （90 秒能看到前几个节点），再切到提前跑好的任务讲完整链路。
> 详见 `演示稿/`。

## 目录

| 路径 | 用途 |
|------|------|
| `上传这些文件/` | **12 个附件，扁平无子目录**——打开全选直接拖 |
| `题目.txt` | 全选复制，粘进方案模式输入框 |
| `演示稿/` | 完整底稿（含 18 问专家问答预案）+ 一页速查卡 |
| `备用素材/` | 断网或跑挂时的兜底：论文、4 张图表、2 MB 交付包、粒子群动画 GIF |

## 不想等那么久？

`上传这些文件/` 里的 `attachment2_sales.parquet`（11.5 MB，87.8 万行明细）
是**可选**的——它让问题 3 的「单品级」分析能做全，但读数慢。
只留另外 11 个聚合文件也能覆盖问题 1/2 的主要分析，跑得更快。

## 提前跑好的任务

| 项 | 值 |
|----|----|
| task_id | **`9ad383ce`** |
| 归属 | `zhang66633`（**必须登录**才看得到） |
| 状态 | completed |
| 论文 | 44,204 字符 |
| 图表 | 4 张 |
| 事件 | 764 条 |
| 产品 | 12 个 CSV + 2.02 MB 交付包 |

> 这一跑的关键区别：**数据预处理 agent 真的执行了**，agent 读写的是真实竞赛数据
> （沙箱日志里能看到它列出工作目录的 `attachment1_products.xlsx` 等文件）。
> 更早几跑因附件根本没进流水线，求解 agent 被告知「没有预挂载数据文件」
> 而**构造模拟数据**——论文里的数字是编的。这条已于 2026-10-14 修复。
>
> 另一处可直接指着讲的亮点：这一跑的节点序列里出现了
> `verification_agent → modeling_agent` 的**回退**（验证不通过，带原因重新建模）。

## 已修复的相关缺陷（2026-10-14）

演示前踩出来的，都值得当「工程深度」讲：

1. **附件从未真正进入流水线**：`create_initial_state` 不收 `data_files`，
   且 `retrieve_knowledge` 会用空列表把它覆盖回去 → 数据预处理被恒跳过、
   求解 agent 转而编数据。已修（增量合并 + 任务级 `_inputs/` 自动挂载）。
2. **长题面撞穿模型上下文上限**：`problem_raw` 含附件摘要时超 8192 token，
   向量检索与情景记忆各 400 一次。已加检索 query 截断。
3. **方案任务只能增不能删**：`/api/tasks` 无 DELETE，前端删的只是会话。
   已加 `DELETE /api/tasks/{task_id}`（属主校验 + 联动清理磁盘产物）。
4. **后台任务被 GC 回收**：`asyncio.create_task` 返回值无人持有 → 任务建成功
   却永远 `running`、0 条消息。已加强引用集合。
"""


def main() -> int:
    if not SRC.exists():
        print(f"!! 数据源不存在: {SRC}")
        return 1

    # 迁移：旧版把备用素材放在 `04_备用素材/`，新版改叫 `备用素材/`。
    # 先搬再删，别把刚刷新过的论文/图表/交付包丢掉。
    old_backup = KIT / "04_备用素材"
    new_backup = KIT / "备用素材"
    if old_backup.is_dir():
        new_backup.mkdir(parents=True, exist_ok=True)
        for item in old_backup.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(old_backup)
            dst = new_backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(item, dst)
        print(f"已从 04_备用素材/ 迁移 {len(list(new_backup.rglob('*')))} 项到 备用素材/")

    # 清掉旧结构（上一版有 01_/02_/03_/04_ 编号目录与子目录）
    if KIT.exists():
        for stale in KIT.iterdir():
            if stale.name not in ("上传这些文件", "演示稿", "备用素材", "README.md", "题目.txt"):
                if stale.is_dir():
                    shutil.rmtree(stale, ignore_errors=True)
                else:
                    stale.unlink()
        for old in ("01_题目文本.txt", "02_数据文件", "03_演示稿"):
            p = KIT / old
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()

    for d in (UPLOAD_DIR, SCRIPT_DIR, BACKUP_DIR, CHARTS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # 上传目录：只放要上传的文件，清掉一切杂项
    for stale in UPLOAD_DIR.iterdir():
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
        else:
            stale.unlink()

    n_ok = 0
    total = 0
    for name in UPLOAD_FILES:
        src = SRC / name
        if not src.exists():
            print(f"  !! 缺 {name}")
            continue
        dst = UPLOAD_DIR / name
        shutil.copy2(src, dst)
        n_ok += 1
        total += dst.stat().st_size
    print(f"上传目录: {n_ok} 个文件 / {total/1e6:.2f} MB")

    # 题目与 README
    (KIT / "题目.txt").write_text(PROBLEM, encoding="utf-8")
    (KIT / "README.md").write_text(README, encoding="utf-8")

    # 演示稿
    for name in ("defense-demo.md", "答辩速查卡.md"):
        src = DOCS / name
        if src.exists():
            shutil.copy2(src, SCRIPT_DIR / name)
        else:
            print(f"  !! 缺 docs/{name}")

    # 备用素材：保留已刷新过的那份（论文/图表/交付包/GIF），只补缺
    backup = DESKTOP / "答辩备用"
    if backup.exists():
        for name in ("pso_demo.gif",):
            src = backup / name
            if src.exists() and not (BACKUP_DIR / name).exists():
                shutil.copy2(src, BACKUP_DIR / name)

    print("\n=== 最终结构 ===")
    grand = 0
    for p in sorted(KIT.rglob("*")):
        rel = p.relative_to(KIT)
        indent = "  " * (len(rel.parts) - 1)
        if p.is_dir():
            print(f"{indent}[{rel.name}/]")
        else:
            grand += p.stat().st_size
            print(f"{indent}{p.stat().st_size:>12,}  {rel.name}")
    print(f"\n合计 {grand:,} B（{grand/1e6:.2f} MB）")
    print(f"\n>>> 上传用: {UPLOAD_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
