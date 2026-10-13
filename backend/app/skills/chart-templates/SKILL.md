---
name: chart-templates
description: 14 类论文图表的可直接运行绘图模板（折线/条形/热力图/散点回归/箱线/双轴/多子图/网络图/雷达/预测区间/龙卷风敏感度等），每类含 apply_chart_style + create_chart 两个入口，替换示例数据即可用。
agents:
  - solving
  - data_preprocessing
priority: 25
---

# 论文图表模板库

出图的**规范**（中文标注、双重编码、dpi≥300、禁止清单）见 `chart-standards` 技能，必须先遵守。
本技能给**能直接跑的代码骨架**：每个模板都是 `apply_chart_style()` + `create_chart()` 两个入口，
把示例数据换成你的变量即可，风格与布局不用重写。

完整 14 个模板在 `backend/app/skills/chart-templates/templates/<图型>.py`（与本技能同目录），
下面列出索引；正文只放最常用的两个完整代码，其余按需查阅同目录文件。

## 一、图型索引（按数据特征选，别一把梭全用折线）

| 文件 | 图型 | 适用场景 |
|------|------|----------|
| `line_chart.py` | 折线图 ✅正文含完整代码 | 单参数扫描/灵敏度、收敛过程、时间序列；带估计区间阴影 |
| `heatmap.py` | 热力图 ✅正文含完整代码 | 两参数交互、相关性矩阵（`vmin=-1, vmax=1`） |
| `bar_chart.py` | 条形图 | 方案/对象排序比较，Top-N 高亮 |
| `grouped_bar_chart.py` | 分组条形图 | 多方案 × 多指标并排比较 |
| `stacked_bar_chart.py` | 堆叠条形图 | 构成比例随类别/时间变化（一次出**两张**：绝对值 + 百分比） |
| `scatter_regression.py` | 散点+回归 | 相关性与拟合，可带置信带 |
| `bubble_chart.py` | 气泡图 | 三维信息（x、y、点大小） |
| `box_violin.py` | 箱线/小提琴图 | 分布比较、多组离散度 |
| `dual_axis_chart.py` | 双轴图 | 量纲不同的两条曲线同图（慎用，易误读） |
| `multi_panel_combined.py` | 多子图组合 | 一屏并列多个视角 |
| `network_graph.py` | 网络图 | 图论/关系网络结构 |
| `radar_chart.py` | 雷达图 | 多维指标综合对比（≤6 维，否则不可读） |
| `prediction_interval.py` | 预测区间图 | 历史 + 预测 + 不确定性带 |
| `tornado_sensitivity.py` | 龙卷风图 | 单因素敏感度排序（哪几个参数最要紧） |

## 二、折线图（`line_chart.py` 完整代码）

```python
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    plt.rcParams.update({
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 1.6,
        "figure.facecolor": "white",
    })

def create_chart() -> plt.Figure:
    apply_chart_style()
    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    # 三条曲线：颜色 + 线型 + 标记三重区分（灰度打印仍可辨）
    ax.plot(x, actual,    color="#6F86B6", marker="o", lw=2.2, ms=5.2, label="历史观测")
    ax.plot(x, fitted,    color="#C8B1BC", marker="s", lw=2.0, ms=4.8, linestyle="--", label="基线拟合")
    ax.plot(x, optimized, color="#C46E8A", marker="^", lw=2.2, ms=5.4, label="优化策略")
    # 估计区间用阴影带，不要画成误差棒森林
    ax.fill_between(x, fitted - m1, fitted + m1, color="#C8B1BC", alpha=0.10, linewidth=0)
    ax.set_xlabel("月份"); ax.set_ylabel("月度需求量 / 万件")
    ax.grid(axis="y", linestyle="--", linewidth=0.75, alpha=0.18)
    ax.axhline(160, color="#767676", lw=1.0, linestyle="--", alpha=0.45, zorder=0)  # 基准线
    fig.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.82, 0.93))
    fig.tight_layout(rect=(0.02, 0, 0.82, 1))
    return fig
```

## 三、热力图（`heatmap.py` 完整代码）

```python
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

def create_chart() -> plt.Figure:
    sns.set_theme(style="white")
    fig, ax = plt.subplots(figsize=(7.8, 6.2))
    sns.heatmap(
        matrix,                      # 你的相关系数/交互矩阵
        annot=True, fmt=".2f",       # 格子里标数值，否则读者读不出
        cmap=sns.diverging_palette(250, 8, as_cmap=True),
        vmin=-1, vmax=1,             # 固定量纲，正负语义才不错乱
        square=True, linewidths=0.8, linecolor="white",
        cbar_kws={"shrink": 0.85, "label": "相关系数"},
        xticklabels=labels, yticklabels=labels, ax=ax,
    )
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    return fig
```

## 四、使用要点

- **只换数据不换风格**：模板里的配色、线型、标记、留白已经按论文标准调过，改数据即可；
  要改配色就整套换，别单改一条曲线的颜色（同一变量在所有图里必须同色）。
- **返回契约**：`create_chart()` 返回一个 `Figure`；`stacked_bar_chart` 一次出两张
  （绝对值 + 百分比），返回 `(fig1, fig2)`——调用时按可迭代处理即可。
- **保存**：`fig.savefig(path, dpi=300, bbox_inches="tight")`——dpi 低于 300 打印会糊。
- **中文**：模板不设字体（由运行环境决定）。沙箱内已配 `Noto Sans CJK SC`/`Microsoft YaHei` 等
  中文字体回退列表；若出现豆腐块，先查字体而不是改代码。
- **依赖**：除 matplotlib/numpy 外，`heatmap` 需 seaborn、`network_graph` 需 networkx
  （两者均已在 `pyproject.toml` 与 `Dockerfile.sandbox` 中声明）。
- **同目录文件**：`templates/` 下 14 个 `.py` 与正文两个模板同构，直接读来用。
