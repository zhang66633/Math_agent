# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 弱化坐标轴装饰，突出气泡大小、颜色和城市标签。
    plt.rcParams.update(
        {
            "font.size": 10.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.4,
            "figure.facecolor": "white",
        }
    )

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：成本、服务水平、规模和风险共同决定气泡编码。
    cities = ["北京", "上海", "广州", "深圳", "成都", "武汉", "西安", "杭州"]
    cost = np.array([7.1, 6.6, 5.9, 6.1, 4.8, 4.9, 4.4, 5.2])
    service = np.array([95.0, 96.2, 93.5, 94.6, 91.8, 92.4, 90.9, 93.1])
    volume = np.array([122, 135, 108, 118, 86, 91, 72, 95])
    risk = np.array([0.44, 0.38, 0.51, 0.47, 0.59, 0.54, 0.62, 0.49])

    fig, ax = plt.subplots(figsize=(9.0, 5.9))
    scatter = ax.scatter(cost, service, s=volume * 8, c=risk, cmap="RdPu", alpha=0.68, edgecolor="white", linewidth=0.8)

    x_pad = (cost.max() - cost.min()) * 0.12
    y_pad = (service.max() - service.min()) * 0.22
    ax.set_xlim(cost.min() - x_pad, cost.max() + x_pad)
    ax.set_ylim(service.min() - y_pad * 0.35, service.max() + y_pad)

    for x, y, label in zip(cost, service, cities):
        x_offset = 0.03 if x < cost.max() - 0.25 else -0.14
        y_offset = 0.08 if y < service.max() - 0.45 else 0.04
        ax.text(x + x_offset, y + y_offset, label, fontsize=9.7, color="#333333")

    ax.set_xlabel("单位履约成本 / 元")
    ax.set_ylabel("服务水平 / %")
    ax.grid(True, linestyle="--", alpha=0.2)
    cbar = fig.colorbar(scatter, ax=ax, shrink=0.86)
    cbar.set_label("风险指数")

    fig.tight_layout(rect=(0.02, 0, 0.985, 1))
    return fig
