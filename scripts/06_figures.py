# -*- coding: utf-8 -*-
"""静态图：网络总览、中心性、社群、时序、跨模态、人物卡。"""
import sys, io, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_common import PROC, FIG, DOCS, RAW, setup_font, LAYER_COLOR, ROLE_COLOR, PAPER
from lib_layout import forceatlas2

setup_font()
persons = pd.read_csv(PROC / "persons.csv", encoding="utf-8-sig")
rels = pd.read_csv(PROC / "relations.csv", encoding="utf-8-sig")
nm = pd.read_csv(PROC / "node_metrics.csv", encoding="utf-8-sig")
cm = pd.read_csv(PROC / "chapter_metrics.csv", encoding="utf-8-sig")
bm = pd.read_csv(PROC / "block_metrics.csv", encoding="utf-8-sig")
sc = pd.read_csv(PROC / "cooccurrence_scene.csv", encoding="utf-8-sig")
fates = pd.read_csv(PROC / "fates.csv", encoding="utf-8-sig")
S = json.load(open(PROC / "network_summary.json", encoding="utf-8"))

live = persons[persons["合并至"].isna() | (persons["合并至"] == "")]
pid = list(live["人物ID"])
name = dict(zip(live["人物ID"], live["标准名"]))
role = dict(zip(live["人物ID"], live["身份类别"]))

G = nx.Graph(); G.add_nodes_from(pid)
for _, r in rels.iterrows():
    if r["主体ID"] in pid and r["客体ID"] in pid and r["主体ID"] != r["客体ID"]:
        G.add_edge(r["主体ID"], r["客体ID"], layer=r["关系大类"])

GT = nx.Graph(); GT.add_nodes_from(pid)
for _, r in sc[sc["同场次数"] >= 3].iterrows():
    GT.add_edge(r["a"], r["b"], weight=int(r["同场次数"]))

COMM = dict(zip(nm["人物ID"], nm["社群"]))
CMAP = ["#B03A2E", "#2E86C1", "#229954", "#D68910", "#7D3C98",
        "#17A589", "#CA6F1E", "#5D6D7E", "#C2185B"]

def save(fig, fn):
    for d in (FIG, DOCS / "figures"):
        fig.patch.set_facecolor(PAPER)
        fig.savefig(d / fn, facecolor=PAPER)
    plt.close(fig)
    print("saved", fn)

# ---------------------------------------------------------------- F1 关系网络
def f1():
    giant = max(nx.connected_components(G), key=len)
    H = G.subgraph(giant)
    pos = forceatlas2(H, weight=None, iterations=700, seed=7)
    fig, ax = plt.subplots(figsize=(13, 10))
    for L, c in LAYER_COLOR.items():
        es = [(a, b) for a, b, d in H.edges(data=True) if d["layer"] == L]
        nx.draw_networkx_edges(H, pos, edgelist=es, edge_color=c, width=1.3, alpha=0.6, ax=ax)
    sizes = [90 + 95 * G.degree(n) for n in H]
    colors = [CMAP[COMM.get(n, 0) % len(CMAP)] for n in H]
    nx.draw_networkx_nodes(H, pos, node_size=sizes, node_color=colors,
                           edgecolors=PAPER, linewidths=1.2, alpha=0.95, ax=ax)
    top = set(nm.nlargest(26, "度")["人物ID"])
    for n, (x, y) in pos.items():
        if n in top:
            ax.text(x, y, name[n], fontsize=8.4, ha="center", va="center",
                    color="#111111", zorder=10,
                    path_effects=[pe.withStroke(linewidth=2.6, foreground=PAPER)])
    ax.set_axis_off()
    ax.set_title("《红楼梦》人物关系网络（亲属 / 主仆 / 社会 三层）\n"
                 "巨连通块 %d 人 · %d 条关系 · 9 个社群（模块度 %.2f）；另 %d 人散在小圈子"
                 % (H.number_of_nodes(), H.number_of_edges(), S["community"]["modularity"],
                    len(pid) - H.number_of_nodes()),
                 fontsize=15, pad=16)
    handles = [Line2D([], [], color=c, lw=2, label=L) for L, c in LAYER_COLOR.items()]
    handles += [Patch(facecolor=CMAP[i], label="社群 %d（%d 人）" % (i, s))
                for i, s in enumerate(S["community"]["sizes"])]
    ax.legend(handles=handles, loc="lower left", fontsize=8.5, frameon=False, ncol=2)
    save(fig, "fig1_relation_network.png")

