# -*- coding: utf-8 -*-
"""生成 docs/index.html：单文件交互式网络 + 图文报告。"""
import sys, io, json, math
from pathlib import Path
import pandas as pd
import networkx as nx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_common import PROC, DOCS, FIG

S = json.load(open(PROC / "network_summary.json", encoding="utf-8"))
nm = pd.read_csv(PROC / "node_metrics.csv", encoding="utf-8-sig")
rels = pd.read_csv(PROC / "relations.csv", encoding="utf-8-sig")
persons = pd.read_csv(PROC / "persons.csv", encoding="utf-8-sig")
live = persons[persons["合并至"].isna() | (persons["合并至"] == "")]
idx = {p: i for i, p in enumerate(live["人物ID"])}

nodes = []
for _, r in live.iterrows():
    nodes.append(dict(
        id=r["人物ID"], n=r["标准名"], r=r["身份类别"], c=int(nm.set_index("人物ID").loc[r["人物ID"], "社群"]),
        d=int(nm.set_index("人物ID").loc[r["人物ID"], "度"]),
        b=float(round(nm.set_index("人物ID").loc[r["人物ID"], "介数"], 4)),
        t=int(nm.set_index("人物ID").loc[r["人物ID"], "文本度"]),
        k=int(nm.set_index("人物ID").loc[r["人物ID"], "kcore"]),
        h=r["居所"], g=r["性别"],
        al="" if pd.isna(r["别名"]) else r["别名"],
        f="" if pd.isna(nm.set_index("人物ID").loc[r["人物ID"], "结局"]) else
        str(nm.set_index("人物ID").loc[r["人物ID"], "结局"]),
        ch=int(nm.set_index("人物ID").loc[r["人物ID"], "出场回数"] or 0),
        img=("img/%s.webp" % r["人物ID"]) if (DOCS / "img" / (r["人物ID"] + ".webp")).exists() else "",
    ))

links = []
for _, r in rels.iterrows():
    a, b = r["主体ID"], r["客体ID"]
    if a in idx and b in idx and a != b:
        links.append(dict(s=idx[a], t=idx[b], l=r["关系大类"], p=r["关系"]))

sc = pd.read_csv(PROC / "cooccurrence_scene.csv", encoding="utf-8-sig")
tl = [dict(s=idx[r["a"]], t=idx[r["b"]], w=int(r["同场次数"]))
      for _, r in sc[sc["同场次数"] >= 3].iterrows() if r["a"] in idx and r["b"] in idx]

# 预计算布局（ForceAtlas2），网页只负责绘制，不再跑力模拟
G = nx.Graph()
G.add_nodes_from(live["人物ID"])
for _, r in rels.iterrows():
    a, b = r["主体ID"], r["客体ID"]
    if a in idx and b in idx and a != b:
        G.add_edge(a, b)
giant = max(nx.connected_components(G), key=len)
Hh = G.subgraph(giant)
from lib_layout import forceatlas2
POS = forceatlas2(Hh, weight=None, iterations=800, seed=7)
iso_nodes = [n for n in live["人物ID"] if G.degree(n) == 0]
# 孤岛排在外环（按度数 0 均分角度）
for i, n in enumerate(iso_nodes):
    ang = 2 * math.pi * i / max(len(iso_nodes), 1)
    POS[n] = (math.cos(ang) * 1.16, math.sin(ang) * 1.16)
mx = max(max(abs(x), abs(y)) for x, y in POS.values()) or 1.0
for nd in nodes:
    x, y = POS.get(nd["id"], (0.0, 0.0))
    nd["nx"] = round(x / mx, 4)
    nd["ny"] = round(y / mx, 4)

cast_raw = json.load(open(PROC / "chapter_cast.json", encoding="utf-8"))
CAST = {int(k): [idx[x] for x in v if x in idx] for k, v in cast_raw.items()}

DATA = dict(nodes=nodes, links=links, text=tl, cast=CAST,
            stats=dict(n=len(nodes), rel=len(links), text=len(tl),
                       chapters=120, images=len(list((DOCS / "img").glob("*.jpg")))))

ev = S["evidence"]
a = S["authorship"]
c = S["community"]
img_cov = S["image_coverage"]

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>红楼梦人物网络 · 多模态分析</title>
<style>
__CSS__
</style>
</head>
<body>
<header>
  <div class="wrap">
    <div class="seal">红</div>
    <h1>红楼梦人物网络</h1>
    <div class="sub">从 188 条人工关系，到亲属—主仆—社会—文本四层可计算网络</div>
    <div class="kpis">
      <div class="kpi"><b>__N__</b><span>人物</span></div>
      <div class="kpi"><b>__REL__</b><span>关系边</span></div>
      <div class="kpi"><b>__TEXT__</b><span>同场共现</span></div>
      <div class="kpi"><b>120</b><span>回全文</span></div>
      <div class="kpi"><b>__IMG__</b><span>可确认剧照</span></div>
    </div>
  </div>
</header>

<nav><div class="wrap">
  <a href="#clean">01 清洗</a><a href="#graph">02 交互网络</a><a href="#struct">03 结构</a>
  <a href="#comm">04 社群</a><a href="#text">05 文本</a><a href="#time">06 时序</a>
  <a href="#visual">07 图像</a><a href="#method">08 方法</a>
</div></nav>

