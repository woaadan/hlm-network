# -*- coding: utf-8 -*-
"""ForceAtlas2 布局（numpy 实现），供静态图与网页共用。"""
import numpy as np
import networkx as nx


def forceatlas2(G, weight="weight", iterations=900, seed=42, kr=1.0, ka=1.0,
                gravity=0.06, dt=0.05, max_step=0.5):
    rng = np.random.default_rng(seed)
    nodes = list(G)
    n = len(nodes)
    ix = {v: i for i, v in enumerate(nodes)}
    pos = rng.normal(size=(n, 2))
    deg = np.array([G.degree(v) for v in nodes], dtype=float)
    if G.number_of_edges():
        e = np.array([[ix[a], ix[b], G[a][b].get(weight, 1.0)] for a, b in G.edges()], dtype=float)
    else:
        e = np.zeros((0, 3))
    mass = deg + 1.0
    for it in range(iterations):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((delta ** 2).sum(-1)) + 1e-9
        np.fill_diagonal(dist, 1e9)
        # 斥力：与度数乘积成正比、与距离成反比
        rep = (kr * mass[:, None] * mass[None, :] / dist)[:, :, None] * (delta / dist[:, :, None])
        force = rep.sum(axis=1)
        # 引力
        if len(e):
            i, j, w = e[:, 0].astype(int), e[:, 1].astype(int), e[:, 2]
            d = pos[i] - pos[j]
            dd = np.sqrt((d ** 2).sum(1)) + 1e-9
            att = (ka * w * dd)[:, None] * (d / dd[:, None])
            np.add.at(force, i, -att)
            np.add.at(force, j, att)
        # 向心引力，防止漂散
        force -= gravity * mass[:, None] * pos
        step = dt * force
        ln = np.sqrt((step ** 2).sum(1))
        scale = np.minimum(1.0, max_step / np.maximum(ln, 1e-9))
        pos += step * scale[:, None]
    pos -= pos.mean(0)
    s = np.abs(pos).max()
    if s > 0:
        pos /= s
    return {v: pos[i] for i, v in enumerate(nodes)}


def pack_with_isolates(G, pos, iso_nodes, radius=1.25):
    """把度数为 0 的孤点排在外圈，避免布局被拉散。"""
    out = dict(pos)
    if not iso_nodes:
        return out
    k = len(iso_nodes)
    for i, v in enumerate(iso_nodes):
        a = 2 * np.pi * i / k
        out[v] = np.array([radius * np.cos(a), radius * np.sin(a)])
    return out