# ---------------------------------------------------------------- F2 融合网络
def f2():
    # 制度关系为骨架；原表中“无关系”的人，用其最强的一次同场共现接回伙伴
    H = G.subgraph([n for n in G if G.degree(n) > 0]).copy()
    pos = forceatlas2(H, weight=None, iterations=700, seed=11)
    iso = [n for n in pid if G.degree(n) == 0]
    best, placed = {}, []
    for n in iso:
        cand = sc[(sc["a"] == n) | (sc["b"] == n)]
        cand = cand[cand["a"].isin(pos) | cand["b"].isin(pos)]
        if not len(cand):
            continue
        r = cand.iloc[0]
        partner = r["b"] if r["a"] == n else r["a"]
        if partner not in pos:
            continue
        best[n] = (partner, int(r["同场次数"]))
        placed.append(n)
    fig, ax = plt.subplots(figsize=(13.5, 10.5))
    # 把“文本接回”的人排到外环，按伙伴方位排序，减少连线交叉
    placed.sort(key=lambda n: math.atan2(pos[best[n][0]][1], pos[best[n][0]][0]))
    R = 1.22
    for i, n in enumerate(placed):
        ang = 2 * np.pi * i / max(len(placed), 1)
        pos[n] = R * np.array([np.cos(ang), np.sin(ang)])
    for n in iso:
        if n not in placed:
            pos[n] = np.array([0, 0])
    # 文本补接边
    for n in placed:
        p, w = best[n]
        ax.plot([pos[n][0], pos[p][0]], [pos[n][1], pos[p][1]],
                color="#7F8C8D", lw=0.6 + 0.1 * min(w, 10), ls=(0, (2, 2)), alpha=0.55, zorder=1)
    for L, c in LAYER_COLOR.items():
        es = [(a, b) for a, b, d in G.edges(data=True) if d["layer"] == L]
        nx.draw_networkx_edges(G, pos, edgelist=es, edge_color=c, width=1.8, alpha=0.9, ax=ax)
    sizes = [70 + 26 * G.degree(n) for n in H] + [40] * len(placed)
    colors = [ROLE_COLOR.get(role[n], "#999999") for n in H] + ["#FFFFFF"] * len(placed)
    nodes = list(H) + placed
    nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_size=sizes, node_color=colors,
                           edgecolors=[ROLE_COLOR.get(role[n], "#999") for n in H]
                           + ["#7F8C8D"] * len(placed),
                           linewidths=1.0, alpha=0.96, ax=ax)
    for n in H:
        if G.degree(n) >= 6:
            ax.text(pos[n][0], pos[n][1], name[n], fontsize=8.2, ha="center", va="center",
                    zorder=12, path_effects=[pe.withStroke(linewidth=2.6, foreground=PAPER)])
    for n in placed:
        r = pos[n] * 1.055
        ax.text(r[0], r[1], name[n], fontsize=6.8, ha="center", va="center", color="#4D5656",
                zorder=12, path_effects=[pe.withStroke(linewidth=2.2, foreground=PAPER)])
    ax.set_xlim(-1.42, 1.42)
    ax.set_ylim(-1.36, 1.36)
    ax.set_axis_off()
    ax.set_title("制度关系（彩）＋ 文本同场补接（灰虚线）\n"
                 "内圈＝原表已录入的 %d 人；外环＝原表“关系网外”但文本仍在场、可被接回的 %d 人"
                 % (len(H), len(placed)), fontsize=14.5, pad=14)
    handles = [Line2D([], [], color=c, lw=2.4, label=L) for L, c in LAYER_COLOR.items()]
    handles += [Line2D([], [], color="#7F8C8D", lw=1.2, ls=(0, (2, 2)), label="文本同场补接")]
    handles += [Patch(facecolor=c, label=k) for k, c in ROLE_COLOR.items()]
    ax.legend(handles=handles, loc="lower left", fontsize=8.2, frameon=False, ncol=3)
    save(fig, "fig2_fused_network.png")

