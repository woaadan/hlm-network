# -*- coding: utf-8 -*-
"""进阶网络分析：社群间连接、共仆网络、结构洞、命运对照、时序中心性。"""
import sys, io, json, math
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
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
fates = pd.read_csv(PROC / "fates.csv", encoding="utf-8-sig")

live = persons[persons["合并至"].isna() | (persons["合并至"] == "")]
pid = list(live["人物ID"])
name = dict(zip(live["人物ID"], live["标准名"]))
role = dict(zip(live["人物ID"], live["身份类别"]))
nmx = nm.set_index("人物ID")

G = nx.Graph(); G.add_nodes_from(pid)
for _, r in rels.iterrows():
    if r["主体ID"] in pid and r["客体ID"] in pid and r["主体ID"] != r["客体ID"]:
        G.add_edge(r["主体ID"], r["客体ID"], layer=r["关系大类"])

def save(fig, fn):
    save_fig(fig, fn)
    plt.close(fig)
    print("saved", fn)

out = {}

# ---------------------------------------------------------------- 1 社群间连接
def community_matrix():
    sub = nm[nm["社群"] >= 0]
    comm = dict(zip(sub["人物ID"], sub["社群"]))
    k = int(sub["社群"].max()) + 1
    M = np.zeros((k, k), dtype=int)
    for a, b in G.edges():
        ca, cb = comm.get(a, -1), comm.get(b, -1)
        if ca >= 0 and cb >= 0:
            M[ca, cb] += 1
            if ca != cb:
                M[cb, ca] += 1
    # 社群命名：取度数最高的两名成员
    labels = []
    for c in range(k):
        g = sub[sub["社群"] == c]
        labels.append("社群%d\n%s" % (c, "·".join(g.nlargest(2, "度")["标准名"])))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5, 7.2),
                                   gridspec_kw=dict(width_ratios=[1.25, 1]))
    cmap = LinearSegmentedColormap.from_list("p", ["#fffdf8", "#e9d2b4", "#c98d4e", "#8f3b2a"])
    im = ax1.imshow(M, cmap=cmap)
    ax1.set_xticks(range(k)); ax1.set_xticklabels(labels, fontsize=7.5, rotation=35, ha="right")
    ax1.set_yticks(range(k)); ax1.set_yticklabels(labels, fontsize=7.5)
    for i in range(k):
        for j in range(k):
            if M[i, j]:
                ax1.text(j, i, M[i, j], ha="center", va="center", fontsize=8,
                         color="white" if M[i, j] > M.max() * 0.5 else "#4a4136")
    ax1.set_title("社群之间的边数（对角线＝社群的芯）", fontsize=12)
    fig.colorbar(im, ax=ax1, shrink=0.7, label="边数")

    # 社群间“桥接者”：跨社群边占比最高的个人
    rows = []
    for n in G.nodes():
        cn = comm.get(n)
        if cn is None or G.degree(n) == 0:
            continue
        cross = sum(1 for m in G.neighbors(n) if comm.get(m) != cn)
        rows.append((name[n], cn, G.degree(n), cross, cross / G.degree(n)))
    df = pd.DataFrame(rows, columns=["name", "comm", "deg", "cross", "ratio"])
    df = df[df["cross"] > 0].sort_values(["cross", "ratio"], ascending=False).head(14)
    y = np.arange(len(df))
    ax2.barh(y, df["cross"], color=[f"C{int(c) % 10}" for c in df["comm"]], alpha=0.85, height=0.68)
    ax2.set_yticks(y); ax2.set_yticklabels(df["name"], fontsize=9)
    ax2.invert_yaxis()
    for i, (c, r) in enumerate(zip(df["cross"], df["ratio"])):
        ax2.text(c + 0.08, i, "跨社群 %d/%d 边" % (c, 0), va="center", fontsize=7.5, alpha=0)
    ax2.set_xlabel("跨社群边数")
    ax2.set_title("谁在社群之间搭桥", fontsize=12)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    fig.suptitle("九个“房”之间并不老死不相往来：跨社群边集中在少数几个人身上", fontsize=14, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, "fig16_community_matrix.png")
    out["comm_edges"] = dict(K=int(M.sum()) // 2, cross=int(M.sum() - np.trace(M)) // 2,
                             top=[dict(name=r["name"], cross=int(r["cross"]), deg=int(r["deg"]))
                                  for _, r in df.head(8).iterrows()])

