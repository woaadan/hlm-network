# -*- coding: utf-8 -*-
"""清洗主脚本：人物 / 关系 / 别名 / 结局。

处理内容
--------
1. 人物：补齐性别(117)、身份(75 个“未标注”)、居所；合并重复实体（琪官→蒋玉菡、尤老娘→尤氏继母）；
   补 2 个缺失人物（周姨娘、文官）；补别名。
2. 关系：谓词规范化（丫环/丫头/大丫头…→丫鬟）、去重、纠错（惜春世系、迎春/岫烟婚向、湘云称谓）、
   补 20 条文本可证的缺边、按性别与语义自动补互逆边。
3. 落盘 data/processed/*.csv + data/curation/person_curation.csv（可审计）。
"""
import sys, io
from pathlib import Path
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_common import RAW, PROC, CUR
from curation_data import CURATION, MERGE, PRED

# ---------------------------------------------------------------- 读取
persons = pd.read_csv(RAW / "hlm_persons.csv", encoding="utf-8-sig")
rels = pd.read_csv(RAW / "hlm_relations.csv", encoding="utf-8-sig")
alias = pd.read_csv(RAW / "hlm_images_join.csv", encoding="utf-8-sig") if False else None
import openpyxl
wb = openpyxl.load_workbook(RAW / "红楼梦_数据集.xlsx", read_only=True, data_only=True)
ws_alias = wb["05_别名映射"]
rows = list(ws_alias.iter_rows(values_only=True))
alias = pd.DataFrame(rows[1:], columns=rows[0])

persons = persons.rename(columns={"personId": "人物ID", "name": "标准名", "aliases": "别名",
                                  "gender": "性别", "house": "血缘家族", "role": "身份类别",
                                  "degree": "原关系数"})

# ---------------------------------------------------------------- 1 人物
MISSING_GENDER = persons["性别"].isna().sum()
MISSING_ROLE = (persons["身份类别"] == "未标注").sum()

log = []
persons["居所"] = persons["血缘家族"]
persons["校注"] = ""
persons["新别名"] = ""

for i, r in persons.iterrows():
    name = r["标准名"]
    c = CURATION.get(name)
    if not c:
        continue
    if pd.isna(r["性别"]) or r["性别"] != c["gender"]:
        if pd.isna(r["性别"]):
            log.append(("补性别", name, "空", c["gender"]))
        persons.at[i, "性别"] = c["gender"]
    if r["身份类别"] in ("未标注", None) or pd.isna(r["身份类别"]):
        persons.at[i, "身份类别"] = c["role"]
        log.append(("补身份", name, "未标注", c["role"]))
    if c["blood"]:
        if r["血缘家族"] in ("未标注", "其他", None) or pd.isna(r["血缘家族"]):
            persons.at[i, "血缘家族"] = c["blood"]
            log.append(("补血缘家族", name, r["血缘家族"], c["blood"]))
    if c["reside"]:
        persons.at[i, "居所"] = c["reside"]
    if c["alias"]:
        persons.at[i, "新别名"] = c["alias"]
        log.append(("补别名", name, "", c["alias"]))
    if c["note"]:
        persons.at[i, "校注"] = c["note"]

# 合并重复实体
persons["合并至"] = ""
for src, dst in MERGE.items():
    persons.loc[persons["标准名"] == src, "合并至"] = dst
    log.append(("合并实体", src, "", dst))

# 新增人物（原表缺）
NEW = [
    dict(人物ID="HLM-P180", 标准名="周姨娘", 血缘家族="其他", 居所="贾家荣国府",
         身份类别="妾室", 新别名="", 校注="贾政之妾，与赵姨娘并列；原表漏收"),
    dict(人物ID="HLM-P181", 标准名="文官", 血缘家族="其他", 居所="贾家荣国府",
         身份类别="仆役", 新别名="", 校注="十二官之一；原表仅收十一官，补此以足十二之数"),
]
add = pd.DataFrame(NEW)
add["性别"] = ["女", "女"]
add["别名"] = ""
add["原关系数"] = 0
add["合并至"] = ""
for c in ["图像状态", "图像文件", "在关系网", "身份判定依据", "次属家族", "档案职业",
          "出度", "入度", "度中心性", "介数中心性", "社群"]:
    if c not in add:
        add[c] = None
persons = pd.concat([persons, add], ignore_index=True)
for n in NEW:
    log.append(("新增人物", n["标准名"], "", n["校注"]))

