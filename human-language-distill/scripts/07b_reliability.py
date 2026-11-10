#!/usr/bin/env python3
"""Split-half reliability: compute features on the first and second half of each
document, correlate the two across documents, then Spearman-Brown correct."""
from __future__ import annotations
import argparse, glob, gzip, json, os, sys
from multiprocessing import Pool
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, features


def init_worker():
    import jieba
    jieba.initialize()


def halves(item):
    text, genre = item
    n = len(text)
    if n < 500:
        return None
    mid = n // 2
    a, b = text[:mid], text[mid:]
    try:
        return genre, features.compute(a), features.compute(b)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="+", default=[])
    ap.add_argument("--per-genre", type=int, default=2000)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile", "reliability.json"))
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    paths = args.input or sorted(glob.glob(os.path.join(common.WORK, "**", "*sample*.jsonl.gz"), recursive=True))
    paths = [p for p in paths if os.path.exists(p)]
    picked = {}
    for p in paths:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                g = r.get("genre")
                if g and len(picked.setdefault(g, [])) < args.per_genre:
                    picked[g].append(r["text"])
    items = [(t, g) for g, ts in picked.items() for t in ts]
    print({g: len(ts) for g, ts in picked.items()}, "total", len(items))
    with Pool(args.workers, initializer=init_worker) as pool:
        rows = [x for x in pool.map(halves, items, chunksize=50) if x]

    out = {}
    for g in sorted(picked):
        gr = [(a, b) for gg, a, b in rows if gg == g]
        if len(gr) < 100:
            continue
        names = sorted({k for a, b in gr for k in a if k in b})
        fout = {}
        for k in names:
            x = np.array([a.get(k, np.nan) for a, b in gr], dtype=float)
            y = np.array([b.get(k, np.nan) for a, b in gr], dtype=float)
            m = ~(np.isnan(x) | np.isnan(y))
            if m.sum() < 100 or x[m].std() == 0 or y[m].std() == 0:
                continue
            r = float(np.corrcoef(x[m], y[m])[0, 1])
            fout[k] = {"r": r, "spearman_brown": 2 * r / (1 + r) if r > -1 else None, "n": int(m.sum())}
        out[g] = fout
        good = sum(1 for v in fout.values() if v["spearman_brown"] and v["spearman_brown"] >= 0.85)
        print(g, f"{good}/{len(fout)} features >=0.85")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
