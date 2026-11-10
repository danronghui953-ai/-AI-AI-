#!/usr/bin/env python3
"""Second-round analyses on top of the per-document features.

Produces six JSON files under profile/deep/:
  punctuation.json   标点密度（每千字）
  bundles.json       各体裁高频 2/3-gram 与区别性短语
  edges.json         开头句、结尾句的高频片段
  length_strata.json 按篇幅分层的特征均值
  distance.json      体裁间特征距离
  humanlikeness.json HC3 人机分类器给每个体裁打的分
"""
from __future__ import annotations
import argparse, glob, gzip, json, math, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

try:
    import jieba
except Exception:
    jieba = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "profile", "deep")

SAMPLE_GLOBS = [
    os.path.join(common.WORK, "lccc_sample.jsonl.gz"),
    os.path.join(common.WORK, "codedoc_sample.jsonl.gz"),
    os.path.join(common.WORK, "literary_sample.jsonl.gz"),
    os.path.join(common.WORK, "thucnews_sample.jsonl.gz"),
    os.path.join(common.WORK, "classical_sample.jsonl.gz"),
    os.path.join(common.WORK, "clue", "sample_*.jsonl.gz"),
]

PUNCT = {
    "comma": "，,", "period": "。.", "question": "？?", "exclaim": "！!",
    "semicolon": "；;", "colon": "：:", "enum": "、", "quote": "“”‘’\"'「」『』",
    "dash": "—–-", "ellipsis": "…", "paren": "（）()", "booktitle": "《》",
    "middot": "·", "slash": "/／", "newline": "\n",
}
CJK_PUNCT = set("".join(PUNCT.values()))
STRIP_CH = CJK_PUNCT | set(" \t　\r\n")


def is_word(t: str) -> bool:
    t = t.strip()
    if len(t) < 1 or "<" in t or ">" in t:
        return False
    if all(ch in STRIP_CH or ch.isdigit() for ch in t):
        return False
    return any(ch.isalpha() or "一" <= ch <= "鿿" for ch in t)


def iter_samples(cap_chars: int = 0, cap_docs: int = 0):
    """Stream sample records grouped by genre; stop per genre at caps."""
    per = defaultdict(int)
    per_docs = defaultdict(int)
    for pat in SAMPLE_GLOBS:
        for path in sorted(glob.glob(pat)):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    g = r.get("genre") or "unknown"
                    if cap_chars and per[g] >= cap_chars:
                        continue
                    if cap_docs and per_docs[g] >= cap_docs:
                        continue
                    t = r.get("text") or ""
                    if not t:
                        continue
                    per[g] += len(t)
                    per_docs[g] += 1
                    yield g, r.get("subgenre"), t


def punctuation(cap_chars=12_000_000):
    counts = defaultdict(lambda: defaultdict(int))
    total = defaultdict(int)
    for g, _, t in iter_samples(cap_chars=cap_chars):
        total[g] += len(t)
        for cat, chars in PUNCT.items():
            c = sum(t.count(ch) for ch in chars)
            if c:
                counts[g][cat] += c
        # "..." is an ellipsis, not three full stops; move the extra dots
        runs = re.findall(r"\.{2,}", t)
        counts[g]["ellipsis"] += len(runs)
        counts[g]["period"] -= sum(len(x) - 1 for x in runs)
        counts[g]["period"] = max(0, counts[g]["period"])
    out = {}
    for g in sorted(total):
        n = total[g]
        out[g] = {"chars": n, "per_1000": {k: round(v / n * 1000, 3)
                                           for k, v in sorted(counts[g].items())},
                  "punct_per_1000": round(sum(counts[g].values()) / n * 1000, 3)}
    return out


def ngrams(tokens, n):
    for i in range(len(tokens) - n + 1):
        yield "".join(tokens[i:i + n])


