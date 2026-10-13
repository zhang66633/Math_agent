# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 坐标轴去掉上、右边框，保留论文图常用的清爽柱状图样式。
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.8,
            "figure.facecolor": "white",
        }
    )

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：模型评分均值和标准差，运行时可替换为真实评估结果。
    models = ["灰色预测", "ARIMA", "随机森林", "LSTM", "融合方案"]
    scores = np.array([0.71, 0.76, 0.83, 0.87, 0.92])
    std = np.array([0.018, 0.015, 0.013, 0.011, 0.010])
    colors = ["#A9B8D4", "#8FA7C9", "#6B8FB8", "#D9B8C4", "#C77089"]

    fig, ax = plt.subplots(figsize=(9, 5.8))
    bars = ax.bar(
        models,
        scores,
        yerr=std,
        color=colors,
        capsize=5,
        width=0.68,
        edgecolor="#4A4A4A",
        linewidth=0.8,
        error_kw={"elinewidth": 1.6, "capthick": 1.6},
    )

    ax.set_ylabel("综合评分", fontsize=13)
    ax.set_xlabel("候选模型", fontsize=13)
    ax.set_ylim(0.64, 0.96)
    ax.grid(axis="y", linestyle="--", linewidth=0.8, alpha=0.28)

    for bar, value, err in zip(bars, scores, std):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + err + 0.006,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=11,
            color="#333333",
            fontweight="bold",
        )


    fig.tight_layout()
    return fig
