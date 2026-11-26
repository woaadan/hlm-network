# -*- coding: utf-8 -*-
"""补充网络类图：分层网络、度分布、十年块快照、中心性热图。"""
import sys, io, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.colors import LinearSegmentedColormap

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_common import PROC, FIG, DOCS, setup_font, PAPER, INK, LAYER_COLOR, ROLE_COLOR, save_fig
from lib_layout import forceatlas2

setup_font()
persons = pd.read_csv(PROC / "persons.csv", encoding="utf-8-sig")
rels = pd.read_csv(PROC / "relations.csv", encoding="utf-8-sig")
nm = pd.read_csv(PROC / "node_metrics.csv", encoding="utf-8-sig")
sc = pd.read_csv(PROC / "cooccurrence_scene.csv", encoding="utf-8-sig")
pc = pd.read_csv(PROC / "person_chapter.csv", encoding="utf-8-sig")
S = json.load(open(PROC / "network_summary.json", encoding="utf-8"))

live = persons[persons["合并至"].isna() | (persons["合并至"] == "")]
pid = list(live["人物ID"])
name = dict(zip(live["人物ID"], live["标准名"]))
role = dict(zip(live["人物ID"], live["身份类别"]))
LAYERS = ["亲属关系", "主仆关系", "社会关系"]

G = nx.Graph(); G.add_nodes_from(pid)
for _, r in rels.iterrows():
    if r["主体ID"] in pid and r["客体ID"] in pid and r["主体ID"] != r["客体ID"]:
        G.add_edge(r["主体ID"], r["客体ID"], layer=r["关系大类"])

GT = nx.Graph(); GT.add_nodes_from(pid)
for _, r in sc[sc["同场次数"] >= 3].iterrows():
    GT.add_edge(r["a"], r["b"], weight=int(r["同场次数"]))

def save(fig, fn):
    save_fig(fig, fn)
    plt.close(fig)
    print("saved", fn)

giant = max(nx.connected_components(G), key=len)
H = G.subgraph(giant)
POS = forceatlas2(H, weight=None, iterations=700, seed=7)

# ---------------------------------------------------------------- 分层网络
def layers():
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 6.6))
    for ax, L in zip(axes, LAYERS):
        es = [(a, b) for a, b, d in H.edges(data=True) if d["layer"] == L]
        nx.draw_networkx_edges(H, POS, edgelist=list(H.edges()), edge_color="#d9cdb8",
                              width=0.6, alpha=0.55, ax=ax)
        nx.draw_networkx_edges(H, POS, edgelist=es, edge_color=LAYER_COLOR[L], width=1.7,
                              alpha=0.95, ax=ax)
        nodes = [n for n in H if H.degree(n) > 0]
        nx.draw_networkx_nodes(H, POS, nodelist=nodes, node_size=[18 + 10 * H.degree(n) for n in nodes],
                              node_color="#fffdf8", edgecolors="#a89a82", linewidths=0.7, ax=ax)
        active = {n for e in es for n in e}
        nx.draw_networkx_nodes(H, POS, nodelist=list(active),
                              node_size=[18 + 10 * H.degree(n) for n in active],
                              node_color=LAYER_COLOR[L], edgecolors="white", linewidths=0.6,
                              alpha=0.92, ax=ax)
        for n in ("HLM-P001", "HLM-P004", "HLM-P003", "HLM-P010"):
            if n in POS:
                ax.text(POS[n][0], POS[n][1], name[n], fontsize=8, ha="center", va="center",
                        zorder=10, path_effects=[__import__("matplotlib.patheffects", fromlist=["x"])
                                                 .withStroke(linewidth=2.4, foreground=PAPER)])
        ax.set_axis_off()
        ax.set_title("%s　%d 人 / %d 条边" % (L, len(active), len(es)), fontsize=13, pad=8)
    fig.suptitle("同一布局下切开的三层：亲属是骨架，主仆是枝叶，社会关系只是几条细线", fontsize=15, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, "fig12_layers.png")

