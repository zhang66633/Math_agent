# 该文件用于运行时 agent 注入，只保留与图像风格、布局和绘制逻辑强相关的代码。
import matplotlib.pyplot as plt
import networkx as nx

def apply_chart_style() -> None:
    # 网络图以节点大小和边宽表达权重，画布保持白底。
    plt.rcParams.update(
        {
            "font.size": 10.5,
            "figure.facecolor": "white",
        }
    )

def create_chart() -> plt.Figure:
    apply_chart_style()

    # 示例数据：节点大小表示重要度，边权表示协同强度。
    graph = nx.Graph()
    nodes = {
        "供应商A": 820,
        "供应商B": 730,
        "工厂": 1200,
        "华北仓": 920,
        "华东仓": 980,
        "华南仓": 900,
        "电商": 760,
        "商超": 760,
        "直营": 700,
    }
    graph.add_nodes_from(nodes.keys())
    weighted_edges = [
        ("供应商A", "工厂", 3.5),
        ("供应商B", "工厂", 2.9),
        ("工厂", "华北仓", 3.2),
        ("工厂", "华东仓", 3.8),
        ("工厂", "华南仓", 2.7),
        ("华北仓", "电商", 2.2),
        ("华东仓", "商超", 2.6),
        ("华南仓", "直营", 2.0),
        ("华东仓", "电商", 1.6),
        ("华北仓", "商超", 1.4),
        ("华南仓", "商超", 1.2),
    ]
    graph.add_weighted_edges_from(weighted_edges)

    positions = {
        "供应商A": (-1.4, 0.8),
        "供应商B": (-1.4, -0.8),
        "工厂": (0.0, 0.0),
        "华北仓": (1.3, 1.0),
        "华东仓": (1.45, 0.0),
        "华南仓": (1.3, -1.0),
        "电商": (2.8, 1.1),
        "商超": (2.95, 0.0),
        "直营": (2.8, -1.1),
    }
    node_colors = ["#A5B6D6", "#A5B6D6", "#C46E8A", "#D8C3CC", "#D8C3CC", "#D8C3CC", "#7C8FBD", "#7C8FBD", "#7C8FBD"]

    fig, ax = plt.subplots(figsize=(10.4, 5.9))
    nx.draw_networkx_nodes(graph, positions, node_size=[nodes[n] for n in graph.nodes()], node_color=node_colors, alpha=0.92, edgecolors="white", linewidths=1.0, ax=ax)
    nx.draw_networkx_labels(graph, positions, font_size=10, font_color="#222222", ax=ax)
    nx.draw_networkx_edges(
        graph,
        positions,
        width=[data["weight"] for _, _, data in graph.edges(data=True)],
        edge_color="#8A8FA6",
        alpha=0.55,
        ax=ax,
    )
    edge_labels = {(u, v): f"{data['weight']:.1f}" for u, v, data in graph.edges(data=True)}
    nx.draw_networkx_edge_labels(graph, positions, edge_labels=edge_labels, font_size=8.5, font_color="#555555", rotate=False, ax=ax)
    ax.set_axis_off()

    fig.tight_layout()
    return fig