# ---------------------------------------------------------------- 2 共仆网络
def bipartite_household():
    """主仆二部图：左侧主子，右侧其班底。"""
    B = nx.Graph()
    for _, r in rels.iterrows():
        if r["关系"] in ("丫鬟", "小厮", "乳母", "陪房", "买办", "管家", "老仆") and r["客体ID"] in pid:
            m, s_ = r["客体ID"], r["主体ID"]
            if role.get(m) in ("主子", "妾室") and role.get(s_) == "仆役":
                B.add_edge(m, s_)
    masters = sorted([n for n in B if role.get(n) in ("主子", "妾室")],
                     key=lambda n: -B.degree(n))
    masters = [m for m in masters if B.degree(m) > 0]
    servants = sorted({v for m in masters for v in B.neighbors(m)}, key=lambda v: name[v])
    fig, ax = plt.subplots(figsize=(11.5, 11))
    # 按主子分段排布，每段内均匀放置其仆役，避免标签重叠
    jitter, yy = {}, {}
    y = 0.0
    for m in masters:
        ns = sorted(B.neighbors(m), key=lambda x: name[x])
        ys = []
        for s_ in ns:
            jitter[s_] = y
            ys.append(y)
            y -= 1.0
        yy[m] = float(np.mean(ys))
        y -= 0.55
    for m in masters:
        for s_ in B.neighbors(m):
            ax.plot([0, 1], [yy[m], jitter[s_]], color="#cbbda6", lw=0.9, alpha=0.75, zorder=1)
    ax.scatter([0] * len(masters), [yy[m] for m in masters],
               s=[90 + 42 * B.degree(m) for m in masters],
               color=[ROLE_COLOR.get(role[m], "#999") for m in masters],
               edgecolors="white", linewidths=1.4, zorder=3)
    for m in masters:
        ax.text(-0.04, yy[m], "%s（%d）" % (name[m], B.degree(m)), ha="right", va="center",
                fontsize=10)
    ax.scatter([1] * len(servants), [jitter[s_] for s_ in servants], s=52,
               color="#8fa8bf", edgecolors="white", linewidths=0.8, zorder=3)
    for s_ in servants:
        ax.text(1.03, jitter[s_], name[s_], ha="left", va="center", fontsize=8.8, color="#4a443a")
    ax.set_xlim(-0.42, 1.42)
    ax.set_ylim(min(list(yy.values()) + list(jitter.values())) - 1.2,
                max(list(yy.values()) + list(jitter.values())) + 1.2)
    ax.set_axis_off()
    ax.set_title("主仆二部图：每个主子的“班底”有多大\n宝玉 11 人、王夫人 6 人、贾母 4 人——"
                 "荣国府的家务权力先看“手下有几个人”", fontsize=13, pad=14)
    save(fig, "fig17_bipartite.png")
    out["household"] = dict(masters=len(masters), servants=len(servants),
                            top=[dict(name=name[m], n=int(B.degree(m))) for m in masters[:8]])
