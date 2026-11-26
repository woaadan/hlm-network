# -*- coding: utf-8 -*-
"""图像模态：去重定权、错图判定、色彩/构图特征提取。

原表 180 张图里有 20 组 MD5 完全相同（39 人被“共用”一张图），说明图源填充时发生串图。
本脚本对每组按“网络度数最高者持有、其余标冲突”收敛为一人一图，并把图像转成可计算的
低层视觉特征（亮度/饱和度/色彩丰富度/边缘密度/主色相），供后续与网络指标做跨模态比较。
"""
import sys, io, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_common import RAW, PROC, DOCS

IMG = RAW / "images"
persons = pd.read_csv(PROC / "persons.csv", encoding="utf-8-sig")
rels = pd.read_csv(PROC / "relations.csv", encoding="utf-8-sig")

# 无向邻居数作为“持图优先级”
deg = {}
for _, r in rels.iterrows():
    deg.setdefault(r["主体ID"], set()).add(r["客体ID"])
    deg.setdefault(r["客体ID"], set()).add(r["主体ID"])
deg = {k: len(v) for k, v in deg.items()}

ROLE_ORDER = {"主子": 0, "妾室": 1, "宗族": 2, "客卿": 3, "外人": 4, "仆役": 5}

files = sorted(p.name for p in IMG.glob("*.jpg"))
md5 = {f: hashlib.md5((IMG / f).read_bytes()).hexdigest() for f in files}

# 文件名 -> 人物
by_file = {}
for _, r in persons.iterrows():
    f = r["图像文件"]
    if isinstance(f, str) and f.endswith(".jpg"):
        by_file.setdefault(f, []).append(r["人物ID"])
# 图片清单里额外映射（原名/别名文件）
imgs_sheet = pd.read_excel(RAW / "红楼梦_数据集.xlsx", sheet_name="04_图像清单")
for _, r in imgs_sheet.iterrows():
    pid = r["人物ID"]
    fn = r["文件名"]
    if pid in set(persons["人物ID"]):
        by_file.setdefault(fn, [])
        if pid not in by_file[fn]:
            by_file[fn].append(pid)

groups = {}
for f, h in md5.items():
    groups.setdefault(h, []).append(f)

pid_role = dict(zip(persons["人物ID"], persons["身份类别"]))
pid_name = dict(zip(persons["人物ID"], persons["标准名"]))

assign = {}          # pid -> file
status = {}          # pid -> 状态
conflict_groups = []
for h, fs in groups.items():
    pids = []
    for f in fs:
        pids += by_file.get(f, [])
    pids = list(dict.fromkeys(pids))
    if len(set(pids)) <= 1:
        pid = pids[0] if pids else None
        if pid:
            # 同一人的多份文件：取文件名与标准名一致者
            best = next((f for f in fs if Path(f).stem == pid_name[pid]), fs[0])
            assign[pid] = best
            status[pid] = "正常" if len(fs) == 1 else "别名同图"
        continue
    # 多人共用一张图
    ranked = sorted(pids, key=lambda p: (-deg.get(p, 0), ROLE_ORDER.get(pid_role.get(p), 9), p))
    top = ranked[0]
    if deg.get(top, 0) == 0:
        for p in pids:
            status[p] = "图源冲突"
        conflict_groups.append((h[:8], [pid_name[p] for p in pids], None))
    else:
        assign[top] = fs[0]
        status[top] = "占位（同图待核）"
        for p in pids:
            if p != top:
                status[p] = "图源冲突"
        conflict_groups.append((h[:8], [pid_name[p] for p in pids], pid_name[top]))

