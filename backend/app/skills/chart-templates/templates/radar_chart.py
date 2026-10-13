# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 雷达图关闭默认极坐标网格，手工绘制环线以控制论文图质感。
    plt.rcParams.update(
        {
            "font.size": 10.8,
            "figure.facecolor": "white",
        }
    )

def close_loop(values: list[float]) -> list[float]:
    return values + [values[0]]

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：多方案在六类指标上的综合表现。
    metrics = ["准确率", "稳定性", "可解释性", "求解速度", "扩展性", "成本控制"]
    methods = {
        "基线模型": [0.76, 0.71, 0.82, 0.88, 0.69, 0.73],
        "增强模型": [0.84, 0.83, 0.77, 0.79, 0.85, 0.81],
        "本文方案": [0.91, 0.88, 0.85, 0.82, 0.89, 0.87],
    }
    colors = {"基线模型": "#7C8FBD", "增强模型": "#D8C3CC", "本文方案": "#C46E8A"}

    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False)
    angles_closed = np.append(angles, angles[0])
    radial_levels = [0.7, 0.8, 0.9, 1.0]

    fig = plt.figure(figsize=(7.8, 7.4))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_ylim(0.58, 1.08)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    outer_ring = np.full_like(angles_closed, 1.03, dtype=float)
    ax.plot(angles_closed, outer_ring, color="#4D4D4D", lw=1.0, zorder=1)
    for level in radial_levels:
        ax.plot(angles_closed, np.full_like(angles_closed, level, dtype=float), color="#D1D1D1", lw=0.8, zorder=1)
    for angle in angles:
        ax.plot([angle, angle], [0.6, 1.03], color="#D1D1D1", lw=0.8, zorder=1)

    for method, values in methods.items():
        closed = np.append(np.array(values), values[0])
        ax.plot(angles_closed, closed, color=colors[method], linewidth=2.2, label=method, zorder=4)
        ax.fill(angles_closed, closed, color=colors[method], alpha=0.12, zorder=3)
        ax.scatter(angles, values, color=colors[method], s=24, zorder=5)

    label_angle = np.deg2rad(22)
    for level in radial_levels:
        ax.text(
            label_angle,
            level,
            f"{level:.1f}",
            fontsize=9.5,
            color="#333333",
            ha="left",
            va="center",
            zorder=10,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.92, "pad": 0.2},
        )

    for angle, label in zip(angles, metrics):
        radius = 1.075 if abs(np.sin(angle)) < 0.25 else 1.095
        ax.text(
            angle,
            radius,
            label,
            fontsize=10.8,
            ha="center",
            va="center",
            clip_on=False,
            zorder=10,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.90, "pad": 0.25},
        )

    ax.legend(loc="upper right", bbox_to_anchor=(1.23, 1.08), ncol=1, frameon=False)

    fig.tight_layout(rect=(0.02, 0.02, 0.95, 0.98))
    return fig
