# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

RNG_SEED = 42

def apply_chart_style() -> None:
    # 三联图共用克制的网格和边框，让子图在同一视觉体系内。
    plt.rcParams.update(
        {
            "font.size": 10.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.6,
            "figure.facecolor": "white",
        }
    )

def make_trend_panel(ax: plt.Axes) -> list:
    rng = np.random.default_rng(RNG_SEED)
    months = np.arange(1, 13)
    baseline = 48 + 20 * (1 - np.exp(-months / 4.5)) + rng.normal(0, 1.2, len(months))
    robust = baseline + np.linspace(1.5, 7.5, len(months))
    adaptive = baseline + np.linspace(3.0, 10.0, len(months))

    series = [
        ("基准策略", baseline, "#7C8FBD"),
        ("稳健策略", robust, "#D3B6C1"),
        ("自适应策略", adaptive, "#C46E8A"),
    ]
    handles = []
    for label, values, color in series:
        line = ax.plot(months, values, marker="o", lw=2.2, ms=4.8, color=color, label=label)[0]
        handles.append(line)

    all_values = np.concatenate([baseline, robust, adaptive])
    y_padding = (all_values.max() - all_values.min()) * 0.12
    ax.set_xlabel("月份")
    ax.set_ylabel("累计收益率 / %")
    ax.set_xticks(months)
    ax.set_xlim(0.6, 12.4)
    ax.set_ylim(all_values.min() - y_padding, all_values.max() + y_padding)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ax.text(0.02, 0.96, "(a)", transform=ax.transAxes, ha="left", va="top", fontsize=11.5, fontweight="bold")
    return handles

def make_grouped_panel(ax: plt.Axes) -> None:
    scenarios = ["低扰动", "中扰动", "高扰动"]
    policies = ["固定阈值", "滚动优化", "本文策略"]
    values = np.array(
        [
            [82, 78, 69],
            [88, 84, 76],
            [93, 90, 85],
        ]
    )
    colors = ["#A5B6D6", "#7C8FBD", "#C46E8A"]
    x = np.arange(len(scenarios))
    width = 0.22

    for idx, (policy, color) in enumerate(zip(policies, colors)):
        ax.bar(x + (idx - 1) * width, values[idx], width=width, color=color, label=policy)

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.set_ylabel("任务完成率 / %")
    ax.set_xlim(-0.55, len(scenarios) - 0.45)
    ax.set_ylim(58, 98)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ax.text(0.02, 0.96, "(b)", transform=ax.transAxes, ha="left", va="top", fontsize=11.5, fontweight="bold")

def make_sensitivity_panel(ax: plt.Axes) -> None:
    factors = ["需求波动系数", "运输成本权重", "仓储上限", "响应时间约束", "缺货惩罚"]
    impacts = np.array([0.41, 0.32, -0.18, -0.27, 0.36])
    colors = ["#C46E8A" if value > 0 else "#7C8FBD" for value in impacts]

    ax.barh(factors, impacts, color=colors, edgecolor="#4A4A4A", linewidth=0.5)
    ax.axvline(0, color="#555555", lw=1.0)
    ax.set_xlabel("目标函数变化率")
    x_padding = max(abs(impacts.min()), abs(impacts.max())) * 0.25
    ax.set_xlim(impacts.min() - x_padding, impacts.max() + x_padding)
    ax.margins(y=0.12)
    ax.grid(axis="x", linestyle="--", alpha=0.22)
    ax.text(0.02, 0.96, "(c)", transform=ax.transAxes, ha="left", va="top", fontsize=11.5, fontweight="bold")

    for idx, value in enumerate(impacts):
        ha = "left" if value > 0 else "right"
        offset = 0.02 if value > 0 else -0.02
        ax.text(value + offset, idx, f"{value:+.2f}", va="center", ha=ha, fontsize=9.8, color="#333333", clip_on=False)

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据分散在各子图函数中，组合成策略分析三联图。
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(16.8, 5.4),
        gridspec_kw={"width_ratios": [1.25, 1.0, 1.0], "wspace": 0.32},
    )

    handles = make_trend_panel(axes[0])
    make_grouped_panel(axes[1])
    make_sensitivity_panel(axes[2])

    fig.legend(
        handles,
        [h.get_label() for h in handles],
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.06),
        frameon=False,
    )

    fig.subplots_adjust(left=0.06, right=0.985, top=0.985, bottom=0.13, wspace=0.32)
    return fig
