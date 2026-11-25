# -*- coding: utf-8 -*-
"""原始数据体检：把可疑之处逐条列出来，供清洗规则设计使用。"""
import sys, io, hashlib, collections, json
from pathlib import Path
import pandas as pd
import openpyxl

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
XLSX = RAW / "红楼梦_数据集.xlsx"
IMGDIR = RAW / "images"

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
sheets = {s.title: pd.DataFrame(list(s.iter_rows(values_only=True))[1:],
                                columns=list(s.iter_rows(values_only=True))[0])
          for s in wb.worksheets}

persons = sheets["01_人物主表"]
rels = sheets["02_关系三元组"]
profile = sheets["03_人物档案"]
imgs = sheets["04_图像清单"]
alias = sheets["05_别名映射"]

print("=" * 78)
print("规模：persons %s, rels %s, profile %s, imgs %s, alias %s" %
      (persons.shape, rels.shape, profile.shape, imgs.shape, alias.shape))
print("=" * 78)

# ---------- 1 人物表 ----------
print("\n[1] 人物主表缺失值（按列）")
print(persons.isna().sum().to_string())

print("\n[1b] 性别分布：")
print(persons["性别"].fillna("(空)").value_counts().to_string())
print("\n[1c] 身份类别分布：")
print(persons["身份类别"].fillna("(空)").value_counts().to_string())
print("\n[1d] 家族归属分布：")
print(persons["家族归属"].fillna("(空)").value_counts().to_string())
print("\n[1e] 在关系网：", persons["在关系网"].value_counts().to_dict())
print("\n[1f] 图像状态：", persons["图像状态"].value_counts().to_dict())
print("\n[1g] 关系数 与 出度+入度 不一致的行：")
bad = persons[persons["关系数"] != persons["出度"] + persons["入度"]]
print(bad[["人物ID", "标准名", "关系数", "出度", "入度"]].to_string())

print("\n[1h] 重复标准名：")
dup = persons[persons.duplicated("标准名", keep=False)]
print(dup.sort_values("标准名")[["人物ID", "标准名", "别名", "家族归属"]].to_string())

print("\n[1i] 人物ID 是否连续唯一：", persons["人物ID"].is_unique,
      "编号范围", persons["人物ID"].min(), persons["人物ID"].max())

# ---------- 2 关系表 ----------
print("\n[2] 关系三元组")
print("[2a] 关系大类：", rels["关系大类"].value_counts().to_dict())
print("[2b] 关系（谓词）频次 top30：")
print(rels["关系"].value_counts().head(30).to_string())
print("[2c] 互逆配对：", rels["已配对"].value_counts().to_dict())
print("[2d] 未配对条数，按关系：")
print(rels[rels["已配对"] == "否"]["关系"].value_counts().to_string())

# 悬空 ID
pid = set(persons["人物ID"])
for c in ["主体ID", "客体ID"]:
    miss = set(rels[c]) - pid
    print(f"[2e] {c} 悬空引用:", miss)

# 自环
selfloops = rels[rels["主体ID"] == rels["客体ID"]]
print("[2f] 自环:", selfloops.shape[0])

# 主体名称与 ID 不一致
name2id = dict(zip(persons["标准名"], persons["人物ID"]))
for side in ["主体", "客体"]:
    m = rels[~rels.apply(lambda r: name2id.get(r[side]) == r[side + "ID"], axis=1)]
    print(f"[2g] {side}名/ID 不一致:", len(m))
    if len(m):
        print(m.head(10)[[side, side + "ID"]].to_string())

# 府邸标注是否与人物表一致
p_house = dict(zip(persons["人物ID"], persons["家族归属"]))
for side in ["主体", "客体"]:
    m = rels[rels.apply(lambda r: p_house.get(r[side + "ID"]) != r[side + "府邸"], axis=1)]
    print(f"[2h] {side}府邸与人物表不一致:", len(m))
    if len(m):
        print(m.head(8)[[side, side + "ID", side + "府邸"]].to_string())

# 重复三元组
trip = rels.duplicated(["主体ID", "关系", "客体ID"], keep=False)
print("[2i] 完全重复的三元组:", trip.sum())

# 互逆关系词表核对
inv_pairs = collections.Counter(zip(rels["关系"], rels["互逆关系"]))
print("[2j] (关系,互逆关系) 组合：")
for k, v in inv_pairs.most_common():
    print("   ", k, v)

# ---------- 3 人物档案 ----------
print("\n[3] 人物档案")
print("[3a] 属性分组:", profile["属性分组"].value_counts().to_dict())
print("[3b] 属性 top20:")
print(profile["属性"].value_counts().head(20).to_string())
print("[3c] 值类型:", profile["值类型"].value_counts().to_dict())
print("[3d] 空值:", profile.isna().sum().to_dict())
print("[3e] 涉及人物数:", profile["人物ID"].nunique(), "/ 人物表", persons["人物ID"].nunique())
noprof = pid - set(profile["人物ID"])
print("[3f] 无档案人物数:", len(noprof), list(noprof)[:20])

# ---------- 4 图像 ----------
print("\n[4] 图像清单")
print("[4a] 图像状态:", imgs["图像状态"].value_counts().to_dict())
print("[4b] 重复组:", imgs["重复组"].value_counts(dropna=False).head(20).to_dict())
dups = imgs[imgs["重复组"].notna()]
print("[4c] 重复组明细：")
print(dups[["姓名", "人物ID", "文件名", "大小KB", "宽", "高", "MD5前8", "重复组", "同组其他人物", "图像状态"]].sort_values("重复组").to_string())

files = sorted(p.name for p in IMGDIR.glob("*"))
listed = set(imgs["文件名"])
print("\n[4d] 磁盘文件数:", len(files), " 清单行数:", len(imgs))
print("[4e] 磁盘有但清单无:", sorted(set(files) - listed))
print("[4f] 清单有但磁盘无:", sorted(listed - set(files)))

# 真实 MD5 重算
md5 = {}
for f in files:
    md5[f] = hashlib.md5((IMGDIR / f).read_bytes()).hexdigest()[:8]
g = collections.defaultdict(list)
for f, h in md5.items():
    g[h].append(f)
print("[4g] 实际 MD5 重复组：")
for h, fs in g.items():
    if len(fs) > 1:
        print("   ", h, fs)

# 尺寸异常（与清单宽高对比）
from PIL import Image
bad_size = []
for f in files:
    with Image.open(IMGDIR / f) as im:
        w, h = im.size
    row = imgs[imgs["文件名"] == f]
    if len(row):
        rw, rh = int(row.iloc[0]["宽"]), int(row.iloc[0]["高"])
        if (w, h) != (rw, rh):
            bad_size.append((f, (w, h), (rw, rh)))
print("[4h] 清单宽高与实际不符:", len(bad_size), bad_size[:10])

# 名字与清单不符
print("[4i] 文件名与姓名不一致：")
m = imgs[imgs.apply(lambda r: Path(str(r["文件名"])).stem != str(r["姓名"]), axis=1)]
print(m[["姓名", "文件名"]].to_string())

# ---------- 5 别名 ----------
print("\n[5] 别名映射")
print(alias.to_string())

# ---------- 6 图像三种状态 ----------
print("\n[6] 映射到图片后仍缺图的人物：")
print(imgs[imgs["图像状态"] != "正常"][["姓名", "图像状态"]].to_string())
