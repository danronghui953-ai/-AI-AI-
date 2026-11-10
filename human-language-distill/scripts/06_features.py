#!/usr/bin/env python3
"""Extract document features from sampled JSONL.gz files with multiprocessing."""
from __future__ import annotations
import argparse, glob, gzip, hashlib, json, os, sys, time, zlib
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, features


def init_worker():
    import jieba
    jieba.initialize()


def work(item):
    rec, do_pos = item
    try:
        f = features.compute(rec["text"], do_pos=do_pos)
    except Exception as e:
        return {"id": rec.get("id"), "error": str(e)}
    out = {"id": rec.get("id"), "source": rec.get("source"), "subgenre": rec.get("subgenre"),
           "genre": rec.get("genre"), "chars": rec.get("chars"), "feature": f}
    return out


def read_records(paths: list[str]):
    for p in paths:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except Exception:
                    continue


BUNDLE = {("im", "im"), ("opinion", "comment"), ("opinion", "review")}
BUNDLE_CHARS = 800
BUNDLE_MAX = 30


def bundle_records(records):
    """Short texts are grouped into ~800-char pseudo-documents so rhythm and
    lexical features are not dominated by tiny samples."""
    buf, size, key = [], 0, None

    def flush():
        nonlocal buf, size, key
        if not buf:
            return None
        text = "\n\n".join(r["text"] for r in buf)
        h = hashlib.blake2b("".join(str(r.get("id")) for r in buf).encode(), digest_size=8).hexdigest()
        rec = {"id": "b_" + h, "source": "bundled", "subgenre": key[1], "genre": key[0],
               "chars": len(text), "text": text, "bundled": len(buf)}
        buf, size = [], 0
        return rec

    for r in records:
        k = (r.get("genre"), r.get("subgenre"))
        if k not in BUNDLE:
            out = flush()
            if out:
                yield out
                key = None
            yield r
            continue
        if key is not None and k != key:
            out = flush()
            if out:
                yield out
        key = k
        buf.append(r)
        size += int(r.get("chars") or len(r.get("text", "")))
        if size >= BUNDLE_CHARS or len(buf) >= BUNDLE_MAX:
            out = flush()
            if out:
                yield out
    out = flush()
    if out:
        yield out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="+", default=[])
    ap.add_argument("--outdir", default=os.path.join(common.WORK, "features"))
    ap.add_argument("--pos-chars", type=int, default=50_000_000)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    paths = args.input or [
        os.path.join(common.WORK, "lccc_sample.jsonl.gz"),
        os.path.join(common.WORK, "codedoc_sample.jsonl.gz"),
        os.path.join(common.WORK, "literary_sample.jsonl.gz"),
        os.path.join(common.WORK, "thucnews_sample.jsonl.gz"),
        os.path.join(common.WORK, "classical_sample.jsonl.gz"),
    ] + sorted(glob.glob(os.path.join(common.WORK, "clue", "sample_*.jsonl.gz")))
    paths = [p for p in paths if os.path.exists(p)]
    print("inputs:", *paths, sep="\n  ")
    os.makedirs(args.outdir, exist_ok=True)

    total = 0
    for r in bundle_records(read_records(paths)):
        total += int(r.get("chars") or len(r.get("text", "")))
        if args.limit and total >= args.limit:
            break
    pos_prob = min(1.0, args.pos_chars / max(1, total))
    print(f"total_chars={total:,} pos_prob={pos_prob:.3f}")

    outs: dict[str, gzip.GzipFile] = {}
    n = err = 0
    t0 = time.time()
    jobs = []
    for r in bundle_records(read_records(paths)):
        if args.limit and n >= args.limit:
            break
        h = (zlib.crc32(str(r.get("id")).encode()) & 0xFFFFFFFF) / 4294967296.0
        jobs.append((r, h < pos_prob))
        n += 1
    print(f"queued {n:,} docs")

    done = 0
    with Pool(args.workers, initializer=init_worker) as pool:
        for out in pool.imap_unordered(work, jobs, chunksize=100):
            done += 1
            if "error" in out:
                err += 1
                continue
            g = out.get("genre") or "unknown"
            if g not in outs:
                outs[g] = gzip.open(os.path.join(args.outdir, f"features_{g}.jsonl.gz"), "wt", encoding="utf-8")
            outs[g].write(json.dumps(out, ensure_ascii=False) + "\n")
            if done % 10000 == 0:
                print(f"[features] {done:,}/{n:,} docs, {time.time()-t0:.0f}s, errors={err}", flush=True)
    for fh in outs.values():
        fh.close()
    meta = {"docs_in": n, "errors": err, "total_chars": total, "pos_prob": pos_prob,
            "seconds": round(time.time() - t0, 1), "files": paths}
    json.dump(meta, open(os.path.join(args.outdir, "meta.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