<section id="clean"><div class="wrap">
  <h2><span class="num">01 / DATA CLEANING</span>先把数据洗干净</h2>
  <p class="lead">原始数据集标着“待清洗”，确实名副其实：179 人里 117 人没有性别、133 人身份“未标注”、
  75 人与关系网络完全断开、180 张图有 20 组是同一张；关系表里还有把惜春记成贾珍之女这类世系错误。
  下面每一类问题都给出了判定规则与处理结果。</p>

  <div class="grid g4">
    <div class="card smallp"><span class="big">117</span><b>性别缺失</b>
      <p>按亲属谓词（父/母/子/女）+ 主仆谓词（丫鬟/小厮）+ 原文考订逐条补齐，现 179/179 完整。</p></div>
    <div class="card smallp"><span class="big">133</span><b>身份未标注</b>
      <p>重建为 主子／妾室／仆役／宗族／客卿／外人 六类，另加“身份细分”（丫鬟、小厮、管家、优伶…）。</p></div>
    <div class="card smallp"><span class="big">75</span><b>网络孤岛</b>
      <p>原文“在关系网=否”。补 23 条文本可证的缺边（平儿、紫鹃、司棋、待书、抱琴…），59 人可由同场共现接回。</p></div>
    <div class="card smallp"><span class="big">20</span><b>同图多人的图源冲突</b>
      <p>按 MD5 归并，一人一图；无法判定归属的整组标“图源冲突”，不硬凑。</p></div>
  </div>

  <h3>关系谓词规范化</h3>
  <p>原表用了 70 余种谓词，其中大量是同义异写：<code>丫环 / 丫头 / 大丫头 / 大丫环 / 陪房丫头</code> 一律归并为
  <code>丫鬟</code>；<code>父→父亲</code>、<code>好兄弟/好朋友→朋友</code>、<code>相好/暧昧→私情</code>。
  归并后再按性别与语义自动生成互逆边（父亲↔儿子/女儿、妻↔丈夫、丫鬟↔主人），
  使“已配对”由原表的 94/188 提升到 293/348。</p>

  <h3>世系纠错</h3>
  <table class="data">
    <tr><th>原表</th><th>问题</th><th>订正</th></tr>
    <tr><td>贾珍 —父亲→ 贾惜春<br>尤氏 —母亲→ 贾惜春</td><td>惜春是贾敬之女、贾珍之妹，尤氏是其嫂</td>
        <td>贾敬 —父亲→ 贾惜春；尤氏 —嫂子→ 贾惜春</td></tr>
    <tr><td>贾迎春 —妻→ 孙绍祖</td><td>方向反了</td><td>贾迎春 —丈夫→ 孙绍祖</td></tr>
    <tr><td>邢岫烟 —妻→ 薛蝌</td><td>方向反了</td><td>邢岫烟 —丈夫→ 薛蝌</td></tr>
    <tr><td>史湘云 —孙女→ 贾母</td><td>湘云是贾母的侄孙女</td><td>史湘云 —侄孙女→ 贾母</td></tr>
    <tr><td>琪官、尤老娘 各立一行</td><td>分别是蒋玉菡的艺名、尤氏继母</td><td>合并实体，保留别名</td></tr>
  </table>

  <figure><img loading="lazy" decoding="async" src="figures/fig9_evidence.webp" alt="关系边的文本证据">
  <figcaption>把关系边放回 120 回全文里检验：<b>__ZERO__ 条边在全书里从未同回出现</b>，中位数 __MED__ 回。
  低频者多为“间接关系”或误标（如把主仆写成亲属），这为后续人工复核提供了排序依据。</figcaption></figure>
</div></section>

<section id="graph"><div class="wrap">
  <h2><span class="num">02 / INTERACTIVE GRAPH</span>把它转起来</h2>
  <p class="lead">节点颜色=身份，大小=所选指标；边为关系三层。<b>三种模式</b>：浏览（点人物看卡片与直接关系）、
  路径（点两人找最短关系链）、移除（点人物把他拿掉，看网络断成几块）。底部时间轴可按回筛选出场人物，并支持自动播放。</p>
  <div id="net-wrap">
    <canvas id="cv"></canvas>
    <div class="panel">
      <div class="ttl">图层</div>
      <label><input type="checkbox" class="rel" value="亲属关系" checked><span class="dot" style="background:#b03a2e"></span>亲属关系</label>
      <label><input type="checkbox" class="rel" value="主仆关系" checked><span class="dot" style="background:#4f81bd"></span>主仆关系</label>
      <label><input type="checkbox" class="rel" value="社会关系" checked><span class="dot" style="background:#7fa86a"></span>社会关系</label>
      <label><input type="checkbox" id="showText"><span class="dot" style="background:#4a5260"></span>文本同场共现</label>
      <label><input type="checkbox" id="showIso"><span class="dot" style="background:#5d6572"></span>孤岛人物（65）</label>
      <div class="ttl">节点大小</div>
      <div class="row">
        <select id="metric" style="width:100%;background:#fbf7ee;color:#2b2723;border:1px solid #e2d7c3;border-radius:7px;padding:6px;font-size:14px;font-family:inherit">
          <option value="d">关系度数</option><option value="b">介数中心性</option>
          <option value="t">文本共现度</option><option value="k">k-core</option>
        </select>
      </div>
      <div class="ttl">标签密度</div>
      <input type="range" id="lab" min="0" max="40" value="14">
      <input id="search" placeholder="搜索人物…">
      <div class="ttl">社群筛选</div>
      <div id="commlegend" class="commlegend"></div>
      <div style="margin-top:10px"><span class="chip"><span class="dot" style="background:#b03a2e"></span>主子</span>
      <span class="chip"><span class="dot" style="background:#d68910"></span>妾室</span>
      <span class="chip"><span class="dot" style="background:#2e86c1"></span>仆役</span>
      <span class="chip"><span class="dot" style="background:#16a085"></span>客卿</span>
      <span class="chip"><span class="dot" style="background:#7f8c8d"></span>外人</span></div>
    </div>
    <div id="detail"><span class="close" id="closeD">×</span><div id="dbody"></div></div>
    <div class="tools">
      <button data-mode="browse" class="on">浏览</button>
      <button data-mode="path">路径</button>
      <button data-mode="remove">移除</button>
      <span id="toolhint">点击人物查看卡片</span>
    </div>
    <div class="timebar">
      <input type="range" id="chap" min="0" max="120" value="0">
      <div class="row"><span id="chaplab">全部 120 回</span>
        <span><button id="play">▶ 播放</button>
        <select id="speed"><option value="700">0.6×</option><option value="420" selected>1×</option><option value="200">2×</option></select>
        <button id="resetView">复位</button></span></div>
    </div>
    <div class="tip" id="tip"></div>
  </div>
