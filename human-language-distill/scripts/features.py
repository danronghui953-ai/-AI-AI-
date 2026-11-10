"""Document-level stylometric features. Pure Python + jieba, no GPU."""
from __future__ import annotations
import math, re, zlib
from collections import Counter

import jieba
import jieba.posseg as pseg

from common import sentences, paragraphs

# ---------------- lexicons ----------------
MARKERS = ["首先", "其次", "再次", "最后", "然而", "因此", "所以", "但是", "不过", "而且",
           "此外", "另外", "总之", "综上", "由此可见", "值得注意的是", "需要指出",
           "一方面", "另一方面", "与此同时", "换句话说", "也就是说", "总而言之"]
CONTRAST = ["但是", "但", "然而", "不过", "可是", "却", "反而"]
CAUSAL = ["因为", "所以", "因此", "由于", "于是", "导致", "从而"]
HEDGE = ["可能", "也许", "或许", "大概", "在一定程度上", "某种程度上", "相对来说",
         "似乎", "应该是", "恐怕", "大致", "基本上", "可能吧"]
JUDGE = ["我建议", "我认为", "我觉得", "应该", "必须", "不要", "别", "推荐", "最好", "值得", "不建议"]
DISCLAIM = ["仅供参考", "请咨询", "注意风险", "不构成", "谨慎", "风险自负", "具体效果因人而异"]
BOTHSIDES = ["各有优劣", "各有好坏", "取决于", "因人而异", "没有绝对", "见仁见智", "视情况而定", "各有利弊"]
TIME = ["今天", "昨天", "明天", "去年", "今年", "现在", "当时", "刚才", "后来", "以前",
        "以后", "早上", "晚上", "中午", "最近", "目前", "当时"]
FIRST = ["我", "我们", "咱", "咱们", "俺", "自己"]
PRONOUN = ["我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "自己", "大家", "别人"]
COND = re.compile(r"(如果|若|假如|一旦|当.{0,12}时|在.{0,12}情况下|需要结合|具体.{0,8}分析|"
                  r"因人而异|视情况而定|根据.{0,10}情况|看情况)")
CONCRETE = re.compile(r"(\d|高于|低于|超过|少于|大于|小于|达到|至少|至多|以上|以下|之前|之后|"
                      r"之前|之后|万|亿|%|％)")
OPEN_TPL = re.compile(r"^(随着|在当今|近年来|众所周知|首先|在这个|如今|当前)")
CLOSE_TPL = re.compile(r"(综上所述|总之|希望(这些|本文|以上)|感谢(阅读|观看)|欢迎(关注|留言|讨论)|"
                       r"以上(就是|是)|如果你(有|还有).{0,10}(问题|疑问))")
MD_HEAD = re.compile(r"^#{1,6}\s", re.M)
MD_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s", re.M)
MD_BOLD = re.compile(r"\*\*[^*]+\*\*")
PARALLEL = re.compile(r"[^，。！？；\n]{1,15}[，、][^，。！？；\n]{1,15}[，、][^，。！？；\n]{1,15}")

STOP = set("的了是在和与也就都而及着或一个我你他她它有这那不很还又更没会能要可以对从到为以于之其所被把让给向但并且因为所以如果虽然然后因此然而")


def _count_any(text: str, words: list[str]) -> int:
    return sum(text.count(w) for w in words)


def mtdl(tokens: list[str], threshold: float = 0.72) -> float | None:
    if len(tokens) < 50:
        return None
    def one(toks):
        factors, types, n = 0, set(), 0
        for t in toks:
            n += 1
            types.add(t)
            if len(types) / n <= threshold:
                factors += 1
                types, n = set(), 0
        if n:
            factors += (1 - len(types) / n) / (1 - threshold)
        return factors
    f, b = one(tokens), one(tokens[::-1])
    if f <= 0 or b <= 0:
        return None
    return (len(tokens) / f + len(tokens) / b) / 2


def _kurt(xs: list[float]) -> float | None:
    n = len(xs)
    if n < 4:
        return None
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / n
    if v <= 0:
        return None
    return sum((x - m) ** 4 for x in xs) / (n * v * v) - 3


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(round(q * (len(ys) - 1)))))
    return float(ys[i])


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set()


