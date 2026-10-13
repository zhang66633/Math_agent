# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

RNG_SEED = 7

def apply_chart_style() -> None:
    # 散点回归图用低饱和散点和强调色拟合线形成主次层级。
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

    # 示例数据：固定随机种子生成投入与产出关系。
    rng = np.random.default_rng(RNG_SEED)
    investment = np.linspace(2.0, 12.0, 28)
    response = 8.5 + 4.6 * investment + rng.normal(0, 4.2, size=investment.size)
    coefficients = np.polyfit(investment, response, 1)
    fitted = np.polyval(coefficients, investment)
    r2 = 1 - np.sum((response - fitted) ** 2) / np.sum((response - response.mean()) ** 2)

    fig, ax = plt.subplots(figsize=(8.4, 5.8))
    ax.scatter(investment, response, s=52, color="#7C8FBD", alpha=0.85, edgecolor="white", linewidth=0.6, label="样本点")
    ax.plot(investment, fitted, color="#C46E8A", lw=2.4, label="线性回归")
    ax.fill_between(investment, fitted - 6.0, fitted + 6.0, color="#E8CDD6", alpha=0.35, label="近似置信带")

    ax.set_xlabel("基础设施投入 / 百万元")
    ax.set_ylabel("区域产出提升 / %")
    ax.grid(True, linestyle="--", linewidth=0.75, alpha=0.25)
    ax.legend(frameon=False, loc="upper left")
    ax.text(0.97, 0.06, f"y = {coefficients[0]:.2f}x + {coefficients[1]:.2f}\n$R^2$ = {r2:.3f}", transform=ax.transAxes, ha="right", va="bottom", fontsize=10.5, color="#333333")

    fig.tight_layout()
    return fig
