# -*- coding: utf-8 -*-
"""网络分析：关系三层 + 文本共现层 → 融合网络；中心性、社群、桥接、时序、跨模态。

产出
----
data/processed/node_metrics.csv      节点级指标
data/processed/edges_combined.csv    融合网络边表（供网页与复现）
data/processed/chapter_metrics.csv   120 回 / 12 个十年的网络指标
data/processed/network_summary.json  全局指标
"""
import sys, io, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
from networkx.algorithms.structuralholes import constraint as sh_constraint, effective_size as sh_esize
from scipy.stats import spearmanr, mannwhitneyu

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_common import PROC

persons = pd.read_csv(PROC / "persons.csv", encoding="utf-8-sig")
rels = pd.read_csv(PROC / "relations.csv", encoding="utf-8-sig")
co = pd.read_csv(PROC / "cooccurrence.csv", encoding="utf-8-sig")
sc = pd.read_csv(PROC / "cooccurrence_scene.csv", encoding="utf-8-sig")
ts = pd.read_csv(PROC / "text_stats.csv", encoding="utf-8-sig")
pc = pd.read_csv(PROC / "person_chapter.csv", encoding="utf-8-sig")
feats = pd.read_csv(PROC / "image_features.csv", encoding="utf-8-sig")
fates = pd.read_csv(PROC / "fates.csv", encoding="utf-8-sig")

live = persons[persons["合并至"].isna() | (persons["合并至"] == "")].copy()
pid = list(live["人物ID"])
name = dict(zip(live["人物ID"], live["标准名"]))
role = dict(zip(live["人物ID"], live["身份类别"]))
house = dict(zip(live["人物ID"], live["血缘家族"]))
reside = dict(zip(live["人物ID"], live["居所"]))
gender = dict(zip(live["人物ID"], live["性别"]))
LAYERS = ["亲属关系", "主仆关系", "社会关系"]

# ---------------------------------------------------------------- 关系网络
G = nx.Graph(); G.add_nodes_from(pid)
D = nx.DiGraph(); D.add_nodes_from(pid)
for _, r in rels.iterrows():
    a, b = r["主体ID"], r["客体ID"]
    if a not in pid or b not in pid or a == b:
        continue
    D.add_edge(a, b, rel=r["关系"], layer=r["关系大类"])
    if G.has_edge(a, b):
        G[a][b]["layers"].add(r["关系大类"])
        G[a][b]["preds"].append(r["关系"])
    else:
        G.add_edge(a, b, weight=1.0, layers={r["关系大类"]}, preds=[r["关系"]])
for a, b, d in G.edges(data=True):
    d["weight"] = 1.0

GL = {}
for L in LAYERS:
    H = nx.Graph(); H.add_nodes_from(pid)
    for _, r in rels.iterrows():
        if r["关系大类"] == L and r["主体ID"] in pid and r["客体ID"] in pid:
            H.add_edge(r["主体ID"], r["客体ID"])
    H.remove_nodes_from(list(nx.isolates(H)))
    GL[L] = H

# ---------------------------------------------------------------- 文本网络（同场窗口）
T_MIN = 3
GT = nx.Graph(); GT.add_nodes_from(pid)
for _, r in sc[sc["同场次数"] >= T_MIN].iterrows():
    GT.add_edge(r["a"], r["b"], weight=int(r["同场次数"]))

# ---------------------------------------------------------------- 融合网络
GA = nx.Graph(); GA.add_nodes_from(pid)
for a, b, d in G.edges(data=True):
    GA.add_edge(a, b, rel=1, text=0, w=1.0 + math.log1p(0))
for a, b, d in GT.edges(data=True):
    if GA.has_edge(a, b):
        GA[a][b]["text"] = d["weight"]
        GA[a][b]["w"] = 1.0 + math.log1p(d["weight"])
    else:
        GA.add_edge(a, b, rel=0, text=d["weight"], w=math.log1p(d["weight"]))

# 文本证据回填（同回共现次数）
co_idx = {}
for _, r in co.iterrows():
    co_idx[(r["a"], r["b"])] = int(r["共现回数"])
    co_idx[(r["b"], r["a"])] = int(r["共现回数"])