</div></section>

<section id="struct"><div class="wrap">
  <h2><span class="num">03 / STRUCTURE</span>谁不可替代</h2>
  <p class="lead">关系网络极稀疏（密度 __DENS__），109 人的巨连通块却只有 9 跳直径——一个“小世界”。
  度、介数、PageRank 三种口径给出的答案并不相同，这正是多层网络有意思的地方。</p>
  <figure><img loading="lazy" decoding="async" src="figures/fig1_relation_network.webp" alt="关系网络">
  <figcaption>巨连通块 109 人、159 条关系，按 Louvain 社群着色。可以看到荣国府一侧几乎被王夫人、贾母、
  贾政、宝玉切成若干“院”，宁国府（绿）与薛家（橙）各自成团。</figcaption></figure>

  <figure><img loading="lazy" decoding="async" src="figures/fig12_layers.webp" alt="三层分解">
  <figcaption>把同一张图按关系大类拆成三层：<b>亲属层 76 人 / 104 边</b>是骨架，
  <b>主仆层 53 人 / 39 边</b>是若干放射状“星”（每个主子挂一串丫鬟小厮），
  <b>社会层只有 19 人 / 16 边</b>——所谓“朋友”在这部小说里是稀缺资源。</figcaption></figure>
  <div class="grid g3">
    <div class="card smallp"><b>贾宝玉</b><p>度 28、介数 0.214、有效规模 26.5、约束度 0.063——他是唯一横跨亲属、主仆、社会三层的枢纽，
    “结构洞”几乎全部经由他打通。</p></div>
    <div class="card smallp"><b>王夫人</b><p>度 13 却介数第二（0.087）。她连接的是“主子—仆役”过渡带（金钏、玉钏、彩云、周瑞家的），
    是荣国府内务的实际路由。</p></div>
    <div class="card smallp"><b>贾惜春</b><p>度只有 4，介数却排第四（0.048）。她与宁国府的血缘、与荣国府的居住、与佛门的归宿，
    三重身份让她成为三块之间的“窄门”。</p></div>
  </div>
  <figure><img loading="lazy" decoding="async" src="figures/fig3_centrality.webp" alt="中心性">
  <figcaption>三把尺子量同一个人：宝玉在三种口径下都第一；王熙凤 PageRank 低于贾母但介数接近，
  说明她“影响大而路径短”；贾政度很高但介数偏低——他是“门面”而非“通道”。</figcaption></figure>

  <figure><img loading="lazy" decoding="async" src="figures/fig15_centrality_heatmap.webp" alt="中心性热图">
  <figcaption>24 位主要人物的六种中心性并排（列内归一化）。贾宝玉整行几乎全亮；
  王夫人「介数高、度中」；贾惜春「度低、介数高」——三处不一致本身就是结论：
  不同中心性测的是“位置”的不同侧面。</figcaption></figure>
  <figure><img loading="lazy" decoding="async" src="figures/fig5_core_periphery.webp" alt="核心边缘">
  <figcaption>k-core 只有 3 层，说明这部小说的人物网络“薄而宽”：核心并非层层嵌套，而是一个扁平的核心圈
  加大量依附其上的卫星人物。</figcaption></figure>

  <figure><img loading="lazy" decoding="async" src="figures/fig13_degree_dist.webp" alt="度分布">
  <figcaption>两种网络的不同“形状”：关系层是重尾（多数人 1–2 个关系，极少数人二三十个），
  文本同场层则接近均匀——因为“同场”是场景决定的，人人都有机会出场。</figcaption></figure>

  <figure><img loading="lazy" decoding="async" src="figures/fig14_cutpoints.webp" alt="割点">
  <figcaption>拿掉贾宝玉：巨连通块从 109 人掉到 96 人，另外裂出 9 块小碎片。
  这些碎片不是别的人物，正是只经由宝玉与外界相连的丫鬟、小厮与外客。</figcaption></figure>

  <figure><img loading="lazy" decoding="async" src="figures/fig18_structural_holes.webp" alt="结构洞">
  <figcaption>结构洞：横轴“有效规模”越大、纵轴“约束度”越低，越接近“桥”。
  宝玉孤悬左下角（有效规模 26.5、约束度 0.063）；薛蟠、薛宝钗等人则聚在右上角——
  他们的关系高度重叠，任何一条都通向同一小圈子。</figcaption></figure>
</div></section>

