# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # Tornado 图以正负双色和零轴突出参数扰动方向。
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.4,
            "figure.facecolor": "white",
        }
    )

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：参数扰动对目标函数的正负影响。
    factors = np.array(["单位运输成本", "需求波动", "安全库存系数", "装载率", "配送时窗", "司机可用率", "油价系数", "缺货惩罚"])
    effects = np.array([-0.31, 0.27, 0.18, -0.12, 0.22, 0.09, -0.15, 0.34])
    order = np.argsort(np.abs(effects))
    factors = factors[order]
    effects = effects[order]
    colors = ["#7C8FBD" if value < 0 else "#C46E8A" for value in effects]

    fig, ax = plt.subplots(figsize=(8.8, 5.9))
    ax.barh(factors, effects, color=colors, edgecolor="#4A4A4A", linewidth=0.5)
    ax.axvline(0, color="#666666", lw=1.1)
    ax.set_xlabel("目标函数变化率")
    x_padding = max(abs(effects.min()), abs(effects.max())) * 0.25
    ax.set_xlim(effects.min() - x_padding, effects.max() + x_padding)
    ax.margins(y=0.12)
    ax.grid(axis="x", linestyle="--", alpha=0.22)

    for idx, value in enumerate(effects):
        offset = 0.02 if value >= 0 else -0.02
        ha = "left" if value >= 0 else "right"
        ax.text(value + offset, idx, f"{value:+.2f}", va="center", ha=ha, fontsize=10, color="#333333", clip_on=False)

    fig.tight_layout(rect=(0.03, 0, 0.985, 1))
    return fig
