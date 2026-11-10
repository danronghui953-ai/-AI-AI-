#!/usr/bin/env python3
"""Known-groups validation: can profile features separate HC3 human vs ChatGPT answers?"""
from __future__ import annotations
import argparse, json, os, sys, time
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, features


def init_worker():
    import jieba
    jieba.initialize()


def work_text(text):
    try:
        return features.compute(text, do_pos=False)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hc3", default=os.path.join(common.RAW, "HC3-Chinese-all.jsonl"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile", "validation.json"))
    ap.add_argument("--max-per-side", type=int, default=2)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    items = []
    with open(args.hc3, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            for a in d.get("human_answers", [])[:args.max_per_side]:
                if a and len(a) >= 20:
                    items.append((common.clean(a), 0))
            for a in d.get("chatgpt_answers", [])[:args.max_per_side]:
                if a and len(a) >= 20:
                    items.append((common.clean(a), 1))
    print("texts", len(items), "human", sum(1 for _, y in items if y == 0), "ai", sum(1 for _, y in items if y == 1))
    t0 = time.time()
    with Pool(args.workers, initializer=init_worker) as pool:
        feats = pool.map(work_text, [t for t, _ in items], chunksize=200)
    y = [l for _, l in items]
    rows = [(f, label) for f, label in zip(feats, y) if f]
    print("feature rows", len(rows), f"{time.time()-t0:.0f}s")

    names = sorted({k for f, _ in rows for k in f})
    X = [[0.0 if f.get(k) is None else f.get(k) for k in names] for f, _ in rows]
    yy = [label for _, label in rows]

    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import roc_auc_score, accuracy_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X = np.array(X, dtype=np.float32)
    yy = np.array(yy)
    # keep the design matrix so downstream analyses can reuse the same
    # human-vs-GPT-3.5 classifier without recomputing 30k feature rows
    np.savez_compressed(os.path.join(os.path.dirname(args.out), "hc3_features.npz"),
                        X=X, y=yy, names=np.array(names, dtype=object))
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=20261110)
    results = {}
    for name, clf in [
        ("logreg", make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))),
        ("gbdt", GradientBoostingClassifier(random_state=20261110)),
    ]:
        prob = cross_val_predict(clf, X, yy, cv=cv, method="predict_proba")[:, 1]
        results[name] = {"auc": float(roc_auc_score(yy, prob)),
                         "accuracy": float(accuracy_score(yy, prob > 0.5))}
        print(name, results[name])

    # univariate direction: human mean vs ai mean for key features
    contrasts = {}
    for k in names:
        a = np.array([0.0 if f.get(k) is None else f.get(k) for f, lab in rows if lab == 0])
        b = np.array([0.0 if f.get(k) is None else f.get(k) for f, lab in rows if lab == 1])
        if a.std() + b.std() == 0:
            continue
        d = (a.mean() - b.mean()) / (np.sqrt((a.var() + b.var()) / 2) + 1e-9)
        contrasts[k] = {"human_mean": float(a.mean()), "ai_mean": float(b.mean()), "cohen_d": float(d)}
    top = sorted(contrasts.items(), key=lambda kv: -abs(kv[1]["cohen_d"]))[:15]
    out = {"n_texts": len(rows), "n_human": int((yy == 0).sum()), "n_ai": int((yy == 1).sum()),
           "models": results, "top_contrasts": dict(top),
           "note": "HC3 AI side is 2022 GPT-3.5; this is a known-groups sanity check, not a modern AI detector."}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "top_contrasts"}, ensure_ascii=False, indent=1))
    print("top contrasts:")
    for k, v in top:
        print(f"  {k:24s} d={v['cohen_d']:+.2f} human={v['human_mean']:.3f} ai={v['ai_mean']:.3f}")


if __name__ == "__main__":
    main()
