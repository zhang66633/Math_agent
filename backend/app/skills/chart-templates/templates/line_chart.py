# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 折线图去掉冗余边框，用阴影带表达估计区间。
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.6,
            "figure.facecolor": "white",
        }
    )

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：历史观测、基线拟合和优化策略三条趋势线。
    months = np.arange(1, 13)
    actual = np.array([118, 124, 129, 141, 155, 164, 172, 181, 177, 168, 154, 146])
    fitted = np.array([116, 123, 131, 139, 151, 162, 170, 179, 175, 166, 156, 148])
    optimized = np.array([119, 126, 133, 145, 160, 171, 181, 189, 186, 178, 166, 158])
    fitted_margin = np.array([1.6, 1.4, 1.5, 1.8, 1.7, 1.6, 1.4, 1.5, 1.4, 1.5, 1.6, 1.7])
    optimized_margin = np.array([1.8, 1.7, 1.8, 2.0, 2.0, 1.9, 1.8, 1.8, 1.7, 1.8, 1.9, 2.0])

    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    actual_line = ax.plot(months, actual, color="#6F86B6", marker="o", lw=2.2, ms=5.2, label="历史观测")[0]
    fitted_line = ax.plot(months, fitted, color="#C8B1BC", marker="s", lw=2.0, ms=4.8, linestyle="--", label="基线拟合")[0]
    optimized_line = ax.plot(months, optimized, color="#C46E8A", marker="^", lw=2.2, ms=5.4, label="优化策略")[0]
    ax.fill_between(months, fitted - fitted_margin, fitted + fitted_margin, color="#C8B1BC", alpha=0.10, linewidth=0, zorder=1)
    ax.fill_between(months, optimized - optimized_margin, optimized + optimized_margin, color="#C46E8A", alpha=0.08, linewidth=0, zorder=1)

    ax.set_xlabel("月份")
    ax.set_ylabel("月度需求量 / 万件")
    ax.set_xticks(months)
    ax.set_xlim(0.5, 12.4)
    ax.set_ylim(min(actual.min(), fitted.min(), optimized.min()) - 4, max(actual.max(), fitted.max(), optimized.max()) + 3)
    ax.set_yticks([120, 140, 160, 180, 190])
    ax.grid(axis="y", linestyle="--", linewidth=0.75, alpha=0.18)
    ax.axhline(160, color="#767676", lw=1.0, linestyle="--", alpha=0.45, zorder=0)
    fig.legend([actual_line, fitted_line, optimized_line], ["历史观测", "基线拟合", "优化策略"], frameon=False, ncol=1, loc="upper left", bbox_to_anchor=(0.82, 0.93))

    fig.tight_layout(rect=(0.02, 0, 0.82, 1))
    return fig
