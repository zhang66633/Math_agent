# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

RNG_SEED = 21

def apply_chart_style() -> None:
    # 白底网格让箱线图和小提琴图的分布差异更容易比较。
    plt.rcParams.update(
        {
            "font.size": 10.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.4,
            "figure.facecolor": "white",
        }
    )
    sns.set_theme(style="whitegrid")

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：固定随机种子生成分布，保持预览图可复现。
    rng = np.random.default_rng(RNG_SEED)
    groups = ["方案A", "方案B", "方案C", "方案D"]
    data = {
        "方案A": rng.normal(72, 6, 80),
        "方案B": rng.normal(78, 5, 80),
        "方案C": rng.normal(83, 4, 80),
        "方案D": rng.normal(87, 4.5, 80),
    }

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 5.6), sharey=True)
    palette = ["#A5B6D6", "#7C8FBD", "#D8C3CC", "#C46E8A"]

    sns.boxplot(data=[data[g] for g in groups], palette=palette, width=0.55, ax=axes[0], linewidth=1.1, fliersize=2.5)
    axes[0].set_xlabel("策略方案")
    axes[0].set_ylabel("综合得分")
    axes[0].set_xticks(range(len(groups)))
    axes[0].set_xticklabels(groups)
    axes[0].text(0.02, 0.96, "(a)", transform=axes[0].transAxes, ha="left", va="top", fontsize=11.2, fontweight="bold")

    sns.violinplot(data=[data[g] for g in groups], palette=palette, inner="quartile", cut=0, linewidth=1.0, ax=axes[1])
    axes[1].set_xlabel("策略方案")
    axes[1].set_xticks(range(len(groups)))
    axes[1].set_xticklabels(groups)
    axes[1].text(0.02, 0.96, "(b)", transform=axes[1].transAxes, ha="left", va="top", fontsize=11.2, fontweight="bold")

    fig.tight_layout()
    return fig