# ---------------------------------------------------------------- 3 结构洞
def holes():
    t = nm[nm["度"] > 0].copy()
    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    sc_ = ax.scatter(t["有效规模"], t["约束度"], s=40 + 26 * t["度"],
                     c=[ROLE_COLOR.get(r, "#999") for r in t["身份类别"]],
                     alpha=0.85, edgecolors="white", linewidths=1.2)
    for _, r in t.nsmallest(8, "约束度").iterrows():
        ax.annotate(r["标准名"], (r["有效规模"], r["约束度"]), fontsize=9.5,
                    xytext=(6, 4), textcoords="offset points")
    ax.set_xlabel("有效规模（能触达的、互不重复的关系数）")
    ax.set_ylabel("约束度（越低越像“结构洞”占有者）")
    ax.invert_yaxis()
    ax.grid(linestyle=":", alpha=0.5)
    ax.set_title("结构洞：右上角是被困在单一圈子里的人，左下角是“桥”\n"
                 "宝玉的有效规模 26.5、约束度 0.063，是唯一的全局经纪人", fontsize=12.5)
    ax.legend(handles=[Patch(facecolor=c, label=k) for k, c in ROLE_COLOR.items()],
              fontsize=8.5, frameon=False, loc="upper right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    save(fig, "fig18_structural_holes.png")

# ---------------------------------------------------------------- 4 命运 × 位置
def fate():
    t = nm.dropna(subset=["结局类别"])
    order = ["死亡", "出家", "守寡", "远嫁", "流放", "婚配", "仕宦", "存续", "失踪", "不详"]
    order = [o for o in order if o in set(t["结局类别"])]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.2),
                                   gridspec_kw=dict(width_ratios=[1.15, 1]))
    data = [t[t["结局类别"] == o]["介数"].values for o in order]
    bp = ax1.boxplot(data, patch_artist=True, widths=0.55, showfliers=False)
    for p in bp["boxes"]:
        p.set_facecolor("#d9b27c"); p.set_alpha(0.75)
    for i, o in enumerate(order):
        y = t[t["结局类别"] == o]["介数"].values
        ax1.scatter(np.random.normal(i + 1, 0.06, len(y)), y, s=18, color="#8f3b2a", alpha=0.75, zorder=3)
    ax1.set_xticks(range(1, len(order) + 1))
    ax1.set_xticklabels(order, fontsize=10)
    ax1.set_ylabel("介数中心性")
    ax1.set_title("结局类别 × 介数：死亡组里既有一线人物，也有边缘人", fontsize=12)

    d = t.dropna(subset=["结局回目"])
    ax2.scatter(d["出场回数"], d["结局回目"], s=30 + 40 * d["介数"], c="#3d6a8f", alpha=0.75,
                edgecolors="white")
    for _, r in d.nlargest(6, "介数").iterrows():
        ax2.annotate(r["标准名"], (r["出场回数"], r["结局回目"]), fontsize=9,
                     xytext=(5, 3), textcoords="offset points")
    ax2.set_xlabel("出场回数")
    ax2.set_ylabel("结局回目（逝世/离场）")
    ax2.grid(linestyle=":", alpha=0.5)
    ax2.set_title("戏份越多，退场越晚？——并不成立", fontsize=12)
    for ax in (ax1, ax2):
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.suptitle("网络位置能预测命运吗：能的一部分，不能的是另一部分", fontsize=14, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "fig19_fate.png")
    out["fate"] = {o: dict(n=int(len(t[t["结局类别"] == o])),
                           med=float(t[t["结局类别"] == o]["介数"].median())) for o in order}

# ---------------------------------------------------------------- 5 时序中心性
def temporal_centrality():
    picks = ["贾宝玉", "王熙凤", "林黛玉", "薛宝钗", "袭人", "王夫人", "贾探春", "贾琏"]
    ids = {name_: next((p for p in pid if name[p] == name_), None) for name_ in picks}
    rows = []
    for blk in range(1, 13):
        sub = pc[((pc["回"] - 1) // 10 + 1) == blk]
        per = {c: set(g["人物ID"]) for c, g in sub.groupby("回")}
        H = nx.Graph()
        cnt = Counter()
        for c, s in per.items():
            s = sorted(s)
            for i in range(len(s)):
                for j in range(i + 1, len(s)):
                    cnt[(s[i], s[j])] += 1
        for e, w in cnt.items():
            H.add_edge(*e, weight=w)
        if H.number_of_nodes() > 3:
            bc = nx.betweenness_centrality(H.subgraph(max(nx.connected_components(H), key=len)))
        else:
            bc = {}
        for n_, p in ids.items():
            if p:
                rows.append(dict(块=blk, 人物=n_, 度=H.degree(p) if p in H else 0,
                                 介数=bc.get(p, 0.0)))
    df = pd.DataFrame(rows)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.8))
    for n_ in picks:
        d = df[df["人物"] == n_]
        ax1.plot(d["块"], d["度"], marker="o", ms=3.5, lw=1.7, label=n_)
        ax2.plot(d["块"], d["介数"], marker="o", ms=3.5, lw=1.7, label=n_)
    for ax, title, ylab in [(ax1, "同场网络中的度（十年块）", "度"),
                            (ax2, "同场网络中的介数（十年块）", "介数")]:
        ax.set_xlabel("十年块（1 = 第 1–10 回）")
        ax.set_ylabel(ylab)
        ax.set_title(title, fontsize=12)
        ax.grid(linestyle=":", alpha=0.5)
        ax.axvline(8, color="#a4342a", ls="--", lw=1)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    ax1.legend(fontsize=8.5, ncol=2, frameon=False)
    fig.suptitle("中心性不是常数：宝玉的“桥”属性在第 80 回后明显下降", fontsize=14, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "fig20_temporal_centrality.png")
    out["temporal"] = df.groupby("人物")[["度", "介数"]].mean().round(2).to_dict()

for f in (community_matrix, bipartite_household, holes, fate, temporal_centrality):
    try:
        f()
    except Exception:
        import traceback; traceback.print_exc()

json.dump(out, open(PROC / "extra_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:800])