rels["同回共现"] = [co_idx.get((r["主体ID"], r["客体ID"]), 0) for _, r in rels.iterrows()]
rels["jaccard"] = [round(co_idx.get((r["主体ID"], r["客体ID"]), 0) /
                         max(ts.set_index("人物ID").loc[r["主体ID"], "出场回数"] +
                             ts.set_index("人物ID").loc[r["客体ID"], "出场回数"] -
                             co_idx.get((r["主体ID"], r["客体ID"]), 0), 1), 4)
                     for _, r in rels.iterrows()]

# ---------------------------------------------------------------- 指标
def basic(Gx):
    comps = list(nx.connected_components(Gx))
    giant = max(comps, key=len) if comps else set()
    g = Gx.subgraph(giant)
    try:
        diam, asp = nx.diameter(g), nx.average_shortest_path_length(g)
    except Exception:
        diam, asp = None, None
    return dict(n=Gx.number_of_nodes(), m=Gx.number_of_edges(),
                density=round(nx.density(Gx), 4),
                avg_degree=round(2 * Gx.number_of_edges() / max(Gx.number_of_nodes(), 1), 2),
                components=len(comps), giant=len(giant), diameter=diam,
                avg_path=round(asp, 3) if asp else None,
                clustering=round(nx.average_clustering(Gx), 3),
                isolates=len(list(nx.isolates(Gx))),
                assortativity=round(nx.degree_assortativity_coefficient(Gx), 3))

summary = dict(relation=dict(**basic(G), name="关系网络"),
               combined=dict(**basic(GA), name="融合网络"),
               text=dict(**basic(GT), name="文本共现层", threshold=T_MIN),
               reciprocity=round(nx.overall_reciprocity(D), 3))
for L in LAYERS:
    summary[L] = dict(**basic(GL[L]), name=L)

# 社群：关系网络只在巨连通块内做（孤立点不参与，否则模块度虚高）
giant_rel = max(nx.connected_components(G), key=len)
subr = G.subgraph(giant_rel).copy()
commr = sorted(nx.community.louvain_communities(subr, seed=42), key=len, reverse=True)
comm_of = {n: i for i, c in enumerate(commr) for n in c}
mod = nx.community.modularity(subr, commr)
# 对照：文本同场网络上的社群
GT10 = GT.copy()
GT10.remove_nodes_from(list(nx.isolates(GT10)))
c10 = sorted(nx.community.louvain_communities(GT10, seed=42, weight="weight"), key=len, reverse=True)
mod10 = nx.community.modularity(GT10, c10, weight="weight")
comm10_of = {n: i for i, c in enumerate(c10) for n in c}
summary["community"] = dict(n=len(commr), modularity=round(mod, 3),
                            sizes=[len(c) for c in commr],
                            text_n=len(c10), text_modularity=round(mod10, 3),
                            text_sizes=[len(c) for c in c10])

# 中心性（关系网络）
btw = nx.betweenness_centrality(G, normalized=True)
clo = nx.closeness_centrality(G)
try:
    eig = nx.eigenvector_centrality_numpy(G)
except Exception:
    eig = nx.eigenvector_centrality(G, max_iter=2000)
pr = nx.pagerank(G, alpha=0.85)
cons, esize = sh_constraint(G), sh_esize(G)
core = nx.core_number(G)
core_a = nx.core_number(GA)
btw_a = nx.betweenness_centrality(GA, weight=None, normalized=True)