# ---------------------------------------------------------------- F3 中心性
def f3():
    top = nm.nlargest(15, "介数")
    fig, axes = plt.subplots(1, 3, figsize=(15, 6.4))
    specs = [("度", "度中心性（关系邻居数）", "#B03A2E"),
             ("介数", "介数中心性（最短路经过率）", "#2E86C1"),
             ("PageRank", "PageRank（加权影响力）", "#229954")]
    for ax, (col, title, c) in zip(axes, specs):
        t = nm.nlargest(15, col).iloc[::-1]
        ax.barh(t["标准名"], t[col], color=c, alpha=0.85, height=0.72)
        for y, v in enumerate(t[col]):
            ax.text(v, y, " %.3f" % v if v < 1 else " %d" % v, va="center", fontsize=8)
        ax.set_title(title, fontsize=12)
        ax.tick_params(labelsize=9)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.suptitle("谁在结构上不可替代：三种中心性口径下的前 15 人", fontsize=15, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, "fig3_centrality.png")

# ---------------------------------------------------------------- F4 社群 vs 府邸
def f4():
    sub = nm[nm["社群"] >= 0]
    ct = pd.crosstab(sub["社群"], sub["居所"])
    ct = ct[ct.sum().sort_values(ascending=False).index]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.2),
                                   gridspec_kw=dict(width_ratios=[1.35, 1]))
    im = ax1.imshow(ct.values, cmap="YlOrRd", aspect="auto")
    ax1.set_xticks(range(len(ct.columns)))
    ax1.set_xticklabels(ct.columns, rotation=32, ha="right", fontsize=9)
    ax1.set_yticks(range(len(ct.index)))
    short = {i: "·".join(nm[nm["社群"] == i].nlargest(2, "度")["标准名"])
             for i in ct.index}
    ax1.set_yticklabels(["社群%d｜%s" % (i, short[i]) for i in ct.index], fontsize=8.5)
    for i in range(ct.shape[0]):
        for j in range(ct.shape[1]):
            v = ct.values[i, j]
            if v:
                ax1.text(j, i, v, ha="center", va="center", fontsize=9,
                         color="white" if v > ct.values.max() * 0.55 else "#333333")
    ax1.set_title("社群 × 居所：Louvain 社群与府邸的对应", fontsize=12)
    fig.colorbar(im, ax=ax1, shrink=0.72, label="人数")

    # 社群画像：主子/仆役/客卿占比
    prof = sub.groupby("社群")["身份类别"].value_counts(normalize=True).unstack().fillna(0)
    prof = prof[[c for c in ["主子", "妾室", "仆役", "宗族", "客卿", "外人"] if c in prof]]
    bottom = np.zeros(len(prof))
    for c in prof.columns:
        ax2.bar([str(i) for i in prof.index], prof[c], bottom=bottom,
                color=ROLE_COLOR[c], label=c, width=0.7)
        bottom += prof[c].values
    ax2.set_title("各社群的等级构成", fontsize=12)
    ax2.set_xlabel("社群")
    ax2.set_ylabel("占比")
    ax2.legend(fontsize=8, ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    fig.suptitle("宗法结构的分形：社群≈房头（NMI=%.2f，模块度=%.2f；关系层）"
                 % (S["community"]["nmi居所"], S["community"]["modularity"]),
                 fontsize=14, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, "fig4_community_mansion.png")

# ---------------------------------------------------------------- F5 核心-边缘
def f5():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 6.2),
                                   gridspec_kw=dict(width_ratios=[1, 1.3]))
    kc = nm["kcore"].value_counts().sort_index()
    ax1.bar(kc.index.astype(str), kc.values, color="#5D6D7E", width=0.62)
    for x, v in zip(kc.index.astype(str), kc.values):
        ax1.text(x, v, str(v), ha="center", va="bottom", fontsize=10)
    ax1.set_xlabel("k-core 层（k 值）")
    ax1.set_ylabel("人数")
    ax1.set_title("k-core 分解：网络只有 3 层核", fontsize=12)
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)

    ax2.scatter(nm["度"], nm["介数"] + 1e-4, s=28,
                c=[ROLE_COLOR.get(r, "#999") for r in nm["身份类别"]], alpha=0.85,
                edgecolors=PAPER, linewidths=0.6)
    for _, r in nm.nlargest(8, "介数").iterrows():
        ax2.annotate(r["标准名"], (r["度"], r["介数"]), fontsize=9,
                     xytext=(4, 3), textcoords="offset points")
    ax2.set_xscale("symlog", linthresh=1)
    ax2.set_yscale("log")
    ax2.set_xlabel("度（关系邻居数）")
    ax2.set_ylabel("介数中心性")
    ax2.set_title("度—介数关系：高介数者未必高 degree", fontsize=12)
    ax2.grid(linestyle=":", alpha=0.4)
    ax2.legend(handles=[Patch(facecolor=c, label=k) for k, c in ROLE_COLOR.items()],
               fontsize=8, frameon=False)
    fig.suptitle("核心—边缘：谁处在“桥”上", fontsize=14, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, "fig5_core_periphery.png")