<section id="comm"><div class="wrap">
  <h2><span class="num">04 / COMMUNITY</span>宗法结构的分形</h2>
  <p class="lead">在关系网络上做 Louvain，得到 9 个社群、模块度 __MOD__。它们几乎逐个对应“房头”：
  宁国府、薛家、凤姐—琏二房、王夫人—元春、贾政—赵姨娘、秦可卿—秦家、邢夫人—邢家，
  以及被单独切出来的“怡红院系”。</p>
  <figure><img loading="lazy" decoding="async" src="figures/fig4_community_mansion.webp" alt="社群与府邸">
  <figcaption>左：社群 × 居所。注意“贾家荣国府”一列被切成 5 段——同一座府邸内部按“房”分裂；
  右：各社群的等级构成，仆役占比高的社群（怡红院、凤姐院）恰恰是关系最密的地方。</figcaption></figure>

  <h3>九房之间并不老死不相往来</h3>
  <p>97 条社群内部的边之外，还有 36 条跨社群边（37%）。它们并非平均分布：宝玉一人贡献 12 条，
  贾政 8 条、王夫人 6 条、贾母 5 条。换句话说，<b>“房”与“房”之间的往来，是由少数几个家长承担的</b>，
  其余人一辈子只在自己那一小块里活动。</p>
  <figure><img loading="lazy" decoding="async" src="figures/fig16_community_matrix.webp" alt="社群邻接矩阵">
  <figcaption>左：社群 × 社群的边数，对角线是各社群内部的“芯”；右：跨社群边最多的 14 人。</figcaption></figure>

  <h3>家户：手下有几个人</h3>
  <p>把主仆关系还原成二部图，班底大小一目了然：宝玉 11 人、王夫人 6 人、贾母 4 人、黛玉 3 人。
  <b>荣国府的家务权力，先看“手下有几个人”</b>。而全府只有一对主子共用仆人——贾母与黛玉共用紫鹃，
  正对应“紫鹃原是贾母的丫头，给了黛玉”。制度的刚性，在这里表现为一个几乎为零的数字。</p>
  <figure><img loading="lazy" decoding="async" src="figures/fig17_bipartite.webp" alt="主仆二部图">
  <figcaption>左列主子（按班底大小排序），右列其丫鬟、小厮、陪房；38 名仆役、16 位主子。</figcaption></figure>
  <blockquote>府邸只能解释 __NMI__（NMI），血缘解释 __NMIB__。真正切分网络的不是“住在哪”，
  而是“跟着谁吃饭”——宗法共同体的最小单位是“房”，不是“府”。</blockquote>
  <p>另一个值得注意的现象：把同样的算法用在<b>文本同场网络</b>上，模块度只有 __TMOD__。
  也就是说，小说的“舞台”本身是高度整合的——宝玉几乎和所有人同场；而制度性的亲属/主仆关系才是
  把这张舞台切成碎块的力量。<b>文本层的低模块度 × 关系层的高模块度</b>，正是“人情社会的表层”与
  “宗法结构的里层”之间的落差。</p>
</div></section>

<section id="text"><div class="wrap">
  <h2><span class="num">05 / TEXT LAYER</span>被表格漏掉的人</h2>
  <p class="lead">原表 179 人里有 65 人没有任何关系边——包括平儿、紫鹃、司棋、待书、抱琴这些大丫鬟。
  这不是她们不重要，而是编表时“只记主仆、不记丫鬟网络”。用 120 回全文的 400 字同场窗口重建后，
  59 人可以接回主网。</p>
  <figure><img loading="lazy" decoding="async" src="figures/fig2_fused_network.webp" alt="融合网络">
  <figcaption>内圈＝原表已录入的 114 人；外环＝原表“关系网外”、但文本仍在场的 59 人，灰虚线指向其最强的同场伙伴。
  外环里能认出宝玉的小厮（茗烟、锄药、扫红）、贾母的丫鬟（琥珀、翡翠、玻璃）、十二官与清客。</figcaption></figure>
  <p>文本层还给出一个反直觉的结果：<b>丫鬟网络不是“星形”而是“链形”</b>。以袭人为例，她与宝玉的同场次数极高，
  但与晴雯、麝月、秋纹的同场次数同样高——怡红院内部是一个近乎完全图的小团体，
  宝玉只是其对外接口。这也解释了为什么“宝玉—袭人”在介数上并不突出：<i>捷径被内部稠密性抵消了</i>。</p>
</div></section>

<section id="time"><div class="wrap">
  <h2><span class="num">06 / TIME</span>舞台从谁身上移开</h2>
  <p class="lead">把 120 回切成 12 个十年块，重建每块的同场共现网络，能看到人物戏份的此消彼长：
  袭人、晴雯在第 8 块（71–80 回）后急剧退场，紫鹃、王夫人在 81–100 回抬头，薛宝钗在最后两块回到中心。</p>
  <figure><img loading="lazy" decoding="async" src="figures/fig6_temporal.webp" alt="时序">
  <figcaption>上排：每回出场人数与内部共现密度，虚线为第 80 回。下：主要人物出场强度热图。
  “抄检大观园”（74 回）之后，网络从“园中群像”退回到“府内家长”。</figcaption></figure>
  <figure><img loading="lazy" decoding="async" src="figures/fig7_authorship.webp" alt="前后80回">
  <figcaption>前 80 回与后 40 回的人物戏份高度连续：Spearman ρ=__RHO__，前 20 名重合 __OVER__ 人。
  这更像“同一舞台的延续”而非“另起炉灶”；但后 40 回确实有新面孔进入前列（__NEW__）。
  该指标只说明文本层面的连续性，<b>不足以单独判定作者归属</b>。</figcaption></figure>

  <figure><img loading="lazy" decoding="async" src="figures/fig20_temporal_centrality.webp" alt="时序中心性">
  <figcaption>把 120 回切成 12 块、每块重建同场网络：宝玉的“度”一路高企，但“介数”在第 8 块
  （71–80 回）之后明显下滑——抄检大观园之后，他不再是各房之间的必经之路。</figcaption></figure>

  <figure><img loading="lazy" decoding="async" src="figures/fig19_fate.webp" alt="命运与位置">
  <figcaption>结局 × 介数：<b>死亡组的中位数反而最低</b>——死亡并不专属于主角，大量边缘人物是“无声退场”；
  而<b>出家组</b>（宝玉、惜春、紫鹃、甄士隐）介数最高。戏份与退场早晚也没有明显关系。</figcaption></figure>
</div></section>