# 身份细分
YAHUAN = set("玉钏儿 金钏儿 鸳鸯 紫鹃 晴雯 袭人 麝月 秋纹 彩云 彩霞 雪雁 莺儿 司棋 侍画 抱琴 入画 "
             "坠儿 碧痕 四儿 小鹊 小蝉 小舍儿 彩儿 彩凤 彩屏 彩明 彩鸾 宝珠 瑞珠 琥珀 翡翠 玻璃 "
             "珍珠 丰儿 柳五儿 傻大姐 宋嬷嬷 张妈妈".split())
XIAOSI = set("茗烟 伴鹤 扫红 锄药 兴儿 昭儿 隆儿 寿儿 喜儿 庆儿 住儿 李十儿 玉柱儿 王柱儿".split())
GUANJIA = set("赖大 赖嬷嬷 周瑞 周瑞家的 林之孝 林之孝家的 吴新登 余信 金文翔 金文翔家的 "
              "王善保 王善保家的 李贵 包勇 吴贵 焦大".split())
YOUGONG = set("芳官 藕官 蕊官 药官 葵官 艾官 豆官 茄官 龄官 宝官 玉官 文官 琪官 蒋玉菡".split())

def fine(r):
    n, role = r["标准名"], r["身份类别"]
    if role == "仆役":
        if n in YOUGONG:
            return "优伶"
        if n in YAHUAN:
            return "丫鬟"
        if n in XIAOSI:
            return "小厮"
        if n in GUANJIA:
            return "管家/婆子"
        return "仆役"
    if role == "客卿":
        return "僧尼" if n in "净虚 圆信 智善 智通 大色空 智能儿 妙玉" else "清客"
    if role == "外人":
        return "内监" if n in "周太监 夏秉忠 载权 裘世安" else "外官/乡绅"
    return ""

persons["身份细分"] = persons.apply(fine, axis=1)

# 别名
name2row = {r["标准名"]: i for i, r in persons.iterrows()}
for _, a in alias.iterrows():
    src, dst = str(a.iloc[0]), str(a.iloc[1])
    i = name2row.get(dst)
    if i is None:
        continue
    cur = persons.at[i, "新别名"]
    persons.at[i, "新别名"] = (cur + "|" + src) if cur else src

def merge_alias(row):
    a = [x for x in str(row["新别名"]).split("|") if x]
    b = [x for x in str(row["别名"]).split("|") if x and str(row["别名"]) != "nan"]
    return "|".join(dict.fromkeys(b + a))
persons["别名"] = persons.apply(merge_alias, axis=1)
persons["别名"] = persons["别名"].replace("", None)

# ---------------------------------------------------------------- 2 关系
rels = rels.rename(columns={"relId": "关系ID", "head": "主体", "headId": "主体ID",
                            "rel": "关系", "bucket": "关系大类",
                            "tail": "客体", "tailId": "客体ID", "paired": "已配对"})
pid2name = dict(zip(persons["人物ID"], persons["标准名"]))
name2pid = dict(zip(persons["标准名"], persons["人物ID"]))
gender = dict(zip(persons["人物ID"], persons["性别"]))
# 合并实体映射
for src, dst in MERGE.items():
    rels.loc[rels["主体"] == src, "主体"] = dst
    rels.loc[rels["客体"] == src, "客体"] = dst
for i, r in rels.iterrows():
    rels.at[i, "主体ID"] = name2pid.get(r["主体"])
    rels.at[i, "客体ID"] = name2pid.get(r["客体"])

rels["原始关系"] = rels["关系"]
rels["关系"] = rels["关系"].map(lambda x: PRED.get(x, (x, None))[0])
rels["关系大类"] = [PRED.get(o, (n, b))[1] or b for o, n, b in
                    zip(rels["原始关系"], rels["关系"], rels["关系大类"])]
rels = rels.drop_duplicates(["主体ID", "关系", "客体ID"]).reset_index(drop=True)