# 图像特征
def features(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    small = im.resize((128, int(128 * h / w)), Image.LANCZOS) if w >= h else im.resize(
        (int(128 * w / h), 128), Image.LANCZOS)
    a = np.asarray(small).astype(np.float32) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(2), a.min(2)
    v = mx
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    # Hasler-Süsstrunk colorfulness
    rg, yb = r - g, 0.5 * (r + g) - b
    cf = np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    gx = np.abs(np.diff(lum, axis=1)).mean()
    gy = np.abs(np.diff(lum, axis=0)).mean()
    # 主色相（按饱和度加权）
    hsv = np.asarray(small.convert("HSV")).astype(np.float32)
    hue = hsv[..., 0].ravel()
    sat = hsv[..., 1].ravel() / 255.0
    hist, _ = np.histogram(hue, bins=36, range=(0, 255), weights=sat)
    top3 = np.argsort(hist)[-3:][::-1]
    return dict(width=w, height=h, aspect=round(w / h, 3),
                brightness=round(float(lum.mean()), 4),
                contrast=round(float(lum.std()), 4),
                saturation=round(float(s.mean()), 4),
                colorfulness=round(float(cf), 4),
                edge_density=round(float((gx + gy) / 2), 4),
                hue_main=int(top3[0] * 360 // 36),
                warm=1 if (top3[0] * 360 // 36) < 60 or (top3[0] * 360 // 36) > 300 else 0)

rows, feats = [], []
for pid in persons["人物ID"]:
    f = assign.get(pid)
    st = status.get(pid, "缺图")
    rows.append(dict(人物ID=pid, 图像文件=f, 图像状态_清洗=st))
    if f:
        fe = features(IMG / f)
        fe["人物ID"] = pid
        feats.append(fe)

im = pd.DataFrame(rows)

# 经人工目视复核：以下条目的图根本不是人物像（冰纹、云盘图标、玉石、雕像、文字占位）
NOT_PORTRAIT = {
    "玻璃": "冰裂纹理图",
    "彩云": "云盘 app 图标",
    "翡翠": "玉石照片",
    "张华": "石雕像",
    "东平王": "骑马雕像",
    "住儿": "纯文字占位图",
    "庆儿": "纯文字占位图",
    # 第二轮：逐张目视复核后确认的“望文生义图”、书封与拼图
    "鸳鸯": "鸳鸯戏水照片（望文生义）",
    "彩凤": "鹦鹉照片（望文生义）",
    "琥珀": "琥珀珠照片（望文生义）",
    "李贵": "《红楼梦》书封",
    "宋嬷嬷": "《红楼梦》书封",
    "甄应嘉": "《红楼梦》书封",
    "程日兴": "《红楼梦》书封",
    "王子腾": "群马图（非人物）",
    "载权": "女性绣像（图不对人）",
    "邓好时": "女性绣像（图不对人）",
    "彩儿": "四人拼图（非单人像）",
    "侍画": "视频截图（多人同框）",
    "蒋玉菡": "情节插画（非人物像）",
}
for i, r in im.iterrows():
    nm_ = pid_name.get(r["人物ID"])
    if nm_ in NOT_PORTRAIT:
        im.at[i, "图像状态_清洗"] = "非人物像"
        im.at[i, "图像校注"] = NOT_PORTRAIT[nm_]
        im.at[i, "图像文件"] = None

persons = persons.drop(columns=[c for c in persons.columns if c.startswith("图像状态_清洗")],
                       errors="ignore")
persons = persons.drop(columns=["图像状态", "图像文件"], errors="ignore").merge(
    im, on="人物ID", how="left")
persons.to_csv(PROC / "persons.csv", index=False, encoding="utf-8-sig")

ft = pd.DataFrame(feats)
ft = ft[~ft["人物ID"].isin({p for p, n in pid_name.items() if n in NOT_PORTRAIT})]
ft.to_csv(PROC / "image_features.csv", index=False, encoding="utf-8-sig")

# 复制到网页目录（一人一图，文件名用人物ID）；非人物像不复制
excl_ids = {pid for pid, n in pid_name.items() if n in NOT_PORTRAIT}
for pid, f in assign.items():
    dst = DOCS / "img" / (pid + ".jpg")
    if pid in excl_ids:
        if dst.exists():
            dst.unlink()
        continue
    dst.write_bytes((IMG / f).read_bytes())

print("图像状态：", persons["图像状态_清洗"].value_counts().to_dict())
print("冲突组数：", len(conflict_groups))
for g in conflict_groups:
    print("   %s  共用者=%s  保留=%s" % g)
print("特征表：", ft.shape, "列：", list(ft.columns))
print(ft[["brightness", "saturation", "colorfulness", "edge_density"]].describe().round(3).to_string())
json.dump([dict(md5=g[0], members=g[1], keeper=g[2]) for g in conflict_groups],
          open(PROC / "image_conflicts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


