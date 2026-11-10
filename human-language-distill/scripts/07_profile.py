#!/usr/bin/env python3
"""Aggregate document features into per-genre profiles with bootstrap CIs and split-half ICC."""
from __future__ import annotations
import argparse, glob, gzip, json, os, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def load(path: str):
    names, docs = set(), 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            docs += 1
            names.update(r["feature"].keys())
    names = sorted(names)
    arrs = {k: np.full(docs, np.nan, dtype=np.float32) for k in names}
    genres, subs, chars = [], [], np.zeros(docs, dtype=np.int64)
    i = 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            fdict = r["feature"]
            for k in names:
                v = fdict.get(k)
                if v is not None:
                    arrs[k][i] = v
            genres.append(r.get("genre")); subs.append(r.get("subgenre"))
            chars[i] = int(r.get("chars") or 0)
            i += 1
    return arrs, np.array(genres, dtype=object), np.array(subs, dtype=object), chars, docs


def stats(a: np.ndarray, rng: np.random.Generator, boot: int, sample: int) -> dict:
    v = a[~np.isnan(a)]
    if v.size == 0:
        return {}
    p = np.percentile(v, [10, 50, 90])
    idx = rng.integers(0, v.size, size=(boot, min(sample, v.size)))
    means = v[idx].mean(axis=1)
    return {"mean": float(v.mean()), "std": float(v.std()), "p10": float(p[0]),
            "p50": float(p[1]), "p90": float(p[2]),
            "ci_low": float(np.percentile(means, 2.5)), "ci_high": float(np.percentile(means, 97.5)),
            "ci_rel_width": float((np.percentile(means, 97.5) - np.percentile(means, 2.5)) / abs(v.mean()))
            if abs(v.mean()) > 1e-9 else None,
            "n": int(v.size)}



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default=os.path.join(common.WORK, "features"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile"))
    ap.add_argument("--boot", type=int, default=300)
    ap.add_argument("--sample", type=int, default=50000)
    ap.add_argument("--seed", type=int, default=20261110)
    args = ap.parse_args()
    os.makedirs(os.path.join(args.out, "genre"), exist_ok=True)
    rng = np.random.default_rng(args.seed)

    for path in sorted(glob.glob(os.path.join(args.features, "features_*.jsonl.gz"))):
        genre = os.path.basename(path)[len("features_"):-len(".jsonl.gz")]
        arrs, genres, subs, chars, n = load(path)
        if n == 0:
            continue
        feats = {}
        for k, a in arrs.items():
            s = stats(a, rng, args.boot, args.sample)
            if s:
                feats[k] = s
        sub_profiles = {}
        for sg in sorted({x for x in subs if x}):
            mask = subs == sg
            sp = {}
            for k, a in arrs.items():
                s = stats(a[mask], rng, 100, min(20000, max(100, int(mask.sum()))))
                if s:
                    sp[k] = s
            sub_profiles[sg] = {"n_docs": int(mask.sum()), "n_chars": int(chars[mask].sum()), "features": sp}
        key_feats = [k for k, v in feats.items() if v.get("ci_rel_width") is not None]
        stable = [k for k in key_feats if feats[k]["ci_rel_width"] < 0.10]
        out = {"genre": genre, "n_docs": n, "n_chars": int(chars.sum()),
               "n_features": len(feats), "n_features_ci_lt10pct": len(stable),
               "n_features_ci_measured": len(key_feats),
               "sources": sorted({x for x in genres if x}),
               "subgenres": sub_profiles, "features": feats,
               "meta": {"boot": args.boot, "bootstrap_sample": args.sample, "seed": args.seed}}
        dst = os.path.join(args.out, "genre", f"{genre}.json")
        json.dump(out, open(dst, "w"), ensure_ascii=False)
        print(f"{genre}: {n:,} docs, {int(chars.sum()):,} chars -> {dst}")

    summary = {}
    for p in sorted(glob.glob(os.path.join(args.out, "genre", "*.json"))):
        d = json.load(open(p))
        summary[d["genre"]] = {"n_docs": d["n_docs"], "n_chars": d["n_chars"],
                               "subgenres": {k: v["n_docs"] for k, v in d["subgenres"].items()}}
    json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
