"""Shared constants, cleaning and genre rules for the human-language distillation."""
from __future__ import annotations
import os, re, unicodedata

PROJECT = os.path.expanduser("~/Documents/human-language-distill")
RAW = os.path.join(PROJECT, "raw")
WORK = os.path.join(PROJECT, "work")
LOGS = os.path.join(PROJECT, "logs")

# ---- sampling quotas (characters) ----
QUOTA = {
    "news": 130_000_000,
    "wiki": 50_000_000,
    "longpost": 40_000_000,
    "qa": 70_000_000,
    "review": 30_000_000,
    "comment": 30_000_000,
    "marketing": 0,
    "other": 0,
}
QUOTA_LCCC = 80_000_000
QUOTA_CODEDOC = 30_000_000
QUOTA_LITERARY = 10_000_000

SUBGENRE_TO_GENRE = {
    "news": "longform", "wiki": "longform", "longpost": "longform",
    "qa": "opinion", "review": "opinion", "comment": "opinion",
    "marketing": "excluded", "other": "excluded",
}

# ---- rules ----
NEWS = re.compile(r"(本报讯|本报记者|新华社|中新网|中新社|人民网|环球网|光明网|经济日报|"
                  r"记者[：:\s]?[一-龥]{2,4}|来源[：:]|原标题|通讯员)")
WIKI = re.compile(r"(学名[：:]|拉丁学名|参考文献|外部链接|又名|俗称|是一[种位个名]|"
                  r"是.{0,15}的(植物|动物|人物|城市|国家|电影|书籍|游戏|组织|公司|朝代|歌手|演员))")
QA = re.compile(r"(如何|为什么|怎么|怎样|有哪些|是什么|请问|求助|请教|想问|有没有|能不能|该不该|是不是)")
REVIEW = re.compile(r"(好吃|不错|推荐|满意|失望|快递|包装|质量|服务|味道|价格|性价比|买了|用了|收到|好评|差评|口感|效果|打分|星)")
MARK = re.compile(r"(扫码|报名|客服|微信|优惠|包邮|下单|特价|折扣|促销|门店|订购|咨询电话)")
FP = re.compile(r"(我|我们|自己|觉得|感觉|认为)")
PART = re.compile(r"(啊|吧|呢|嘛|呀|哦|哈|唉|哎)")
PRICE = re.compile(r"([0-9]+元|[¥￥]|折|优惠|包邮|http)")
QUESTION = re.compile(r"[？?]")

# boilerplate stripped from document edges
BOILER = [
    re.compile(r"^原标题[：:].*?\n?"),
    re.compile(r"责任编辑[：:].*$"),
    re.compile(r"^来源[：:].*$", re.M),
    re.compile(r"（?点击(查看|进入).*?）?$"),
    re.compile(r"^免责声明.*$", re.M),
]
URL = re.compile(r"https?://\S+|www\.\S+")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
IDCARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ATUSER = re.compile(r"@[\w一-龥-]{1,30}")
MULTI_PUNCT = re.compile(r"([。！？!?，,、；;：:])\1{2,}")
ZERO = re.compile(r"[​-‏  ﻿]")

def clean(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = ZERO.sub("", t).replace("\r", "\n")
    t = t.replace("　", " ")
    t = URL.sub(" <URL> ", t)
    t = EMAIL.sub(" <EMAIL> ", t)
    t = PHONE.sub(" <PHONE> ", t)
    t = IDCARD.sub(" <ID> ", t)
    t = ATUSER.sub(" <AT> ", t)
    for b in BOILER:
        t = b.sub("", t)
    t = MULTI_PUNCT.sub(r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    nonspace = sum(1 for ch in text if not ch.isspace())
    return cjk / max(1, nonspace)

def shape_ok(text: str) -> bool:
    """Reject low-information lines before classification."""
    n = len(text)
    if n < 5 or n > 20000:
        return False
    if cjk_ratio(text) < 0.45:
        return False
    # repeated single char (spam)
    if len(set(text[:200])) <= 5:
        return False
    return True

def classify_clue(t: str) -> str:
    L = len(t)
    mk = len(MARK.findall(t))
    # strong advertorial
    if mk >= 2 and PRICE.search(t):
        return "marketing"
    if NEWS.search(t) and L >= 100 and not QUESTION.search(t[:40]):
        return "news"
    if WIKI.search(t) and L >= 150 and not QUESTION.search(t) and not FP.search(t[:120]):
        return "wiki"
    if QA.search(t) and QUESTION.search(t) and L >= 30:
        return "qa"
    if L <= 300 and (len(REVIEW.findall(t)) >= 2 or re.search(r"[1-5]分|五星|好评|差评", t)):
        return "review"
    if L <= 150 and (FP.search(t) or PART.search(t)):
        return "comment"
    if L >= 800:
        return "longpost"
    return "other"

def length_ok(t: str, sub: str) -> bool:
    L = len(t)
    if sub in ("comment",):
        return 10 <= L <= 300
    if sub in ("review",):
        return 10 <= L <= 400
    if sub in ("qa",):
        return 30 <= L <= 5000
    if sub in ("news",):
        return 100 <= L <= 8000
    if sub in ("wiki",):
        return 150 <= L <= 8000
    if sub in ("longpost",):
        return 800 <= L <= 20000
    return 10 <= L <= 20000

SENT_SPLIT = re.compile(r"[。！？!?；;\n]+")
PARA_SPLIT = re.compile(r"\n\s*\n")

def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text) if len(s.strip()) >= 2]

def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in PARA_SPLIT.split(text) if p.strip()]