<section id="visual"><div class="wrap">
  <h2><span class="num">07 / IMAGE MODALITY</span>脸能不能解释位置</h2>
  <p class="lead">127 张可确认的人物剧照提取了亮度、饱和度、色彩丰富度、边缘密度与主色相，再与身份、网络指标对照。
  结论有点扫兴但很诚实：<b>视觉特征与网络位置几乎不相关</b>（度—饱和度 r=__CS__，度—亮度 r=__CB__）。</p>
  <figure><img loading="lazy" decoding="async" src="figures/fig8_visual_modality.webp" alt="图像模态">
  <figcaption>主子与仆役剧照的亮度、饱和度差异均不显著（Mann-Whitney p=__PB__ / __PS__）；
  唯一显著的是边缘密度（p=__PE__），可能来自构图景别而非身份。右图揭示真正的偏差：
  <b>“有图”本身就是一种资源</b>——仆役的图源冲突率远高于主子；另有 20 张根本不是人像（书封、鸳鸯、鹦鹉、琥珀、雕像、文字占位、拼图等），已剔除。</figcaption></figure>
  <figure><img loading="lazy" decoding="async" src="figures/fig10_persona_cards.webp" alt="人物卡">
  <figcaption>多模态人物卡：剧照（图像）＋ 度/介数（网络）＋ 出场回数（文本）。</figcaption></figure>
  <p class="small">说明：原始图源分为 87 版剧照、工笔/绣像与带水印的网络图片三类，年代与风格不统一，
  因此本页只做<b>低层视觉统计</b>，不据此推断人物形象。</p>
</div></section>

<section id="method"><div class="wrap">
  <h2><span class="num">08 / METHOD</span>怎么复现</h2>
  <div class="grid g2">
    <div>
      <h3>数据</h3>
      <p class="small">原始三表 + 178 图（未改动，存 <code>data/raw/</code>）；全文来自公开的 120 回本
      （<code>data/external/hlm_master.txt</code>，85 万字）；清洗与增补结果在 <code>data/processed/</code>，
      人工考订明细在 <code>data/curation/person_curation.csv</code>，每一条都能追到依据。</p>
      <h3>方法</h3>
      <p class="small">人物抽取：别名词典 + 最长匹配 + 泛称（珍珠、琥珀、彩云…）上下文过滤；
      共现：400 字滑动窗口（同场）与章回级（证据）两套；社区：Louvain（关系层）；
      中心性：NetworkX；布局：自实现 ForceAtlas2，静态图与网页共用坐标。</p>
    </div>
    <div>
      <h3>运行</h3>
      <pre>pip install -r requirements.txt
python scripts/02_clean.py     # 清洗＋增补
python scripts/03_text.py      # 全文解析＋共现
python scripts/04_images.py    # 图像去重＋特征
python scripts/05_network.py   # 网络指标
python scripts/06_figures.py   # 静态图
python scripts/07_web.py       # 生成本页</pre>
      <h3>局限</h3>
      <p class="small">① 人物识别基于词典，别名遗漏会造成漏计；② 同场窗口是“阅读经验”的近似，
      不是真的场景切分；③ 结局、部分关系为人工整理，依赖 120 回通行本；④ 图源冲突的 20 组只做了
      “一人一图”收敛，未做真人识别。</p>
    </div>
  </div>
  <p class="small" style="margin-top:22px">数据与代码：<a href="__REPO__">GitHub</a> ·
  原始数据：用户提供的《红楼梦》（部分数据、待清洗）数据集 · 全文：seeed 公开 120 回本 ·
  图源：原数据集附带剧照。本页仅用于研究与教学。</p>
</div></section>

<footer><div class="wrap">
  红楼梦人物网络 · 多模态分析　|　清洗 · 补全 · 网络分析 · 可视化　|　__YEAR__
</div></footer>

<script>
const DATA = __DATA__;
const nodes = DATA.nodes, links = DATA.links, tlinks = DATA.text, CAST = DATA.cast;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let W=0, H=0, DPR=Math.min(window.devicePixelRatio||1,2);
let showText=false, showIso=false, metric='d', labN=14, selected=-1, hover=-1, dragging=-1;
let mode='browse', chap=0, castSet=null, pathA=-1, pathB=-1, pathSeq=[], pathSet=new Set();
const removed=new Set(), commOff=new Set();
const COL={ '主子':'#a4342a','妾室':'#c9862b','仆役':'#3d6a8f','宗族':'#7a5a95','客卿':'#3f8f7a','外人':'#8a8071' };
const LAYER={ '亲属关系':'#b0504a','主仆关系':'#4a7ba3','社会关系':'#7d9459' };
const COMMCOL=['#a4342a','#3d6a8f','#5f7f4a','#9a6a32','#7a5a95','#3f8f7a','#b0603a','#6b7280','#a0486e'];
const activeLayer=new Set(['亲属关系','主仆关系','社会关系']);

const cvWrap=document.getElementById('net-wrap');
const tip=document.getElementById('tip'), toolhint=document.getElementById('toolhint');

function resize(){
  W=cv.clientWidth; H=cv.clientHeight;
  cv.width=W*DPR; cv.height=H*DPR;
  ctx.setTransform(DPR,0,0,DPR,0,0);
  applyLayout();
}
function applyLayout(){
  const s=Math.min(W,H)*0.47;
  const ox=W>900?70:0;
  nodes.forEach(n=>{ n.x=W/2+ox+n.nx*s; n.y=H/2+n.ny*s; });
}
window.addEventListener('resize',resize);

function visible(n){
  if(removed.has(n.id)) return false;
  if(castSet && !castSet.has(n.id)) return false;
  if(commOff.has(n.c)) return false;
  if(!showIso && n.d===0) return false;
  return true;
}
const val=n=>metric==='d'?n.d:metric==='b'?n.b*60:metric==='t'?n.t:n.k*4;
function radius(n){ return 3.6+Math.sqrt(Math.max(val(n),0))*1.7; }

// -------- 邻接（供路径与聚焦）--------
let adj=null;
function buildAdj(){
  adj=nodes.map(()=>[]);
  links.forEach((l,i)=>{
    if(!activeLayer.has(l.l)) return;
    adj[l.s].push([l.t,i]); adj[l.t].push([l.s,i]);
  });
}
function bfs(a,b){
  if(a<0||b<0) return null;
  const prev=new Array(nodes.length).fill(-1), pe=new Array(nodes.length).fill(-1);
  const q=[a]; prev[a]=a;
  while(q.length){
    const u=q.shift();
    if(u===b) break;
    for(const [v,ei] of adj[u]){
      if(prev[v]===-1 && visible(nodes[v])){ prev[v]=u; pe[v]=ei; q.push(v); }
    }
  }
  if(prev[b]===-1) return null;
  const seq=[], es=[];
  let cur=b;
  while(cur!==a){ seq.push(cur); es.push(pe[cur]); cur=prev[cur]; }
  seq.push(a); seq.reverse(); es.reverse();
  return {seq, es};
}

