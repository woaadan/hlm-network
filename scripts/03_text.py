# -*- coding: utf-8 -*-
"""文本模态：切分 120 回、人物提及识别、章回共现矩阵。

输出
----
data/external/chapters/第001回.txt ...
data/processed/person_chapter.csv   人物 × 回 的提及次数（长表）
data/processed/text_stats.csv       出场回数、首末出场、提及总数
data/processed/cooccurrence.csv     同回共现对（weight=共现回数, jaccard）
data/processed/mention_audit.csv    每个检索词命中的次数（便于核查误匹配）
"""
import sys, io, re, json
from pathlib import Path
import pandas as pd
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_common import RAW, EXT, PROC
from curation_data import CURATION

TXT = EXT / "hlm_master.txt"
CH_DIR = EXT / "chapters"
CH_DIR.mkdir(parents=True, exist_ok=True)

text = TXT.read_text(encoding="utf-8").replace("\r", "")
lines = text.split("\n")

# ---------------------------------------------------------------- 切分
CN = "零〇一二三四五六七八九十百"
head_re = re.compile(r"^第([" + CN + r"]+)\s*回[\s\u3000]+(\S.*)$")
def cn2int(s):
    d = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
         "六": 6, "七": 7, "八": 8, "九": 9}
    if "百" in s:
        a, b = s.split("百")
        return (d.get(a, 1) if a else 1) * 100 + (cn2int(b) if b else 0)
    if "十" in s:
        a, b = s.split("十")
        return (d.get(a, 1) if a else 1) * 10 + (d.get(b, 0) if b else 0)
    v = 0
    for ch in s:
        v = v * 10 + d[ch]
    return v

heads = []
for i, l in enumerate(lines):
    m = head_re.match(l)
    if m and 1 <= cn2int(m.group(1)) <= 120:
        heads.append((i, cn2int(m.group(1)), m.group(1), m.group(2).strip()))
# 同一回可能出现两次标题（正文里再次出现），只取第一次
seen, seq = set(), []
for h in heads:
    if h[1] in seen:
        continue
    seen.add(h[1]); seq.append(h)
seq.sort(key=lambda x: x[0])
missing = sorted(set(range(1, 121)) - seen)
print("识别回目：", len(seq), "缺：", missing)
print("首", seq[0][2], "末", seq[-1][2])

chapters = []
for k, (i, num, cn, title) in enumerate(seq):
    end = seq[k + 1][0] if k + 1 < len(seq) else len(lines)
    body = "\n".join(lines[i + 1:end]).strip()
    body = re.sub(r"[\u3000\t]+", "", body)
    chapters.append(dict(num=num, cn=cn, title=title, text=body))
    (CH_DIR / ("第%03d回.txt" % num)).write_text("第%s回 %s\n\n%s" % (cn, title, body), encoding="utf-8")