# ---------------------------------------------------------------- F6 时序
def f6():
    fig = plt.figure(figsize=(15, 9))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.25], hspace=0.35, wspace=0.22)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(cm["回"], cm["人数"], color="#2E86C1", lw=1.4)
    ax1.axvline(80.5, color="#B03A2E", ls="--", lw=1)
    ax1.set_xlabel("回")
    ax1.set_ylabel("出场人数")
    ax1.set_title("每回出场人数", fontsize=12)
    ax1.grid(linestyle=":", alpha=0.4)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(cm["回"], cm["内部共现边"], color="#229954", lw=1.4)
    ax2.axvline(80.5, color="#B03A2E", ls="--", lw=1)
    ax2.set_xlabel("回")
    ax2.set_ylabel("同场共现边数")
    ax2.set_title("每回内部共现密度", fontsize=12)
    ax2.grid(linestyle=":", alpha=0.4)

    ax3 = fig.add_subplot(gs[1, :])
    top = nm.nlargest(26, "文本度")["人物ID"].tolist()
    pc = pd.read_csv(PROC / "person_chapter.csv", encoding="utf-8-sig")
    mat = np.zeros((len(top), 12))
    for i, p in enumerate(top):
        for b in range(1, 13):
            mat[i, b - 1] = pc[(pc["人物ID"] == p) & (((pc["回"] - 1) // 10 + 1) == b)]["次数"].sum()
    mat = mat / np.maximum(mat.max(axis=1, keepdims=True), 1)
    im = ax3.imshow(mat, aspect="auto", cmap="YlGnBu")
    ax3.set_yticks(range(len(top)))
    ax3.set_yticklabels([name[p] for p in top], fontsize=8.5)
    ax3.set_xticks(range(12))
    ax3.set_xticklabels(bm["回段"], rotation=30, ha="right", fontsize=8)
    ax3.axvline(7.5, color="#B03A2E", ls="--", lw=1.2)
    ax3.set_title("主要人物出场强度（按十年块归一化）——虚线为第 80 回", fontsize=12)
    fig.colorbar(im, ax=ax3, shrink=0.6, label="相对强度")
    fig.suptitle("时序：大观园的“舞台”从谁身上移开", fontsize=15, y=0.98)
    save(fig, "fig6_temporal.png")

# ---------------------------------------------------------------- F7 前后 80 回
def f7():
    pc = pd.read_csv(PROC / "person_chapter.csv", encoding="utf-8-sig")
    first = pc[pc["回"] <= 80].groupby("人物ID")["次数"].sum()
    last = pc[pc["回"] > 80].groupby("人物ID")["次数"].sum()
    both = pd.DataFrame({"前80": first, "后40": last}).fillna(0)
    both["name"] = [name.get(i, i) for i in both.index]
    fig, ax = plt.subplots(figsize=(9.5, 8))
    ax.scatter(both["前80"] + 1, both["后40"] + 1, s=26, color="#2E86C1", alpha=0.7,
               edgecolors=PAPER, linewidths=0.5)
    lim = max(both["前80"].max(), both["后40"].max()) * 1.3 + 2
    ax.plot([1, lim], [1, lim], ls="--", color="#999999", lw=1)
    for _, r in both.nlargest(12, "前80").iterrows():
        ax.annotate(r["name"], (r["前80"] + 1, r["后40"] + 1), fontsize=9,
                    xytext=(4, -8), textcoords="offset points")
    for _, r in both.nlargest(4, "后40").iterrows():
        if r["后40"] > r["前80"] * 1.2:
            ax.annotate(r["name"], (r["前80"] + 1, r["后40"] + 1), fontsize=9, color="#B03A2E",
                        xytext=(4, 4), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("前 80 回提及次数（对数）")
    ax.set_ylabel("后 40 回提及次数（对数）")
    ax.grid(linestyle=":", alpha=0.4)
    a = S["authorship"]
    ax.set_title("前 80 回 vs 后 40 回：人物戏份的连续性\n"
                 "Spearman ρ=%.3f（p=%.1g），前 20 名重合 %d 人，仅前 80 回出现 %d 人"
                 % (a["spearman"], a["p"], a["top20_overlap"], a["only_first80_n"]), fontsize=12)
    save(fig, "fig7_authorship.png")

# ---------------------------------------------------------------- F8 视觉模态
def f8():
    fz = nm.dropna(subset=["brightness"])
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.6),
                             gridspec_kw=dict(width_ratios=[1, 1, 1.15]))
    order = ["主子", "妾室", "宗族", "客卿", "外人", "仆役"]
    for ax, col, title in [(axes[0], "brightness", "画面亮度"),
                           (axes[1], "saturation", "色彩饱和度")]:
        data = [fz[fz["身份类别"] == k][col].dropna().values for k in order]
        bp = ax.boxplot(data, patch_artist=True, widths=0.55, showfliers=True)
        for patch, k in zip(bp["boxes"], order):
            patch.set_facecolor(ROLE_COLOR[k])
            patch.set_alpha(0.75)
        ax.set_xticklabels(order, fontsize=8.5, rotation=20)
        ax.set_title(title + " × 身份", fontsize=12)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    p = S["visual"]["mw_p"]
    axes[1].text(0.02, 0.97, "主子 vs 仆役 Mann-Whitney\n亮度 p=%.2f，饱和度 p=%.2f"
                 % (p.get("brightness", 1), p.get("saturation", 1)),
                 transform=axes[1].transAxes, fontsize=8.5, va="top")

    cov = pd.crosstab(nm.set_index("人物ID")["身份类别"],
                      live.set_index("人物ID")["图像状态_清洗"].reindex(nm["人物ID"]).values)
    cov = cov.reindex(order).fillna(0)
    cols = [c for c in ["正常", "别名同图", "占位（同图待核）", "图源冲突", "缺图"] if c in cov.columns]
    bottom = np.zeros(len(cov))
    colors = {"正常": "#229954", "别名同图": "#7DCEA0", "占位（同图待核）": "#F1C40F",
              "图源冲突": "#E67E22", "缺图": "#B03A2E"}
    for c in cols:
        axes[2].bar(cov.index, cov[c], bottom=bottom, color=colors[c], label=c, width=0.66)
        bottom += cov[c].values
    axes[2].set_title("图像可信度 × 身份", fontsize=12)
    axes[2].legend(fontsize=8, frameon=False)
    axes[2].tick_params(labelsize=8.5, axis="x", rotation=20)
    for s in ("top", "right"):
        axes[2].spines[s].set_visible(False)
    fig.suptitle("图像模态：剧照的低层视觉特征与网络位置几乎无关，但“谁有图”暴露了知识库偏差",
                 fontsize=13.5, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "fig8_visual_modality.png")

# ---------------------------------------------------------------- F9 文本证据
def f9():
    ev = rels[rels["同回共现"].notna()].copy()
    ev["同回共现"] = ev["同回共现"].astype(int)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8),
                                   gridspec_kw=dict(width_ratios=[1, 1.2]))
    bins = np.arange(0, ev["同回共现"].max() + 2) - 0.5
    for L, c in LAYER_COLOR.items():
        d = ev[ev["关系大类"] == L]["同回共现"]
        ax1.hist(d, bins=bins, color=c, alpha=0.6, label=L)
    ax1.axvline(ev["同回共现"].median(), color="#333", ls="--", lw=1)
    ax1.set_xlabel("同回共现次数")
    ax1.set_ylabel("关系边数")
    ax1.set_title("关系边的“文本曝光度”", fontsize=12)
    ax1.legend(fontsize=8.5, frameon=False)
    ax1.grid(axis="y", linestyle=":", alpha=0.4)

    w = ev.nsmallest(14, "同回共现")
    y = range(len(w))
    vals = w["同回共现"].values.astype(float)
    ax2.barh(list(y), np.maximum(vals, 0.02), color="#E67E22", alpha=0.85, height=0.62)
    ax2.set_xlim(0, max(3, float(vals.max()) * 1.15 + 1))
    for yy, v in zip(y, vals):
        ax2.text(max(v, 0.02) + 0.05, yy, "%d 次" % v, va="center", fontsize=8, color="#7F8C8D")
    ax2.set_yticks(list(y))
    ax2.set_yticklabels(["%s—%s（%s）" % (r["主体"], r["客体"], r["关系"]) for _, r in w.iterrows()],
                        fontsize=8.5)
    ax2.invert_yaxis()
    ax2.set_xlabel("同回共现次数")
    ax2.set_title("文本证据最弱的关系边（可能为误标或间接关系）", fontsize=12)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    fig.suptitle("关系网络能否被文本证实：%d 条边中 %d 条从未同回出现"
                 % (S["evidence"]["edges"], S["evidence"]["zero"]), fontsize=14, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "fig9_evidence.png")

