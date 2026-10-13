# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 预测区间图用浅色置信带承载不确定性，主线保持高对比。
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

    # 示例数据：历史序列、预测均值和上下界。
    history_x = np.arange(1, 19)
    history_y = np.array([84, 87, 91, 96, 101, 105, 109, 111, 116, 119, 123, 126, 130, 133, 135, 139, 141, 144])
    future_x = np.arange(19, 25)
    pred = np.array([147, 151, 154, 158, 161, 164])
    lower = pred - np.array([5, 6, 6, 7, 7, 8])
    upper = pred + np.array([5, 6, 6, 7, 7, 8])

    fig, ax = plt.subplots(figsize=(9.4, 5.8))
    ax.plot(history_x, history_y, color="#6F86B6", marker="o", lw=2.2, ms=4.8, label="历史序列")
    ax.plot(future_x, pred, color="#C46E8A", marker="o", lw=2.2, ms=4.8, label="预测均值")
    ax.fill_between(future_x, lower, upper, color="#E8CDD6", alpha=0.45, label="95% 预测区间")
    ax.axvline(18.5, color="#666666", linestyle="--", linewidth=1.2)
    ax.text(18.65, history_y.min() + 2, "预测起点", fontsize=10.2, color="#555555")

    ax.set_xlabel("时间期数")
    ax.set_ylabel("需求量 / 万件")
    ax.grid(axis="y", linestyle="--", linewidth=0.75, alpha=0.25)
    ax.legend(frameon=False, loc="upper left")

    fig.tight_layout()
    return fig