# ---------------------------------------------------------------- 度分布
def degree_dist():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.8))
    for Gx, lab, c in [(G, "关系网络", "#a4342a"), (GT, "文本同场网络", "#3d6a8f")]:
        ks = np.array([d for _, d in Gx.degree() if d > 0])
        vals, cnts = np.unique(ks, return_counts=True)
        ax1.scatter(vals, cnts / cnts.sum(), s=28, color=c, alpha=0.85, label=lab, edgecolors="white")
        ccdf = [(vals >= k).sum() / (ks >= 1).sum() for k in vals]
        ax2.scatter(vals, ccdf, s=24, color=c, alpha=0.75, label=lab, edgecolors="white")
        if lab == "关系网络":
            m = vals >= 3
            if m.sum() > 2:
                k, b = np.polyfit(np.log(vals[m]), np.log(cnts[m] / cnts.sum()), 1)
                ax1.plot(vals[m], np.exp(b) * vals[m] ** k, "--", color=c, lw=1, alpha=0.8)
    ax1.set_xscale("log"); ax1.set_yscale("log")
    ax1.set_xlabel("度 k"); ax1.set_ylabel("P(k)")
    ax1.set_title("度分布（双对数）", fontsize=12)
    ax2.set_xscale("log"); ax2.set_yscale("log")
    ax2.set_xlabel("度 k"); ax2.set_ylabel("P(K ≥ k)")
    ax2.set_title("累计度分布：关系层是重尾，文本层接近均匀", fontsize=12)
    for ax in (ax1, ax2):
        ax.grid(linestyle=":", alpha=0.5)
        ax.legend(fontsize=9, frameon=False)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.suptitle("两种网络的不同“形状”", fontsize=15, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "fig13_degree_dist.png")

# ---------------------------------------------------------------- 割点：拿掉宝玉之后
def cutpoints():
    rem = "HLM-P001"
    HH = H.copy(); HH.remove_node(rem)
    comps = sorted(nx.connected_components(HH), key=len, reverse=True)
    cmap = ["#a4342a", "#3d6a8f", "#6f8f52", "#9a6a32", "#7a5a95", "#4f8f8b"]
    color = {}
    for i, c in enumerate(comps):
        for n in c:
            color[n] = cmap[i % len(cmap)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5, 7.2))
    nx.draw_networkx_edges(H, POS, edge_color="#d3c7b1", width=0.9, alpha=0.7, ax=ax1)
    nx.draw_networkx_nodes(H, POS, nodelist=[n for n in H if n != rem],
                           node_color=[color.get(n, "#cccccc") for n in H if n != rem],
                           node_size=[40 + 22 * H.degree(n) for n in H if n != rem],
                           edgecolors="white", linewidths=0.6, ax=ax1)
    nx.draw_networkx_nodes(H, POS, nodelist=[rem], node_color=PAPER, edgecolors="#a4342a",
                           linewidths=2.2, node_size=520, ax=ax1)
    ax1.text(POS[rem][0], POS[rem][1], "宝玉\n(已移除)", ha="center", va="center", fontsize=9,
             color="#a4342a")
    ax1.set_axis_off()
    ax1.set_title("原网络：去掉贾宝玉", fontsize=13)

    sizes = [len(c) for c in comps]
    ax2.barh(range(len(sizes)), sizes, color=[cmap[i % len(cmap)] for i in range(len(sizes))],
             height=0.65)
    ax2.set_yticks(range(len(sizes)))
    ax2.set_yticklabels(["第 %d 块" % (i + 1) for i in range(len(sizes))], fontsize=9)
    ax2.invert_yaxis()
    for i, v in enumerate(sizes):
        ax2.text(v + 0.6, i, str(v), va="center", fontsize=9)
    ax2.set_xlabel("人数")
    ax2.set_title("移除后裂成 %d 块：最大块 %d 人（原 109 人）" % (len(sizes), sizes[0]), fontsize=13)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    fig.suptitle("谁是真正的“关节”：贾宝玉是唯一横跨三层的人，拿掉他网络即断成数块",
                 fontsize=14.5, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "fig14_cutpoints.png")

# ---------------------------------------------------------------- 中心性热图
def heatmap():
    cols = ["度", "介数", "接近度", "PageRank", "kcore", "文本度"]
    lab = ["度", "介数", "接近度", "PageRank", "k-core", "文本度"]
    t = nm.copy()
    t["综合"] = sum((t[c] - t[c].min()) / (t[c].max() - t[c].min() + 1e-9) for c in cols)
    t = t.nlargest(24, "综合")
    M = np.array([[(r[c] - nm[c].min()) / (nm[c].max() - nm[c].min() + 1e-9) for c in cols]
                  for _, r in t.iterrows()], dtype=float)
    cmap = LinearSegmentedColormap.from_list("paper", ["#fffdf8", "#e8cfae", "#c98d4e", "#8f3b2a"])
    fig, ax = plt.subplots(figsize=(9.5, 9))
    im = ax.imshow(M, cmap=cmap, aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(lab, fontsize=11)
    ax.set_yticks(range(len(t)))
    ax.set_yticklabels(t["标准名"], fontsize=10)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            if v > 0.55:
                ax.text(j, i, "%.2f" % v, ha="center", va="center", fontsize=7.2, color="white")
    ax.set_title("主要人物的六种中心性（列内归一化）", fontsize=14, pad=12)
    fig.colorbar(im, ax=ax, shrink=0.7, label="相对强度")
    fig.tight_layout()
    save(fig, "fig15_centrality_heatmap.png")

for f in (layers, degree_dist, cutpoints, heatmap):
    try:
        f()
    except Exception as e:
        import traceback; traceback.print_exc()