# ---------------------------------------------------------------- F10 人物卡
def f10():
    picks = ["HLM-P001", "HLM-P006", "HLM-P017", "HLM-P010", "HLM-P004",
             "HLM-P029", "HLM-P016", "HLM-P053", "HLM-P133", "HLM-P062",
             "HLM-P044", "HLM-P050"]
    nmx = nm.set_index("人物ID")
    fig, axes = plt.subplots(3, 4, figsize=(13.5, 11))
    for ax, p in zip(axes.ravel(), picks):
        r = nmx.loc[p]
        img = DOCS / "img" / (p + ".jpg")
        if img.exists():
            ax.imshow(Image.open(img))
        else:
            ax.add_patch(plt.Rectangle((0, 0), 1, 1, color="#E5E8E8"))
            ax.text(0.5, 0.5, "无图", ha="center", va="center", fontsize=12, color="#777")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title("%s\n%s｜度 %d｜介数 %.3f" % (r["标准名"], r["身份类别"], r["度"], r["介数"]),
                     fontsize=10)
        for s in ax.spines.values():
            s.set_edgecolor(ROLE_COLOR.get(r["身份类别"], "#999"))
            s.set_linewidth(2.2)
    fig.suptitle("多模态人物卡：剧照（图像）＋ 关系指标（网络）＋ 出场回数（文本）", fontsize=14, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save(fig, "fig10_persona_cards.png")

# ---------------------------------------------------------------- F11 图像墙
def f11():
    imgs = [(p, DOCS / "img" / (p + ".jpg")) for p in pid if (DOCS / "img" / (p + ".jpg")).exists()]
    imgs.sort(key=lambda x: -nm.set_index("人物ID").loc[x[0], "度"])
    cols, rows = 16, math.ceil(len(imgs) / 16)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 1.05, rows * 1.35))
    for ax in axes.ravel():
        ax.axis("off")
    for ax, (p, f) in zip(axes.ravel(), imgs):
        ax.imshow(Image.open(f))
        ax.set_title(name[p], fontsize=6.2, pad=1.5)
    fig.suptitle("图像模态全集：%d 位人物的可确认剧照（按关系度数降序）" % len(imgs), fontsize=13, y=1.0)
    fig.tight_layout(pad=0.35)
    save(fig, "fig11_portrait_wall.png")

for fn in (f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11):
    try:
        fn()
    except Exception as e:
        import traceback
        print("!! %s 失败：" % fn.__name__, e)
        traceback.print_exc()