print("总字数：", sum(len(c["text"]) for c in chapters))
json.dump([{k: c[k] for k in ("num", "cn", "title")} for c in chapters],
          open(EXT / "chapters.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- 检索词
persons = pd.read_csv(PROC / "persons.csv", encoding="utf-8-sig")
persons = persons[persons["合并至"].isna() | (persons["合并至"] == "")]
BAD_SUFFIX = {"夫人", "家的", "姨娘", "嬷嬷", "姥姥", "太太", "老爷", "姨妈", "姑娘", "氏"}
GENERIC = {"珍珠", "翡翠", "玻璃", "琥珀", "彩云", "彩霞", "秋纹", "碧痕", "香菱"}
SURNAME = set("贾王史薛林邢尤秦蒋柳甄")

token2pid, token_meta = {}, {}
for _, r in persons.iterrows():
    pid, name = r["人物ID"], r["标准名"]
    toks = {name}
    for a in str(r["别名"]).split("|") if isinstance(r["别名"], str) else []:
        if a:
            toks.add(a)
    c = CURATION.get(name, {})
    if c.get("match"):
        toks = {name} | set(c["match"].split("|"))
    elif name[0] in SURNAME and len(name) >= 3:
        short = name[1:]
        if short not in BAD_SUFFIX and len(short) >= 2:
            toks.add(short)
    for t in toks:
        if len(t) < 2:
            continue
        token2pid.setdefault(t, pid)
        token_meta.setdefault(t, []).append(pid)

# 冲突：同一检索词指向多个人（应极少）
conflict = {t: v for t, v in token_meta.items() if len(set(v)) > 1}
if conflict:
    print("!! 检索词冲突：", conflict)

tokens = sorted(token2pid, key=len, reverse=True)
pat = re.compile("|".join(map(re.escape, tokens)))
CTX = re.compile(r"丫头|丫鬟|丫环|姑娘|姐姐|妹妹|媳妇|婆子|小厮|奶奶|太太|老祖宗|"
                 r"道|说|笑|忙|回说|答应|进来|出去|等|两个|这个|那个")

def keep_generic(tok, s, a, b):
    if tok not in GENERIC:
        return True
    window = s[max(0, a - 5):b + 5]
    return bool(CTX.search(window))

mentions = defaultdict(int)
audit = defaultdict(int)
rows = []
for ch in chapters:
    s = ch["text"]
    cnt = defaultdict(int)
    for m in pat.finditer(s):
        tok = m.group(0)
        pid = token2pid[tok]
        if not keep_generic(tok, s, m.start(), m.end()):
            continue
        cnt[pid] += 1
        audit[(tok, pid)] += 1
    for pid, c in cnt.items():
        rows.append(dict(人物ID=pid, 回=ch["num"], 次数=c))
    mentions[ch["num"]] = cnt

pc = pd.DataFrame(rows)
pc.to_csv(PROC / "person_chapter.csv", index=False, encoding="utf-8-sig")

# 别名归并：把 token 计数并入人物
audit_df = pd.DataFrame([dict(检索词=t, 人物ID=p, 次数=c) for (t, p), c in audit.items()])
audit_df.to_csv(PROC / "mention_audit.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------- 统计
stat = []
for _, r in persons.iterrows():
    pid = r["人物ID"]
    sub = pc[pc["人物ID"] == pid]
    stat.append(dict(人物ID=pid, 标准名=r["标准名"], 提及总数=int(sub["次数"].sum()),
                     出场回数=len(sub), 首出场=int(sub["回"].min()) if len(sub) else None,
                     末出场=int(sub["回"].max()) if len(sub) else None))
st = pd.DataFrame(stat).sort_values("提及总数", ascending=False)
st.to_csv(PROC / "text_stats.csv", index=False, encoding="utf-8-sig")
print("文本覆盖：", (st["提及总数"] > 0).sum(), "/", len(st), "人至少出现一次")
print(st.head(15)[["标准名", "提及总数", "出场回数", "首出场"]].to_string(index=False))
print("零提及：", st[st["提及总数"] == 0]["标准名"].tolist())

# ---------------------------------------------------------------- 共现
pairs = defaultdict(int)
peri = {}
for ch in chapters:
    ids = sorted(mentions[ch["num"]])
    peri[ch["num"]] = ids
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            pairs[(ids[i], ids[j])] += 1

cnt = dict(zip(st["人物ID"], st["出场回数"]))
co = pd.DataFrame([dict(a=a, b=b, 共现回数=w,
                        jaccard=round(w / (cnt[a] + cnt[b] - w), 4) if cnt[a] + cnt[b] - w else 0)
                   for (a, b), w in pairs.items()])
co = co.sort_values("共现回数", ascending=False)
co.to_csv(PROC / "cooccurrence.csv", index=False, encoding="utf-8-sig")
print("共现对：", len(co), " 最大共现：", co.iloc[0].to_dict() if len(co) else None)
print("每回平均出场人数：%.1f" % (sum(len(v) for v in peri.values()) / len(peri)))
json.dump({str(k): v for k, v in peri.items()}, open(PROC / "chapter_cast.json", "w", encoding="utf-8"),
          ensure_ascii=False)


# ---------------------------------------------------------------- 同场共现（400 字窗口）
# 章回级共现每回 20+ 人，近乎完全图；改用 400 字滑动窗口近似“同场”，结构更接近阅读经验。
scenes = []
for ch in chapters:
    s = ch["text"]
    for i in range(0, len(s), 400):
        w = s[i:i + 400]
        if len(w) < 120:
            continue
        ids = set()
        for m in pat.finditer(w):
            tok = m.group(0)
            if keep_generic(tok, w, m.start(), m.end()):
                ids.add(token2pid[tok])
        if len(ids) > 1:
            scenes.append((ch["num"], sorted(ids)))

sp = defaultdict(int)
for _, ids in scenes:
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sp[(ids[i], ids[j])] += 1
scene_df = pd.DataFrame([dict(a=a, b=b, 同场次数=w) for (a, b), w in sp.items()])
scene_df = scene_df.sort_values("同场次数", ascending=False)
scene_df.to_csv(PROC / "cooccurrence_scene.csv", index=False, encoding="utf-8-sig")
print("同场窗口：", len(scenes), " 同场对：", len(scene_df),
      " 最大：", scene_df.iloc[0]["同场次数"] if len(scene_df) else 0)