const zoom={s:1,x:0,y:0};
function draw(){
  ctx.clearRect(0,0,W,H);
  ctx.save();
  ctx.translate(zoom.x+W/2,zoom.y+H/2); ctx.scale(zoom.s,zoom.s); ctx.translate(-W/2,-H/2);

  const focus=(hover>=0?hover:selected);
  const nbr=new Set();
  if(focus>=0 && mode==='browse'){
    adj[focus].forEach(([v])=>nbr.add(v));
  }
  const dimAll = (focus>=0 && mode==='browse');

  links.forEach((l,i)=>{
    if(!activeLayer.has(l.l)) return;
    const a=nodes[l.s], b=nodes[l.t];
    if(!visible(a)||!visible(b)) return;
    const onPath=pathSet.has(i);
    const near=(focus===l.s||focus===l.t);
    if(dimAll && !onPath && !near){ ctx.globalAlpha=0.10; }
    else if(onPath){ ctx.globalAlpha=1; }
    else { ctx.globalAlpha=near?0.9:0.42; }
    ctx.strokeStyle=onPath?'#c8a24a':LAYER[l.l];
    ctx.lineWidth=onPath?2.8:((l.l==='主仆关系')?1.0:1.25);
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  });

  if(showText){
    ctx.strokeStyle='#b3a58c';
    tlinks.forEach(l=>{
      if(l.w<4) return;
      const a=nodes[l.s], b=nodes[l.t];
      if(!visible(a)||!visible(b)) return;
      ctx.globalAlpha=Math.min(0.05+l.w*0.007,0.30);
      ctx.lineWidth=0.6;
      ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
    });
  }
  ctx.globalAlpha=1;

  const order=nodes.map((n,i)=>i).sort((i,j)=>radius(nodes[i])-radius(nodes[j]));
  order.forEach(i=>{
    const n=nodes[i];
    if(!visible(n)) return;
    const r=radius(n);
    const hl=(i===hover||i===selected);
    const onPath=pathSeq.includes(i);
    const dim=dimAll && !(i===focus||nbr.has(i)) && !onPath;
    if(hl||onPath){
      ctx.beginPath(); ctx.arc(n.x,n.y,r+9,0,7);
      ctx.fillStyle=onPath?'rgba(200,162,74,.28)':'rgba(164,52,42,.12)'; ctx.fill();
    }
    ctx.globalAlpha=dim?0.22:1;
    ctx.beginPath(); ctx.arc(n.x,n.y,r,0,7);
    ctx.fillStyle=COL[n.r]||'#888'; ctx.fill();
    ctx.lineWidth=(hl||onPath)?2.4:1.0;
    ctx.strokeStyle=(hl||onPath)?'#c8a24a':'rgba(255,253,248,.95)';
    ctx.stroke();
  });
  ctx.globalAlpha=1;

  const top=nodes.map((n,i)=>i).filter(i=>visible(nodes[i]))
                  .sort((a,b)=>val(nodes[b])-val(nodes[a])).slice(0,labN);
  ctx.textAlign='center'; ctx.textBaseline='middle';
  top.forEach(i=>{
    const n=nodes[i], r=radius(n);
    ctx.font=(r>11?'14px':'12.5px')+" 'Songti SC','SimSun',serif";
    ctx.lineWidth=3.6; ctx.strokeStyle='rgba(247,243,234,.96)';
    ctx.strokeText(n.n,n.x,n.y+r+10);
    ctx.fillStyle='#2b2723';
    ctx.fillText(n.n,n.x,n.y+r+10);
  });
  ctx.restore();
}
function loop(){
  if(cv.clientWidth>10 && cv.clientHeight>10){
    if(W!==cv.clientWidth || H!==cv.clientHeight) resize();
    draw();
  }
  requestAnimationFrame(loop);
}

// ---------------- 交互 ----------------
let panning=false, last=null;
function pos(e){
  const r=cv.getBoundingClientRect();
  return { x:(e.clientX-r.left-zoom.x-W/2)/zoom.s+W/2,
           y:(e.clientY-r.top-zoom.y-H/2)/zoom.s+H/2 };
}
function pick(p){
  let best=-1,bd=1e9;
  nodes.forEach((n,i)=>{
    if(!visible(n)) return;
    const d=(n.x-p.x)**2+(n.y-p.y)**2;
    if(d<bd && d<(radius(n)+9)**2){ bd=d; best=i; }
  });
  return best;
}
cv.addEventListener('mousedown',e=>{
  const p=pos(e), i=pick(p);
  if(i>=0){
    if(mode==='remove'){
      removed.has(nodes[i].id)?removed.delete(nodes[i].id):removed.add(nodes[i].id);
      updateHint(); return;
    }
    if(mode==='path'){
      if(pathA<0){ pathA=i; updateHint(); }
      else if(pathB<0){ pathB=i; const r=bfs(pathA,pathB);
        pathSeq=r?r.seq:[]; pathSet=new Set(r?r.es:[]);
        showPath(r);
        updateHint();
      }
      else { pathA=i; pathB=-1; pathSeq=[]; pathSet=new Set(); updateHint(); }
      return;
    }
    dragging=i;
  } else { panning=true; last={x:e.clientX,y:e.clientY}; cv.classList.add('drag'); }
});
cv.addEventListener('mousemove',e=>{
  const p=pos(e);
  if(dragging>=0){ const n=nodes[dragging]; n.x=p.x; n.y=p.y; }
  else if(panning){ zoom.x+=e.clientX-last.x; zoom.y+=e.clientY-last.y; last={x:e.clientX,y:e.clientY}; }
  else {
    hover=pick(p); cv.style.cursor=hover>=0?'pointer':'grab';
    if(hover>=0 && mode!=='remove'){
      const n=nodes[hover], r=cvWrap.getBoundingClientRect();
      tip.style.display='block';
      tip.style.left=(e.clientX-r.left+16)+'px';
      tip.style.top=(e.clientY-r.top+14)+'px';
      tip.innerHTML='<b>'+n.n+'</b><span>'+(n.r||'')+' · 度 '+n.d+' · 介数 '+n.b.toFixed(3)+'</span>';
    } else tip.style.display='none';
  }
});
cv.addEventListener('mouseleave',()=>{tip.style.display='none';});
window.addEventListener('mouseup',e=>{
  if(dragging>=0){ if(mode==='browse') select(dragging); dragging=-1; }
  panning=false; cv.classList.remove('drag');
});
cv.addEventListener('wheel',e=>{
  e.preventDefault();
  const f=e.deltaY<0?1.12:1/1.12;
  const r=cv.getBoundingClientRect();
  const mx=e.clientX-r.left-W/2, my=e.clientY-r.top-H/2;
  zoom.x=mx-(mx-zoom.x)*f; zoom.y=my-(my-zoom.y)*f;
  zoom.s=Math.max(0.4,Math.min(5,zoom.s*f));
},{passive:false});

