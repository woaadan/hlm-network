# -*- coding: utf-8 -*-
"""统一路径、字体与工具。"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EXT = ROOT / "data" / "external"
CUR = ROOT / "data" / "curation"
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"
DOCS = ROOT / "docs"

for d in (CUR, PROC, FIG, DOCS, DOCS / "figures", DOCS / "img"):
    d.mkdir(parents=True, exist_ok=True)

CJK = "Microsoft YaHei"
PAPER = "#f7f3ea"      # 宣纸底色：网页与图共用，避免白底突兀
INK = "#2b2723"
def setup_font():
    for name in ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"]:
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 150
    plt.rcParams["savefig.dpi"] = 200
    plt.rcParams["savefig.bbox"] = "tight"
    plt.rcParams["figure.facecolor"] = PAPER
    plt.rcParams["axes.facecolor"] = PAPER
    plt.rcParams["savefig.facecolor"] = PAPER
    plt.rcParams["text.color"] = INK
    plt.rcParams["axes.labelcolor"] = INK
    plt.rcParams["axes.edgecolor"] = "#b9ad99"
    plt.rcParams["axes.linewidth"] = 0.8
    plt.rcParams["xtick.color"] = "#5b544a"
    plt.rcParams["ytick.color"] = "#5b544a"
    plt.rcParams["grid.color"] = "#ddd2be"
    plt.rcParams["legend.facecolor"] = PAPER
    plt.rcParams["legend.edgecolor"] = "none"

# 统一配色
LAYER_COLOR = {"亲属关系": "#C0504D", "主仆关系": "#4F81BD", "社会关系": "#9BBB59"}
ROLE_COLOR = {"主子": "#B03A2E", "妾室": "#D68910", "仆役": "#2E86C1",
              "宗族": "#7D3C98", "客卿": "#16A085", "外人": "#7F8C8D"}