def compute(text: str, do_pos: bool = False) -> dict:
    text = text.strip()[:20000]
    L = len(text)
    sents = sentences(text)
    paras = paragraphs(text)
    slens = [len(s) for s in sents]
    plens = [len(p) for p in paras]
    n_s = max(1, len(sents))
    feats: dict[str, float] = {"chars": L, "n_sents": len(sents), "n_paras": len(paras)}

    # rhythm
    mean = sum(slens) / n_s if slens else 0
    std = math.sqrt(sum((x - mean) ** 2 for x in slens) / n_s) if slens else 0
    pmean = sum(plens) / max(1, len(plens))
    feats.update({
        "sent_mean": mean, "sent_std": std,
        "sent_cv": std / mean if mean and len(slens) >= 2 else None,
        "sent_kurt": _kurt(slens), "sent_p10": _pct(slens, .1), "sent_p90": _pct(slens, .9),
        "sent_max": max(slens) if slens else 0,
        "para_mean": pmean,
        "para_cv": (math.sqrt(sum((x - pmean) ** 2 for x in plens) / len(plens)) / pmean)
                   if len(plens) >= 2 and pmean else None,
        "burstiness": (std - mean) / (std + mean) if (std + mean) else None,
    })

    # lexical
    toks = [t for t in jieba.cut(text) if t.strip()]
    n_tok = max(1, len(toks))
    feats.update({
        "n_tokens": len(toks),
        "ttr": len(set(toks)) / n_tok,
        "mtld": mtdl(toks[:2000]),
        "nominalization": sum(1 for t in toks if len(t) >= 2 and t.endswith(("性", "化", "主义"))) / n_tok,
        "pronoun": sum(1 for t in toks if t in PRONOUN) / n_tok,
        "content_ratio": sum(1 for t in toks if t not in STOP and len(t) >= 2) / n_tok,
    })

    # concreteness
    feats.update({
        "digit_per100": sum(ch.isdigit() for ch in text) / max(1, L) * 100,
        "first_person_per100": _count_any(text, FIRST) / max(1, L) * 100,
        "time_per100": _count_any(text, TIME) / max(1, L) * 100,
        "number_token_ratio": sum(1 for t in toks if any(ch.isdigit() for ch in t)) / n_tok,
    })

    # discourse
    feats.update({
        "marker_per100": _count_any(text, MARKERS) / max(1, L) * 100,
        "contrast_per100": _count_any(text, CONTRAST) / max(1, L) * 100,
        "causal_per100": _count_any(text, CAUSAL) / max(1, L) * 100,
        "parallel_ratio": sum(1 for s in sents if PARALLEL.search(s)) / n_s,
        "bei_per100": text.count("被") / max(1, L) * 100,
        "ba_per100": text.count("把") / max(1, L) * 100,
    })

    # structure
    feats.update({
        "md_heading_per1000": len(MD_HEAD.findall(text)) / max(1, L) * 1000,
        "md_list_per1000": len(MD_LIST.findall(text)) / max(1, L) * 1000,
        "md_bold_per1000": len(MD_BOLD.findall(text)) / max(1, L) * 1000,
        "para_sent_ratio": len(paras) / n_s,
        "opening_template": 1.0 if OPEN_TPL.search(text[:60]) else 0.0,
        "closing_template": 1.0 if CLOSE_TPL.search(text[-80:]) else 0.0,
        "newline_ratio": text.count("\n") / max(1, L) * 100,
    })

    # stance
    n_q = min(n_s, len(re.findall(r"[？?]", text)))
    asserts = [s for s in sents if len(s) >= 8]
    empty_cond = 0
    for s in asserts:
        m = COND.search(s)
        if not m:
            continue
        clause = re.split(r"[，,。；;]", s[m.start():])[0]
        # a condition carries information if it names a number, a threshold,
        # a Latin term, or a quoted term; otherwise it is a generic disclaimer
        if not (CONCRETE.search(clause) or re.search(r"[A-Za-z]{2,}", clause) or "“" in clause or "\"" in clause):
            empty_cond += 1
    feats.update({
        "hedge_per100": _count_any(text, HEDGE) / max(1, L) * 100,
        "condition_per100": len(COND.findall(text)) / max(1, L) * 100,
        "empty_condition_ratio": empty_cond / max(1, len(asserts) - min(n_q, len(asserts))),
        "both_sides_per100": _count_any(text, BOTHSIDES) / max(1, L) * 100,
        "judgment_per100": _count_any(text, JUDGE) / max(1, L) * 100,
        "disclaimer_per100": _count_any(text, DISCLAIM) / max(1, L) * 100,
        "question_ratio": n_q / n_s,
    })

    # predictability
    clean = re.sub(r"\s+", "", text)
    tri = [clean[i:i + 3] for i in range(max(0, len(clean) - 2))]
    tc = Counter(tri)
    total_tri = max(1, len(tri))
    feats["ngram_repeat"] = sum(v - 1 for v in tc.values() if v > 1) / total_tri
    raw = text.encode("utf-8")
    feats["compression_ratio"] = len(zlib.compress(raw, 6)) / max(1, len(raw))
    sims = []
    for a, b in zip(sents, sents[1:61]):
        A, B = _bigrams(a), _bigrams(b)
        if A or B:
            sims.append(len(A & B) / max(1, len(A | B)))
    feats["adjacent_sim"] = sum(sims) / len(sims) if sims else 0.0

    # density
    trans_only = sum(1 for s in sents if len(s) <= 8 and any(s.startswith(m) for m in MARKERS))
    feats.update({
        "assertion_per100": max(0, len(asserts) - n_q) / max(1, L) * 100,
        "transition_only_ratio": trans_only / n_s,
        "unique_sent_ratio": len({s for s in sents}) / n_s,
        "distinct_token_ratio": len({t for t in toks if t not in STOP}) / n_tok,
    })

    # POS-based (optional, sampled)
    if do_pos:
        tags = [(w, f) for w, f in pseg.cut(text) if w.strip()]
        nt = max(1, len(tags))
        feats.update({
            "ne_per100": sum(1 for w, f in tags if f in ("nr", "ns", "nt", "nz")) / max(1, L) * 100,
            "idiom_ratio": sum(1 for w, f in tags if f == "i") / nt,
            "noun_ratio": sum(1 for w, f in tags if f.startswith("n")) / nt,
            "verb_ratio": sum(1 for w, f in tags if f.startswith("v")) / nt,
            "adj_ratio": sum(1 for w, f in tags if f.startswith("a")) / nt,
            "pos_sampled": 1.0,
        })
    else:
        feats["pos_sampled"] = 0.0
    return feats