// 侧栏：人物卡 + 直接关系（可点击跳转）
function select(i){
  selected=i;
  const n=nodes[i], d=document.getElementById('detail');
  const rel=links.map((l,k)=>({l,k})).filter(o=>o.l.s===i||o.l.t===i);
  const rows=rel.slice(0,26).map(o=>{
    const other=o.l.s===i?o.l.t:o.l.s;
    const dir=o.l.s===i?'→':'←';
    return '<div class="relrow" data-i="'+other+'"><span>'+dir+' '+o.l.p+'</span>'+nodes[other].n+'</div>';
  }).join('');
  document.getElementById('dbody').innerHTML=
    (n.img?'<img src="'+n.img+'" alt="'+n.n+'">':'')+
    '<h4>'+n.n+'</h4>'+
    '<div class="meta">'+(n.r||'')+' · '+(n.h||'')+' · '+(n.g||'')+'</div>'+
    (n.al?'<div class="meta" style="margin-top:6px">别名：'+n.al+'</div>':'')+
    '<table>'+
    '<tr><td>关系度</td><td>'+n.d+'</td></tr>'+
    '<tr><td>介数</td><td>'+n.b.toFixed(3)+'</td></tr>'+
    '<tr><td>k-core</td><td>'+n.k+'</td></tr>'+
    '<tr><td>文本共现度</td><td>'+n.t+'</td></tr>'+
    '<tr><td>出场回数</td><td>'+n.ch+'</td></tr>'+
    (n.f?'<tr><td>结局</td><td>'+n.f+'</td></tr>':'')+
    '<tr><td>社群</td><td>'+(n.c>=0?('#'+n.c):'—')+'</td></tr>'+
    '</table>'+
    '<div class="relttl">直接关系（点击跳转）</div><div class="rellist">'+rows+'</div>';
  d.style.display='block';
  d.querySelectorAll('.relrow').forEach(el=>el.onclick=()=>{
    const j=+el.dataset.i; select(j); centerOn(j);
  });
}
function centerOn(i){
  zoom.s=1.9; zoom.x=-(nodes[i].x-W/2)*1.9; zoom.y=-(nodes[i].y-H/2)*1.9;
}
document.getElementById('closeD').onclick=()=>{document.getElementById('detail').style.display='none';selected=-1;};

document.querySelectorAll('.rel').forEach(cb=>cb.onchange=()=>{
  if(cb.checked) activeLayer.add(cb.value); else activeLayer.delete(cb.value);
  buildAdj(); if(pathA>=0&&pathB>=0){const r=bfs(pathA,pathB);pathSeq=r?r.seq:[];pathSet=new Set(r?r.es:[]);}
});
document.getElementById('showText').onchange=e=>{showText=e.target.checked;};
document.getElementById('showIso').onchange=e=>{showIso=e.target.checked; updateHint();};
document.getElementById('metric').onchange=e=>{metric=e.target.value;};
document.getElementById('lab').oninput=e=>{labN=+e.target.value;};
document.getElementById('search').oninput=e=>{
  const q=e.target.value.trim();
  if(!q) return;
  const i=nodes.findIndex(n=>n.n.includes(q)||(n.al&&n.al.includes(q)));
  if(i>=0 && visible(nodes[i])){ select(i); centerOn(i); }
};