deg_layer = {L: dict(GL[L].degree()) for L in LAYERS}
rows = []
for p in pid:
    dl = [deg_layer[L].get(p, 0) for L in LAYERS]
    tot = sum(dl)
    part = (len(LAYERS) / (len(LAYERS) - 1)) * (1 - sum((k / tot) ** 2 for k in dl)) if tot else 0.0
    rows.append(dict(人物ID=p, 标准名=name[p], 身份类别=role[p], 血缘家族=house[p],
                     居所=reside[p], 性别=gender[p],
                     度=int(G.degree(p)), 出度=int(D.out_degree(p)), 入度=int(D.in_degree(p)),
                     介数=round(btw[p], 4), 接近度=round(clo[p], 4),
                     特征向量=round(eig.get(p, 0), 4), PageRank=round(pr[p], 5),
                     kcore=core[p], kcore_融合=core_a[p],
                     约束度=round(cons[p], 3), 有效规模=round(esize[p], 2),
                     社群=comm_of.get(p, -1), 社群_文本=comm10_of.get(p, -1),
                     亲属度=dl[0], 主仆度=dl[1], 社会度=dl[2],
                     多层参与=round(part, 3),
                     文本度=int(GT.degree(p)), 文本加权度=float(GT.degree(p, weight="weight")),
                     融合介数=round(btw_a[p], 4)))
nm = pd.DataFrame(rows)
nm["层内主导"] = nm.apply(lambda r: LAYERS[int(np.argmax([r["亲属度"], r["主仆度"], r["社会度"]]))]
                        if max(r["亲属度"], r["主仆度"], r["社会度"]) > 0 else "无", axis=1)
