# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 双轴图保留左侧和右侧轴线，方便同时读取规模与比例。
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.spines.top": False,
            "axes.linewidth": 1.5,
            "figure.facecolor": "white",
        }
    )

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：左轴显示订单规模，右轴显示履约质量。
    months = np.arange(1, 13)
    volume = np.array([86, 91, 95, 109, 121, 132, 138, 144, 141, 129, 118, 106])
    ontime = np.array([88.2, 89.0, 89.6, 90.4, 91.8, 92.7, 93.4, 94.1, 93.6, 92.9, 91.7, 90.3])
    ontime_low = ontime - np.array([0.35, 0.30, 0.28, 0.26, 0.25, 0.25, 0.22, 0.20, 0.21, 0.24, 0.27, 0.30])
    ontime_high = ontime + np.array([0.35, 0.30, 0.28, 0.26, 0.25, 0.25, 0.22, 0.20, 0.21, 0.24, 0.27, 0.30])

    fig, ax1 = plt.subplots(figsize=(10.8, 5.9))
    ax2 = ax1.twinx()

    bars = ax1.bar(months, volume, color="#A5B6D6", width=0.62, label="订单量")
    line = ax2.plot(months, ontime, color="#C46E8A", marker="o", lw=2.2, ms=5.0, label="准时交付率")[0]
    ax2.fill_between(months, ontime_low, ontime_high, color="#C46E8A", alpha=0.12, linewidth=0, zorder=1)

    ax1.set_xlabel("月份")
    ax1.set_ylabel("订单量 / 千单")
    ax2.set_ylabel("准时交付率 / %")
    ax1.set_xticks(months)
    ax1.set_xlim(0.45, 12.85)
    ax1.set_yticks([40, 80, 120, 140])
    ax1.grid(axis="y", linestyle="--", alpha=0.18)
    ax2.set_ylim(86.5, 95.15)
    ax2.axhline(92.0, color="#767676", lw=1.0, linestyle="--", alpha=0.5, zorder=0)

    handles = [bars, line]
    labels = ["订单量", "准时交付率"]
    fig.legend(handles, labels, frameon=False, ncol=1, loc="upper left", bbox_to_anchor=(0.82, 0.93))

    fig.tight_layout(rect=(0.02, 0, 0.82, 1))
    return fig