// 模式切换
document.querySelectorAll('.tools button').forEach(b=>b.onclick=()=>{
  mode=b.dataset.mode;
  document.querySelectorAll('.tools button').forEach(x=>x.classList.toggle('on',x===b));
  if(mode!=='path'){ pathA=pathB=-1; pathSeq=[]; pathSet=new Set(); }
  updateHint();
  cv.style.cursor = mode==='remove'?'crosshair':'grab';
});
function components(){
  const vis=nodes.filter(visible), at=new Map();
  vis.forEach((n,i)=>at.set(n.id,i));
  const par=vis.map((_,i)=>i);
  const find=x=>{ while(par[x]!==x){ par[x]=par[par[x]]; x=par[x]; } return x; };
  links.forEach(l=>{
    if(!activeLayer.has(l.l)) return;
    const a=at.get(nodes[l.s].id), b=at.get(nodes[l.t].id);
    if(a===undefined||b===undefined) return;
    const ra=find(a), rb=find(b); if(ra!==rb) par[ra]=rb;
  });
  const roots=new Set(); vis.forEach((_,i)=>roots.add(find(i)));
  return {n:vis.length, c:roots.size};
}
function updateHint(){
  if(mode==='browse') toolhint.textContent='点击人物查看卡片，悬停高亮邻居';
  else if(mode==='path') toolhint.textContent = pathA<0?'点起点':'点终点（已选起点）';
  else {
    const k=components();
    toolhint.textContent='已移除 '+removed.size+' 人 · 剩 '+k.n+' 人 · '+k.c+' 个连通块';
  }
}
function showPath(r){
  const d=document.getElementById('detail');
  if(!r){
    document.getElementById('dbody').innerHTML='<h4>两人不连通</h4><div class="meta">当前图层下没有通路，试试勾选更多关系层</div>';
    d.style.display='block'; return;
  }
  let html='<h4>关系链</h4><div class="meta">'+(r.seq.length-1)+' 步 · 点击名字可跳转</div><div class="pathlist">';
  r.seq.forEach((ni,k)=>{
    const n=nodes[ni];
    html+='<span class="pnode" data-i="'+ni+'">'+n.n+'</span>';
    if(k<r.es.length){
      const e=links[r.es[k]];
      const SYM=new Set(['兄弟','姐妹','兄妹','表兄妹','朋友','私情','配偶','夫妻']);
      const txt=SYM.has(e.p)?('—'+e.p+'—'):((e.s===ni)?('—'+e.p+'→'):('←'+e.p+'—'));
      html+='<span class="pedge">'+txt+'</span>';
    }
  });
  html+='</div>';
  document.getElementById('dbody').innerHTML=html;
  d.style.display='block';
  d.querySelectorAll('.pnode').forEach(el=>el.onclick=()=>{
    const j=+el.dataset.i; select(j); centerOn(j);
  });
}

// 时间轴
const chapEl=document.getElementById('chap'), chapLab=document.getElementById('chaplab');
function setChapter(v){
  chap=v;
  if(v===0){ castSet=null; chapLab.textContent='全部 120 回'; }
  else {
    const ids=(CAST[v]||[]).map(i=>nodes[i].id);
    castSet=new Set(ids);
    chapLab.textContent='第 '+v+' 回 · '+ids.length+' 人';
  }
  draw();
}
chapEl.oninput=e=>setChapter(+e.target.value);
let timer=null, speed=420;
function tick(){
  if(!timer) return;
  const v = chap>=120?1:chap+1;
  chapEl.value=v; setChapter(v);
  timer=setTimeout(tick, speed);
}
const playBtn=document.getElementById('play');
playBtn.onclick=function(){
  if(timer){ clearTimeout(timer); timer=null; this.textContent='▶ 播放'; return; }
  this.textContent='❚❚ 暂停';
  tick();
};
const spd=document.getElementById('speed');
if(spd) spd.onchange=e=>{ speed=+e.target.value; };
document.getElementById('resetView').onclick=()=>{
  zoom.s=1; zoom.x=0; zoom.y=0;
  removed.clear(); commOff.clear(); pathA=pathB=-1; pathSeq=[]; pathSet=new Set();
  chapEl.value=0; setChapter(0);
  document.querySelectorAll('#commlegend .cl').forEach(x=>x.classList.remove('off'));
  updateHint();
};

// 社群图例
const legend=document.getElementById('commlegend');
const comms=[...new Set(nodes.filter(n=>n.c>=0).map(n=>n.c))].sort((a,b)=>a-b);
comms.forEach(c=>{
  const el=document.createElement('span');
  el.className='cl'; el.dataset.c=c;
  el.innerHTML='<i style="background:'+COMMCOL[c%COMMCOL.length]+'"></i>'+c;
  el.onclick=()=>{
    if(commOff.has(c)){ commOff.delete(c); el.classList.remove('off'); }
    else { commOff.add(c); el.classList.add('off'); }
  };
  legend.appendChild(el);
});

const secs=[...document.querySelectorAll('section')];
window.addEventListener('scroll',()=>{
  const y=window.scrollY+130;
  let cur=secs[0].id;
  secs.forEach(s2=>{ if(s2.offsetTop<=y) cur=s2.id; });
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+cur));
});

buildAdj(); resize(); updateHint(); loop();
</script>
</body>
</html>
"""

html = (HTML.replace("__CSS__", (Path(__file__).with_name("web_theme.css")).read_text(encoding="utf-8"))
            .replace("__DATA__", json.dumps(DATA, ensure_ascii=False, separators=(",", ":")))
            .replace("__N__", str(len(nodes))).replace("__REL__", str(len(links)))
            .replace("__TEXT__", str(len(tl))).replace("__IMG__", str(DATA["stats"]["images"]))
            .replace("__ZERO__", str(ev["zero"])).replace("__MED__", str(int(ev["median"])))
            .replace("__DENS__", str(S["relation"]["density"]))
            .replace("__MOD__", str(c["modularity"]))
            .replace("__NMI__", str(c["nmi居所"])).replace("__NMIB__", str(c["nmi血缘"]))
            .replace("__TMOD__", str(c["text_modularity"]))
            .replace("__RHO__", str(a["spearman"])).replace("__OVER__", str(a["top20_overlap"]))
            .replace("__NEW__", "、".join(a["new_major"]) or "无")
            .replace("__CS__", str(S["visual"]["corr_度_饱和"]))
            .replace("__CB__", str(S["visual"]["corr_度_亮度"]))
            .replace("__PB__", str(S["visual"]["mw_p"].get("brightness")))
            .replace("__PS__", str(S["visual"]["mw_p"].get("saturation")))
            .replace("__PE__", str(S["visual"]["mw_p"].get("edge_density")))
            .replace("__REPO__", "https://github.com/woaadan/hlm-network")
            .replace("__YEAR__", "2026"))

(DOCS / "index.html").write_text(html, encoding="utf-8")
print("index.html 写入：", len(html) / 1024, "KB，节点", len(nodes), "关系边", len(links), "文本边", len(tl))
