def bundles(cap_chars=3_000_000, min_count=5, top=30, distinctive_top=20):
    per = defaultdict(list)
    have = defaultdict(int)
    for g, _, t in iter_samples(cap_chars=cap_chars):
        if have[g] < cap_chars:
            per[g].append(t)
            have[g] += len(t)
    counters, toks = {}, {}
    for g, parts in per.items():
        text = "\n".join(parts)[:cap_chars]
        ts = [w for w in jieba.lcut(text) if is_word(w)]
        toks[g] = len(ts)
        c = Counter()
        for n in (2, 3):
            c.update(ngrams(ts, n))
        counters[g] = Counter({k: v for k, v in c.items() if v >= min_count})
        print(f"[bundles] {g}: {len(ts):,} tokens, {len(counters[g]):,} kept", flush=True)
    global_c = Counter()
    for c in counters.values():
        global_c.update(c)
    total_all = sum(toks.values())

    out = {}
    for g, c in counters.items():
        n = toks[g]
        top_list = [{"bundle": k, "count": v, "per10k": round(v / n * 10000, 2)}
                    for k, v in c.most_common(top)]
        dist = []
        for k, v in c.items():
            if v < 20:
                continue
            cg = v / n
            co = (global_c[k] - v) / max(1, total_all - n)
            if co <= 0:
                continue
            score = math.log2(cg / co)
            if score > 0.8:
                dist.append({"bundle": k, "count": v, "log2_lift": round(score, 2)})
        dist.sort(key=lambda d: -d["log2_lift"])
        out[g] = {"tokens": n, "top": top_list, "distinctive": dist[:distinctive_top]}
    return out


PLACEHOLDER = re.compile(r"<[A-Z]+>")


def split_first_last(t):
    t = PLACEHOLDER.sub("", t)
    first = re.split(r"[。！？!?\n]", t[:160], maxsplit=1)[0]
    tail = re.split(r"[。！？!?\n]", t[-160:])
    last = next((s for s in reversed(tail) if s.strip()), "")
    first = first.lstrip("，,。.；;、 \n")
    return first.strip()[:20], last.strip()[-20:]


def edge_ok(g: str) -> bool:
    # char n-grams over Latin text or punctuation are noise ("er", ",我")
    return all("一" <= ch <= "鿿" for ch in g)


def edges(cap_docs=25_000, top=20):
    first_c = defaultdict(Counter)
    last_c = defaultdict(Counter)
    docs = defaultdict(int)
    for g, _, t in iter_samples(cap_docs=cap_docs):
        if len(t) < 15:
            continue
        f, l = split_first_last(t)
        docs[g] += 1
        for n in (2, 3):
            fg = {x for x in ngrams(list(f), n) if edge_ok(x)}
            lg = {x for x in ngrams(list(l), n) if edge_ok(x)}
            first_c[g].update(fg)
            last_c[g].update(lg)
    out = {}
    for g in docs:
        d = docs[g]
        out[g] = {
            "docs": d,
            "first": [{"gram": k, "share": round(v / d, 4)} for k, v in first_c[g].most_common(top)],
            "last": [{"gram": k, "share": round(v / d, 4)} for k, v in last_c[g].most_common(top)],
        }
    return out


STRATA = [(0, 200), (200, 500), (500, 1000), (1000, 3000), (3000, 1 << 30)]
STRATA_NAMES = ["<200", "200-500", "500-1000", "1000-3000", "3000+"]
STRATA_FEATS = ["sent_mean", "sent_cv", "burstiness", "mtld", "digit_per100",
                "first_person_per100", "marker_per100", "question_ratio",
                "compression_ratio", "ngram_repeat", "adjacent_sim", "judgment_per100"]


def length_strata():
    out = {}
    for path in sorted(glob.glob(os.path.join(common.WORK, "features", "features_*.jsonl.gz"))):
        g = os.path.basename(path)[len("features_"):-len(".jsonl.gz")]
        acc = [[[] for _ in STRATA] for _ in STRATA_FEATS]
        ns = [0] * len(STRATA)
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                L = int(r.get("chars") or 0)
                bi = next((i for i, (lo, hi) in enumerate(STRATA) if lo <= L < hi), None)
                if bi is None:
                    continue
                ns[bi] += 1
                fd = r["feature"]
                for fi, k in enumerate(STRATA_FEATS):
                    v = fd.get(k)
                    if v is not None and isinstance(v, (int, float)):
                        acc[fi][bi].append(v)
        rows = {}
        for i, name in enumerate(STRATA_NAMES):
            if not ns[i]:
                continue
            rows[name] = {"n": ns[i]}
            for fi, k in enumerate(STRATA_FEATS):
                v = acc[fi][i]
                rows[name][k] = round(sum(v) / len(v), 4) if v else None
        out[g] = rows
    return out


