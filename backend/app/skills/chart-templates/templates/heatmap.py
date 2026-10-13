# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

def apply_chart_style() -> None:
    # 热力图使用白底和清晰分隔线，突出相关系数矩阵结构。
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.linewidth": 1.2,
            "figure.facecolor": "white",
        }
    )
    sns.set_theme(style="white")

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：指标间相关系数矩阵。
    labels = ["成本", "时效", "库存", "服务率", "碳排放", "收益"]
    matrix = np.array(
        [
            [1.00, -0.61, 0.48, -0.36, 0.42, -0.55],
            [-0.61, 1.00, -0.29, 0.58, -0.33, 0.64],
            [0.48, -0.29, 1.00, -0.22, 0.37, -0.14],
            [-0.36, 0.58, -0.22, 1.00, -0.31, 0.72],
            [0.42, -0.33, 0.37, -0.31, 1.00, -0.41],
            [-0.55, 0.64, -0.14, 0.72, -0.41, 1.00],
        ]
    )

    fig, ax = plt.subplots(figsize=(7.8, 6.2))
    sns.heatmap(
        matrix,
        annot=True,
        fmt=".2f",
        cmap=sns.diverging_palette(250, 8, as_cmap=True),
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=0.8,
        linecolor="white",
        cbar_kws={"shrink": 0.85, "label": "相关系数"},
        xticklabels=labels,
        yticklabels=labels,
        ax=ax,
    )
    ax.tick_params(axis="x", rotation=25)
    ax.tick_params(axis="y", rotation=0)

    fig.tight_layout()
    return fig