nm = nm.merge(ts[["人物ID", "提及总数", "出场回数", "首出场", "末出场"]], on="人物ID", how="left")
nm = nm.merge(feats.drop(columns=["人物ID"]) if False else feats, on="人物ID", how="left")
nm = nm.merge(fates[["人物ID", "结局", "结局回目", "结局类别"]], on="人物ID", how="left")
nm.to_csv(PROC / "node_metrics.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------- 社群 vs 府邸
def nmi(a, b):
    a, b = np.asarray(a), np.asarray(b)
    n = len(a); ua, ub = pd.unique(a), pd.unique(b); mi = 0.0
    for x in ua:
        for y in ub:
            nij = np.sum((a == x) & (b == y))
            if nij:
                mi += nij / n * math.log(nij * n / (np.sum(a == x) * np.sum(b == y)))
    ha = -sum(np.sum(a == x) / n * math.log(np.sum(a == x) / n) for x in ua)
    hb = -sum(np.sum(b == y) / n * math.log(np.sum(b == y) / n) for y in ub)
    return mi / math.sqrt(ha * hb) if ha > 0 and hb > 0 else 0.0

def ari(a, b):
    a, b = np.asarray(a), np.asarray(b); n = len(a)
    ua, ub = pd.unique(a), pd.unique(b)
    C = math.comb
    idx = sum(C(int(np.sum((a == x) & (b == y))), 2) for x in ua for y in ub)
    ia = sum(C(int(np.sum(a == x)), 2) for x in ua)
    ib = sum(C(int(np.sum(b == y)), 2) for y in ub)
    exp = ia * ib / C(n, 2); mx = (ia + ib) / 2
    return (idx - exp) / (mx - exp) if mx != exp else 0.0

cc = nm[nm["社群"] >= 0]
summary["community"].update(
    nmi居所=round(nmi(cc["社群"], cc["居所"]), 3),
    ari居所=round(ari(cc["社群"], cc["居所"]), 3),
    nmi血缘=round(nmi(cc["社群"], cc["血缘家族"]), 3),
    nmi身份=round(nmi(cc["社群"], cc["身份类别"]), 3))

# 社群画像
prof = []
for k in range(len(commr)):
    g = nm[nm["社群"] == k]
    prof.append(dict(id=k, 人数=len(g),
                     主子占比=round((g["身份类别"] == "主子").mean(), 2),
                     仆役占比=round((g["身份类别"] == "仆役").mean(), 2),
                     主居所=g["居所"].mode().iat[0] if len(g) else "",
                     居所集中度=round(g["居所"].value_counts(normalize=True).iat[0], 2) if len(g) else 0,
                     核心成员="、".join(g.nlargest(5, "度")["标准名"])))
summary["community"]["profiles"] = prof

# ---------------------------------------------------------------- 桥接
arts = list(nx.articulation_points(G))
base = max(len(c) for c in nx.connected_components(G))
imp = []
for a in arts:
    H = G.copy(); H.remove_node(a)
    c = max((len(x) for x in nx.connected_components(H)), default=0)
    imp.append(dict(id=a, name=name[a], 度数=G.degree(a), 删后巨块=c, 损失=base - c))
summary["articulation"] = sorted(imp, key=lambda x: -x["损失"])
summary["bridges"] = len(list(nx.bridges(G)))

# ---------------------------------------------------------------- 一致性
rel_pairs = {tuple(sorted((a, b))) for a, b in G.edges()}
txt_pairs = {tuple(sorted((a, b))) for a, b in GT.edges()}
inter = rel_pairs & txt_pairs
summary["edge_overlap"] = dict(rel=len(rel_pairs), text=len(txt_pairs), both=len(inter),
                               jaccard=round(len(inter) / len(rel_pairs | txt_pairs), 3))
ev = rels[rels["主体ID"].isin(pid) & rels["客体ID"].isin(pid)]
summary["evidence"] = dict(edges=int(len(ev)), zero=int((ev["同回共现"] == 0).sum()),
                           median=float(ev["同回共现"].median()),
                           low=int((ev["同回共现"] <= 2).sum()))
summary["evidence"]["弱证据样本"] = [
    dict(主体=r["主体"], 关系=r["关系"], 客体=r["客体"], 共现=int(r["同回共现"]))
    for _, r in ev.nsmallest(12, "同回共现").iterrows()]

# 孤岛
iso = nm[nm["度"] == 0]
summary["isolates"] = dict(
    rel_total=int(len(iso)), 文本接入=int((iso["文本度"] > 0).sum()),
    仅文本层可见=sorted(iso[iso["文本度"] > 0]["标准名"].tolist()),
    全无=int((iso["文本度"] == 0).sum()),
    全无名=sorted(iso[iso["文本度"] == 0]["标准名"].tolist()))

# ---------------------------------------------------------------- 时序
peri = json.load(open(PROC / "chapter_cast.json", encoding="utf-8"))
ch_rows = []
for ch in range(1, 121):
    ids = [p for p in peri.get(str(ch), []) if p in pid]
    H = GT.subgraph(ids)
    ch_rows.append(dict(回=ch, 人数=len(ids),
                        内部共现密度=round(nx.density(H), 3) if len(ids) > 1 else 0,
                        内部共现边=int(H.number_of_edges()),
                        内部聚类=round(nx.average_clustering(H), 3) if len(ids) > 2 else 0))
cm = pd.DataFrame(ch_rows)
cm["段"] = np.where(cm["回"] <= 80, "前80回", "后40回")

# 十年块（每 10 回）重建共现网络
block_rows = []
pc["块"] = ((pc["回"] - 1) // 10 + 1)
for blk in range(1, 13):
    sub_df = pc[pc["块"] == blk]
    ids = sorted(set(sub_df["人物ID"]))
    H = nx.Graph()
    per_ch = {c: set(g["人物ID"]) for c, g in sub_df.groupby("回")}
    pairs = {}
    for c, s in per_ch.items():
        s = sorted(s)
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                pairs[(s[i], s[j])] = pairs.get((s[i], s[j]), 0) + 1
    for (a, b), w in pairs.items():
        H.add_edge(a, b, weight=w)
    top = sub_df.groupby("人物ID")["次数"].sum().nlargest(5)
    block_rows.append(dict(块=blk, 回段="%d–%d" % (blk * 10 - 9, blk * 10), 人数=len(ids),
                           密度=round(nx.density(H), 4),
                           聚类=round(nx.average_clustering(H), 3),
                           主中心=name[top.index[0]], 前五="、".join(name[i] for i in top.index)))
bm = pd.DataFrame(block_rows)
cm.to_csv(PROC / "chapter_metrics.csv", index=False, encoding="utf-8-sig")
bm.to_csv(PROC / "block_metrics.csv", index=False, encoding="utf-8-sig")
seg = cm.groupby("段")[["人数", "内部共现边", "内部聚类"]].mean().round(3)
print("\n前80/后40：\n", seg.to_string())
print(bm.to_string(index=False))

first = pc[pc["回"] <= 80].groupby("人物ID")["次数"].sum()
last = pc[pc["回"] > 80].groupby("人物ID")["次数"].sum()
both = pd.DataFrame({"前80": first, "后40": last}).fillna(0)
rho, pval = spearmanr(both["前80"], both["后40"])
top_f = set(both.nlargest(20, "前80").index); top_l = set(both.nlargest(20, "后40").index)
summary["authorship"] = dict(
    spearman=round(float(rho), 3), p=float(pval), top20_overlap=len(top_f & top_l),
    new_major=sorted([name[i] for i in (top_l - top_f)]),
    dropped=sorted([name[i] for i in (top_f - top_l)]),
    only_first80_n=len([1 for i in both.index if both.loc[i, "前80"] > 0 and both.loc[i, "后40"] == 0]),
    only_first80=sorted([name[i] for i in both.index
                         if both.loc[i, "前80"] > 0 and both.loc[i, "后40"] == 0])[:20],
    seg=seg.to_dict(), block=bm.to_dict("records"))

# ---------------------------------------------------------------- 跨模态
fz = nm.dropna(subset=["brightness"]).copy()
grp = {k: g for k, g in fz.groupby("身份类别") if len(g) >= 5}
pvals = {}
if "主子" in grp and "仆役" in grp:
    for col in ["brightness", "saturation", "colorfulness", "edge_density"]:
        _, p = mannwhitneyu(grp["主子"][col], grp["仆役"][col])
        pvals[col] = round(float(p), 4)
summary["visual"] = dict(n=int(len(fz)), groups={k: int(len(g)) for k, g in grp.items()},
                         mw_p=pvals,
                         corr_度_饱和=round(float(np.corrcoef(fz["度"], fz["saturation"])[0, 1]), 3),
                         corr_度_亮度=round(float(np.corrcoef(fz["度"], fz["brightness"])[0, 1]), 3),
                         corr_文本度_边缘=round(float(np.corrcoef(
                             fz.dropna(subset=["edge_density"])["文本度"],
                             fz.dropna(subset=["edge_density"])["edge_density"])[0, 1]), 3),
                         hue_top={str(k): int(v) for k, v in fz["hue_main"].value_counts().head(5).items()})
# 图像覆盖 × 身份
cov = persons.copy()
summary["image_coverage"] = {k: dict(n=int(len(g)), 有图=int((g["图像状态_清洗"].isin(
    ["正常", "别名同图", "占位（同图待核）"])).sum()))
    for k, g in cov[cov["合并至"].isna() | (cov["合并至"] == "")].groupby("身份类别")}

# 结局
fc = nm.dropna(subset=["结局类别"])
summary["fate"] = {k: dict(n=int(len(g)), 平均度=round(g["度"].mean(), 2),
                           平均介数=round(g["介数"].mean(), 3),
                           平均kcore=round(g["kcore"].mean(), 2))
                   for k, g in fc.groupby("结局类别")}

summary["top"] = {}
for col in ["度", "介数", "PageRank", "kcore", "文本度", "融合介数"]:
    summary["top"][col] = [dict(name=r["标准名"], v=float(r[col]))
                           for _, r in nm.nlargest(8, col).iterrows()]

# 融合边表
ed = []
for a, b, d in GA.edges(data=True):
    ed.append(dict(a=a, b=b, a_name=name[a], b_name=name[b],
                   rel=d.get("rel", 0), text=d.get("text", 0), w=round(d["w"], 3)))
pd.DataFrame(ed).to_csv(PROC / "edges_combined.csv", index=False, encoding="utf-8-sig")
rels.to_csv(PROC / "relations.csv", index=False, encoding="utf-8-sig")
json.dump(summary, open(PROC / "network_summary.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)

print("\n==", json.dumps({k: summary[k] for k in ["relation", "text", "combined", "community"]},
                         ensure_ascii=False, default=str)[:1200])
print("\n割点 top:", [(d["name"], d["损失"]) for d in summary["articulation"][:10]])
print("NMI 居所=%.3f 血缘=%.3f 身份=%.3f" % (summary["community"]["nmi居所"],
                                            summary["community"]["nmi血缘"],
                                            summary["community"]["nmi身份"]))

