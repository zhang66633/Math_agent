---
name: chart-standards
description: 论文级图表规范：中文标注、线型与标记双重区分（灰度可辨）、字号与单位、dpi 与边距、按数据特征选图型、禁止清单。
agents:
  - solving
  - data_preprocessing
priority: 30
---

# 论文级图表规范

目标：出图**能被评委直接看懂、能被灰度打印、能被正文引用**。以下每条都对应真实扣分点。

## 一、语言：中文论文的图必须中文标注

论文正文是中文，图里的标题、轴标签、图例、注释**一律用中文**（变量符号可保留数学写法）。中英文混排是被一眼看穿的扣分项。

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False   # 不设则负号显示为方块
plt.rcParams["font.size"] = 11               # 全局字号 ≥ 10，缩印后仍可读
```

## 二、区分手段：颜色 + 线型/标记，双重编码

只用颜色区分，灰度打印时会退化成同一条线。每条曲线同时指定**颜色 + 线型 + 标记**：

```python
STYLE = [
    dict(color="#1A6FC4", linestyle="-",  marker="o", markersize=4),
    dict(color="#E53935", linestyle="--", marker="s", markersize=4),
    dict(color="#2E9E44", linestyle="-.", marker="^", markersize=4),
    dict(color="#6A1B9A", linestyle=":",  marker="D", markersize=4),
]
# 用法：ax.plot(x, y, label="方案一", linewidth=1.6, **STYLE[0])
```

配色只用一套主色板（同一变量在所有图里同色）；**避免浅黄、浅青等浅色**——灰阶下几乎消失。

## 三、要素齐全（缺一项就是不合格的图）

- 轴标签**带单位**：`ax.set_xlabel("原料 A 供应量 $b_A$（单位）")`；
- 有图例（多曲线时），`ax.legend(frameon=False)`；
- 去掉上、右两条边框：`ax.spines[["top", "right"]].set_visible(False)`；
- 关键点直接标注数值（最优点、阈值、拐点）；
- 多子图用 `plt.subplots(1, 2, figsize=(11, 4.2))`，子图标题写清各自看什么；
- 保存：`fig.savefig(path, dpi=300, bbox_inches="tight")` —— **dpi 低于 300 打印会糊**。

## 四、按数据特征选图型（别一把梭全用折线）

| 数据/目的 | 该用的图 | 不该用的 |
|-----------|----------|----------|
| 方案/对象排序比较 | 横向条形图（Top-N 高亮，标数值） | 饼图（>3 项不可读） |
| 单参数扫描、灵敏度 | 折线（标出基准线与不变区间阴影） | 只有一根柱子的柱状图 |
| 两参数交互 | 热力图/等高线（关键等值线标数值） | 3D 曲面（投影后读数不准） |
| 收敛过程 | 迭代-目标曲线（可加对数纵轴） | 散点连成的锯齿线 |
| 分布比较 | 箱线图 / 小提琴图并排 | 叠加多条直方图 |
| 相关性 | 热力图 `cmap="RdBu_r", center=0, vmin=-1, vmax=1` | 默认配色（正负语义错乱） |
| 拟合与误差 | 拟合曲线 + 残差子图并列 | 只画拟合线不给残差 |
| 时间序列预测 | 历史+预测分段着色，标注预测区间 | 预测段与历史段同色 |

## 五、禁止清单

- ❌ 默认配色直接出图（无配色方案、无区分度）；
- ❌ 3D 饼图/3D 柱状图、无意义装饰；
- ❌ 截图或屏幕截图当插图（必须由代码 `savefig` 生成）；
- ❌ 图里出现英文标题/轴标签（中文论文场景）；
- ❌ 一张图里塞 6 条以上曲线（读者无法分辨，拆图或选代表性曲线）；
- ❌ 图上没有单位、没有图例、没有数值标注的"三无"图。