# ---- 纠错
FIX = [
    # (主体, 原关系, 客体) -> 新 (主体, 关系, 客体)
    (("贾珍", "父亲", "贾惜春"), ("贾敬", "父亲", "贾惜春")),
    (("贾惜春", "女儿", "贾珍"), ("贾惜春", "女儿", "贾敬")),
    (("尤氏", "母亲", "贾惜春"), ("尤氏", "嫂子", "贾惜春")),
    (("贾惜春", "女儿", "尤氏"), ("贾惜春", "小姑子", "尤氏")),
    (("贾迎春", "妻", "孙绍祖"), ("贾迎春", "丈夫", "孙绍祖")),
    (("邢岫烟", "妻", "薛蝌"), ("邢岫烟", "丈夫", "薛蝌")),
    (("史湘云", "孙女", "贾母"), ("史湘云", "侄孙女", "贾母")),
]
for (h, p, t), (h2, p2, t2) in FIX:
    m = (rels["主体"] == h) & (rels["关系"] == p) & (rels["客体"] == t)
    if m.sum() == 1:
        rels.loc[m, ["主体", "关系", "客体"]] = [h2, p2, t2]
        rels.loc[m, "主体ID"] = name2pid[h2]
        rels.loc[m, "客体ID"] = name2pid[t2]
        rels.loc[m, "原始关系"] = p
        rels.loc[m, "关系大类"] = PRED.get(p2, (p2, "亲属关系"))[1]
        rels.loc[m, "校注"] = "关系纠错"
    else:
        print("!! 纠错未命中", h, p, t, m.sum())

rels["校注"] = rels.get("校注", "")
rels["校注"] = rels["校注"].fillna("")

# ---- 补边（据 120 回本可证）
ADD_EDGES = [
    # 大丫鬟—主子（原表漏标，导致平儿/司棋/待书/抱琴等成为孤岛）
    ("平儿", "丫鬟", "王熙凤", "主仆关系"),
    ("平儿", "妾", "贾琏", "亲属关系"),
    ("紫鹃", "丫鬟", "林黛玉", "主仆关系"),
    ("司棋", "丫鬟", "贾迎春", "主仆关系"),
    ("侍画", "丫鬟", "贾探春", "主仆关系"),
    ("抱琴", "丫鬟", "贾元春", "主仆关系"),
    ("丰儿", "丫鬟", "王熙凤", "主仆关系"),
    ("彩明", "丫鬟", "王熙凤", "主仆关系"),
    ("莺儿", "丫鬟", "薛宝钗", "主仆关系"),
    ("李贵", "小厮", "贾宝玉", "主仆关系"),
    ("周瑞", "陪房", "王夫人", "主仆关系"),
    ("王善保", "陪房", "邢夫人", "主仆关系"),
    ("赖大", "管家", "贾政", "主仆关系"),
    # 兄妹 / 祖孙（荣宁两府第三代结构，原表缺失）
    ("贾宝玉", "哥哥", "贾探春", "亲属关系"),
    ("贾宝玉", "哥哥", "贾惜春", "亲属关系"),
    ("贾迎春", "姐姐", "贾宝玉", "亲属关系"),
    ("贾探春", "姐姐", "贾环", "亲属关系"),
    ("贾琏", "哥哥", "贾迎春", "亲属关系"),
    ("薛蟠", "哥哥", "薛宝钗", "亲属关系"),
    ("贾母", "祖母", "贾迎春", "亲属关系"),
    ("贾母", "祖母", "贾探春", "亲属关系"),
    ("周姨娘", "妾", "贾政", "亲属关系"),
    ("文官", "朋友", "芳官", "社会关系"),
    ("文官", "朋友", "龄官", "社会关系"),
]
for h, p, t, b in ADD_EDGES:
    if h not in name2pid or t not in name2pid:
        print("!! 补边人物不存在", h, t)
        continue
    m = (rels["主体ID"] == name2pid[h]) & (rels["关系"] == p) & (rels["客体ID"] == name2pid[t])
    if m.sum():
        continue
    rels.loc[len(rels)] = dict(关系ID=None, 主体=h, 主体ID=name2pid[h], 关系=p, 关系大类=b,
                               客体=t, 客体ID=name2pid[t], 主体府邸=None, 客体府邸=None,
                               互逆关系=None, 已配对=None, 原始关系=p, 校注="补边",
                               来源="补充（据120回本）")

if "来源" not in rels.columns:
    rels["来源"] = "原表"
rels["来源"] = rels["来源"].fillna("原表")
rels.loc[rels["校注"] == "补边", "来源"] = "补充（据120回本）"
rels.loc[rels["校注"] == "关系纠错", "来源"] = "原表（已纠错）"
print("补边实际写入：", (rels["来源"] == "补充（据120回本）").sum())

