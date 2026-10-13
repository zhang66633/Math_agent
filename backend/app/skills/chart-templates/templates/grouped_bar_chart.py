# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 分组柱图用较粗轴线和浅网格，强调多方法横向比较。
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.8,
            "figure.facecolor": "white",
        }
    )

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：多方法在多指标上的归一化得分。
    metrics = ["拟合优度", "泛化稳定性", "求解速度", "解释性"]
    methods = ["线性规划", "随机森林", "XGBoost", "BiLSTM", "本文方案"]
    values = np.array(
        [
            [0.72, 0.75, 0.81, 0.84],
            [0.78, 0.79, 0.68, 0.63],
            [0.84, 0.86, 0.73, 0.66],
            [0.87, 0.88, 0.61, 0.58],
            [0.91, 0.93, 0.79, 0.82],
        ]
    )
    errors = np.array(
        [
            [0.018, 0.014, 0.021, 0.015],
            [0.013, 0.012, 0.018, 0.014],
            [0.010, 0.009, 0.016, 0.012],
            [0.009, 0.008, 0.017, 0.013],
            [0.008, 0.007, 0.012, 0.010],
        ]
    )
    colors = ["#5B6C9C", "#7C8FBD", "#A6B6D4", "#D8C3CC", "#C46E8A"]

    x = np.arange(len(metrics))
    width = 0.14

    fig, ax = plt.subplots(figsize=(11.8, 6.2))

    for idx, (method, color) in enumerate(zip(methods, colors)):
        ax.bar(
            x + (idx - 2) * width,
            values[idx],
            width=width,
            label=method,
            color=color,
            yerr=errors[idx],
            capsize=3.5,
            edgecolor="#4A4A4A",
            linewidth=0.6,
            error_kw={"elinewidth": 1.1, "capthick": 1.1},
        )

    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("归一化得分", fontsize=13)
    ax.set_ylim(0.45, 1.0)
    ax.grid(axis="y", linestyle="--", linewidth=0.75, alpha=0.25)

    legend = ax.legend(
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        frameon=False,
        fontsize=10.5,
        columnspacing=1.4,
        handletextpad=0.5,
    )
    for text in legend.get_texts():
        text.set_color("#333333")

    fig.subplots_adjust(bottom=0.24)

    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return fig
