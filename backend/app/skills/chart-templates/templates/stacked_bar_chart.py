# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import numpy as np

def apply_chart_style() -> None:
    # 堆叠柱图通过色块和纹理区分结构，适合灰度打印场景。
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 1.5,
            "figure.facecolor": "white",
        }
    )

def plot_absolute(regions: list[str], categories: list[str], values: np.ndarray, colors: list[str]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(11.2, 6.1))
    bottom = np.zeros(len(regions))
    hatches = ["", "//", "..", "xx"]

    for idx, (category, color, hatch) in enumerate(zip(categories, colors, hatches)):
        bars = ax.bar(
            regions,
            values[idx],
            bottom=bottom,
            color=color,
            label=category,
            width=0.62,
            edgecolor="#FFFFFF",
            linewidth=0.8,
        )
        for patch in bars:
            patch.set_hatch(hatch)
        bottom += values[idx]

    ax.set_ylabel("运输量 / 万吨")
    ax.set_ylim(0, values.sum(axis=0).max() * 1.08)
    ax.grid(axis="y", linestyle="--", alpha=0.22)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncol=1, loc="upper left", bbox_to_anchor=(0.84, 0.93))

    fig.tight_layout(rect=(0, 0, 0.83, 1))
    return fig

def plot_percent(regions: list[str], categories: list[str], values: np.ndarray, colors: list[str]) -> plt.Figure:
    percent = values / values.sum(axis=0, keepdims=True)
    fig, ax = plt.subplots(figsize=(11.2, 6.1))
    bottom = np.zeros(len(regions))
    hatches = ["", "//", "..", "xx"]

    for idx, (category, color, hatch) in enumerate(zip(categories, colors, hatches)):
        series = percent[idx] * 100
        bars = ax.bar(
            regions,
            series,
            bottom=bottom,
            color=color,
            label=category,
            width=0.62,
            edgecolor="#FFFFFF",
            linewidth=0.8,
        )
        for patch in bars:
            patch.set_hatch(hatch)
        bottom += series

    ax.set_ylabel("占比 / %")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.22)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncol=1, loc="upper left", bbox_to_anchor=(0.84, 0.93))

    fig.tight_layout(rect=(0, 0, 0.83, 1))
    return fig

def create_chart() -> tuple[plt.Figure, plt.Figure]:
    apply_chart_style()

    # 示例数据：四个区域、四类运输方式的结构数据。
    regions = ["华北", "华东", "华中", "华南"]
    categories = ["公路", "铁路", "水运", "航空"]
    values = np.array(
        [
            [62, 75, 58, 54],
            [34, 42, 39, 31],
            [18, 36, 24, 41],
            [6, 9, 7, 12],
        ]
    )
    colors = ["#A5B6D6", "#7C8FBD", "#D8C3CC", "#C46E8A"]

    absolute_fig = plot_absolute(regions, categories, values, colors)
    percent_fig = plot_percent(regions, categories, values, colors)
    return absolute_fig, percent_fig