# ---- 互逆边
def inverse_of(pred, hg, tg):
    """给定 head 的性别 hg、tail 的性别 tg，返回 (逆谓词, 逆边语义方向是否成立)。"""
    if pred in ("父亲", "母亲"):
        return ("儿子" if tg == "男" else "女儿")
    if pred in ("儿子", "女儿"):
        return ("父亲" if tg == "男" else "母亲")
    if pred == "妻":
        return "丈夫"
    if pred == "丈夫":
        return "妻"
    if pred == "配偶":
        return "配偶"
    if pred == "妾":
        return "纳妾"
    if pred == "纳妾":
        return "妾"
    if pred in ("兄弟", "姐妹", "兄妹", "表兄妹", "朋友", "私情"):
        return pred
    if pred == "哥哥":
        return "弟弟" if hg == "男" else "妹妹"
    if pred == "弟弟":
        return "哥哥" if hg == "男" else "姐姐"
    if pred == "姐姐":
        return "弟弟" if hg == "男" else "妹妹"
    if pred == "妹妹":
        return "哥哥" if hg == "男" else "姐姐"
    if pred == "婆婆":
        return "儿媳"
    if pred == "儿媳":
        return "婆婆"
    if pred == "孙子":
        return "祖父" if tg == "男" else "祖母"
    if pred in ("祖父", "祖母"):
        return "孙子" if hg == "男" else "孙女"
    if pred == "孙女":
        return "祖父" if tg == "男" else "祖母"
    if pred == "外祖母":
        return "外孙" if tg == "男" else "外孙女"
    if pred == "外孙女":
        return "外祖父" if tg == "男" else "外祖母"
    if pred in ("侄女", "侄儿", "侄孙女"):
        return "姑母" if tg == "女" else "伯父"
    if pred in ("伯父", "姑母"):
        return "侄儿" if hg == "男" else "侄女"
    if pred == "岳父" or pred == "岳母":
        return "女婿"
    if pred == "女婿":
        return "岳父" if tg == "男" else "岳母"
    if pred == "养父":
        return "养子" if tg == "男" else "养女"
    if pred in ("养子", "养女"):
        return "养父" if tg == "男" else "养母"
    if pred in ("丫鬟", "小厮", "乳母", "陪房", "买办", "老仆", "管家"):
        return "主人"
    if pred == "主人":
        return "仆役"
    if pred == "嫂子":
        return "小姑子" if hg == "女" else "小叔子"
    if pred in ("小姑子", "小叔子"):
        return "嫂子"
    if pred == "师生":
        return "学生"
    if pred == "学生":
        return "老师"
    return None

have = set(zip(rels["主体ID"], rels["关系"], rels["客体ID"]))
new_rows = []
for _, r in rels.iterrows():
    inv = inverse_of(r["关系"], gender.get(r["客体ID"]), gender.get(r["主体ID"]))
    if not inv:
        continue
    key = (r["客体ID"], inv, r["主体ID"])
    if key in have:
        continue
    new_rows.append(dict(关系ID=None, 主体=r["客体"], 主体ID=r["客体ID"], 关系=inv,
                         关系大类=PRED.get(inv, (inv, r["关系大类"]))[1],
                         客体=r["主体"], 客体ID=r["主体ID"], 主体府邸=None, 客体府邸=None,
                         互逆关系=r["关系"], 已配对="是", 原始关系=inv, 校注="",
                         来源="派生（自动补逆）"))
    have.add(key)
if new_rows:
    rels = pd.concat([rels, pd.DataFrame(new_rows)], ignore_index=True)

# 回填互逆/配对
tri = {(r["主体ID"], r["关系"], r["客体ID"]) for _, r in rels.iterrows()}
pairs = []
for _, r in rels.iterrows():
    inv = inverse_of(r["关系"], gender.get(r["客体ID"]), gender.get(r["主体ID"]))
    ok = bool(inv) and (r["客体ID"], inv, r["主体ID"]) in tri
    pairs.append((inv if ok else "", "是" if ok else "否"))
rels["互逆关系"] = [p[0] for p in pairs]
rels["已配对"] = [p[1] for p in pairs]

# 编号
rels = rels.drop(columns=["互逆关系_y"], errors="ignore")
rels = rels.reset_index(drop=True)
rels["关系ID"] = ["HLM-R%03d" % (i + 1) for i in range(len(rels))]
rels["主体府邸"] = rels["主体ID"].map(dict(zip(persons["人物ID"], persons["居所"])))
rels["客体府邸"] = rels["客体ID"].map(dict(zip(persons["人物ID"], persons["居所"])))