def distance(cap=0):
    genres = {}
    feats = None
    for path in sorted(glob.glob(os.path.join(common.WORK, "features", "features_*.jsonl.gz"))):
        g = os.path.basename(path)[len("features_"):-len(".jsonl.gz")]
        acc = defaultdict(list)
        n = 0
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                fd = r["feature"]
                if feats is None:
                    feats = sorted(k for k in fd if k not in {"chars", "n_sents", "n_paras", "pos_sampled"})
                for k in feats:
                    v = fd.get(k)
                    if v is not None and isinstance(v, (int, float)):
                        acc[k].append(v)
                n += 1
                if cap and n >= cap:
                    break
        genres[g] = ({k: sum(v) / len(v) for k, v in acc.items() if len(v) >= max(1, 0.5 * n)},
                     n)
    keep = [k for k in feats if all(k in genres[g][0] for g in genres)]
    # z-score across genres so no single unit dominates
    z = {}
    for k in keep:
        vals = [genres[g][0][k] for g in genres]
        mu = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals)) or 1.0
        for g, v in zip(genres, vals):
            z.setdefault(g, {})[k] = (v - mu) / sd
    gl = sorted(genres)
    dist = {}
    for i, a in enumerate(gl):
        for b in gl[i + 1:]:
            eu = math.sqrt(sum((z[a][k] - z[b][k]) ** 2 for k in keep))
            dot = sum(z[a][k] * z[b][k] for k in keep)
            na = math.sqrt(sum(z[a][k] ** 2 for k in keep))
            nb = math.sqrt(sum(z[b][k] ** 2 for k in keep))
            dist[f"{a}|{b}"] = {"euclidean": round(eu, 3),
                                "cosine": round(dot / (na * nb), 3) if na and nb else None}
    return {"features": keep, "n_features": len(keep), "genres": {g: genres[g][1] for g in gl},
            "pairwise": dist}


def humanlikeness(per_genre=20_000):
    npz = os.path.join(ROOT, "profile", "hc3_features.npz")
    if not os.path.exists(npz) or jieba is None:
        return {"skipped": "hc3_features.npz missing; run 08_validate.py first"}
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    d = np.load(npz, allow_pickle=True)
    X, y, names = d["X"], d["y"], list(d["names"])
    # length-identifying features make the classifier key on text length:
    # bundled dialogue and READMEs both come out as "AI". Drop them and score
    # only on style features.
    DROP = {"chars", "n_sents", "n_paras", "para_mean", "para_cv",
            "para_sent_ratio", "newline_ratio", "sent_max"}
    keep_i = [i for i, k in enumerate(names) if k not in DROP]
    Xs = X[:, keep_i]
    scaler = StandardScaler().fit(Xs)
    clf = LogisticRegression(max_iter=3000).fit(scaler.transform(Xs), y)
    idx = {names[i]: j for j, i in enumerate(keep_i)}
    scores = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(common.WORK, "features", "features_*.jsonl.gz"))):
        g = os.path.basename(path)[len("features_"):-len(".jsonl.gz")]
        rows = []
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                rows.append(r["feature"])
                if len(rows) >= per_genre:
                    break
        arr = np.zeros((len(rows), len(keep_i)), dtype=np.float32)
        for i, fd in enumerate(rows):
            for k, j in idx.items():
                v = fd.get(k)
                if isinstance(v, (int, float)):
                    arr[i, j] = v
        p = clf.predict_proba(scaler.transform(arr))[:, 1]
        scores[g] = [float(x) for x in p]
    out = {}
    for g, p in scores.items():
        p = np.array(p)
        out[g] = {"n": int(p.size), "mean_ai_prob": round(float(p.mean()), 4),
                  "p10": round(float(np.percentile(p, 10)), 4),
                  "p50": round(float(np.percentile(p, 50)), 4),
                  "p90": round(float(np.percentile(p, 90)), 4),
                  "auc_reference": None}
    out["_note"] = ("分类器在 HC3 中文人类回答 vs GPT-3.5 回答上训练，"
                    "分数是「被判定为 AI 的概率」。已剔除 chars/n_sents 等长度特征，"
                    "否则分类器学的是长短而不是写法。只作相对参考，AI 侧是 2022 年模型。")
    out["_dropped_features"] = sorted(DROP & set(names))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", nargs="*", default=[])
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    jieba and jieba.initialize()

    jobs = [
        ("punctuation", lambda: punctuation(), 60_000_000),
        ("bundles", lambda: bundles(), 3_000_000),
        ("edges", lambda: edges(), 25_000),
        ("length_strata", length_strata, None),
        ("distance", lambda: distance(cap=30_000), None),
        ("humanlikeness", lambda: humanlikeness(), 20_000),
    ]
    for name, fn, _ in jobs:
        if name in args.skip:
            continue
        print(f"[deep] {name} ...", flush=True)
        res = fn()
        json.dump(res, open(os.path.join(OUT, f"{name}.json"), "w"),
                  ensure_ascii=False, indent=1)
        print(f"[deep] {name} done", flush=True)


if __name__ == "__main__":
    main()