# ---------------------------------------------------------------- 3 结局
FATES = [
    ("林黛玉", "泪尽而逝", 98, "死亡"), ("贾宝玉", "出家", 120, "出家"),
    ("薛宝钗", "守寡", 120, "守寡"), ("王熙凤", "病亡", 114, "死亡"),
    ("贾母", "寿终", 110, "死亡"), ("贾政", "袭爵复职", 120, "仕宦"),
    ("贾赦", "流放遇赦", 119, "流放"), ("贾珍", "流放遇赦", 119, "流放"),
    ("贾琏", "守业", 120, "存续"), ("秦可卿", "病亡（天香楼）", 13, "死亡"),
    ("贾元春", "薨逝", 95, "死亡"), ("贾迎春", "遭虐而亡", 109, "死亡"),
    ("贾探春", "远嫁", 102, "远嫁"), ("贾惜春", "出家", 118, "出家"),
    ("史湘云", "夫死守寡", 118, "守寡"), ("李纨", "凤冠霞帔后病亡", 119, "死亡"),
    ("妙玉", "被劫", 112, "失踪"), ("晴雯", "病亡", 77, "死亡"),
    ("袭人", "嫁蒋玉菡", 120, "婚配"), ("鸳鸯", "殉主自尽", 111, "死亡"),
    ("香菱", "难产而亡", 120, "死亡"), ("平儿", "扶正", 119, "婚配"),
    ("尤二姐", "吞金自逝", 69, "死亡"), ("尤三姐", "自刎", 66, "死亡"),
    ("贾环", "随母度日", 120, "存续"), ("巧姐", "嫁周家", 119, "婚配"),
    ("薛蟠", "获罪复赎", 120, "存续"), ("紫鹃", "随惜春出家", 118, "出家"),
    ("司棋", "撞墙自尽", 92, "死亡"), ("金钏儿", "投井", 32, "死亡"),
    ("贾瑞", "病亡", 12, "死亡"), ("秦钟", "病亡", 16, "死亡"),
    ("赵姨娘", "暴病", 113, "死亡"), ("贾雨村", "遇赦为民", 120, "仕宦"),
    ("甄士隐", "出家", 120, "出家"), ("刘姥姥", "救巧姐", 119, "存续"),
    ("贾兰", "中举", 119, "仕宦"), ("蒋玉菡", "娶袭人", 120, "婚配"),
    ("贾蓉", "捐官", 120, "存续"), ("薛姨妈", "守业", 120, "存续"),
    ("邢夫人", "存续", 120, "存续"), ("尤氏", "存续", 120, "存续"),
    ("贾蔷", "不知所终", None, "不详"), ("贾芸", "存续", 120, "存续"),
]
fates = pd.DataFrame(FATES, columns=["标准名", "结局", "结局回目", "结局类别"])
fates = fates[fates["标准名"].isin(persons["标准名"])]
fates["人物ID"] = fates["标准名"].map(name2pid)

# ---------------------------------------------------------------- 4 落盘
KEEP = ["人物ID", "标准名", "别名", "性别", "血缘家族", "居所", "身份类别", "身份细分",
        "原关系数", "图像状态", "图像文件", "合并至", "校注", "在关系网"]
for c in KEEP:
    if c not in persons:
        persons[c] = None
out = persons[KEEP].copy()
out.to_csv(PROC / "persons.csv", index=False, encoding="utf-8-sig")
rels.to_csv(PROC / "relations.csv", index=False, encoding="utf-8-sig")
fates.to_csv(PROC / "fates.csv", index=False, encoding="utf-8-sig")

pd.DataFrame(log, columns=["操作", "人物", "原值", "新值"]).to_csv(
    CUR / "person_curation.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------- 5 摘要
print("人物 %d（合并后 %d），关系 %d，结局 %d" % (
    len(persons), (out["合并至"] == "").sum(), len(rels), len(fates)))
print("补性别 %d，补身份 %d，补家族 %d" % (
    sum(1 for x in log if x[0] == "补性别"), sum(1 for x in log if x[0] == "补身份"),
    sum(1 for x in log if x[0] == "补血缘家族")))
print("关系大类：", rels["关系大类"].value_counts().to_dict())
print("已配对：", rels["已配对"].value_counts().to_dict(), " 来源：", rels["来源"].value_counts().to_dict())
print("身份类别：", out["身份类别"].value_counts().to_dict())
print("性别：", out["性别"].value_counts().to_dict())
print("仍有空值：", out[["性别", "身份类别"]].isna().sum().to_dict())
