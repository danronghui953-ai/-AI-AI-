#!/usr/bin/env python3
"""Scan CLUECorpusSmall (one document per line), classify genre, sample by quota.

Pass 1 writes byte offsets per sub-genre and full counts.
Pass 2 samples deterministically (crc32 threshold), cleans, dedups, writes JSONL.gz.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, struct, sys, time, zlib
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

SUBS = ["news", "wiki", "longpost", "qa", "review", "comment", "marketing", "other"]
REC = struct.Struct("<QI")  # offset, byte length


def pass1(path: str, outdir: str, limit_lines: int | None = None) -> dict:
    os.makedirs(outdir, exist_ok=True)
    files = {s: open(os.path.join(outdir, f"{s}.bin"), "wb") for s in SUBS}
    counts = {s: {"docs": 0, "chars": 0} for s in SUBS}
    n_total = n_bad = 0
    t0 = time.time()
    with open(path, "rb") as f:
        while True:
            off = f.tell()
            raw = f.readline()
            if not raw:
                break
            n_total += 1
            if limit_lines and n_total > limit_lines:
                break
            if n_total % 200000 == 0:
                el = time.time() - t0
                print(f"[pass1] {n_total:,} lines, {el:.0f}s, "
                      f"{n_total/max(el,1):,.0f} lines/s", flush=True)
            try:
                text = raw.decode("utf-8", errors="ignore").strip()
            except Exception:
                n_bad += 1
                continue
            if not common.shape_ok(text):
                n_bad += 1
                continue
            sub = common.classify_clue(text)
            files[sub].write(REC.pack(off, len(raw)))
            counts[sub]["docs"] += 1
            counts[sub]["chars"] += len(text)
    for fh in files.values():
        fh.close()
    counts["_meta"] = {"lines": n_total, "rejected": n_bad, "seconds": round(time.time() - t0, 1), "path": path}
    return counts


def iter_offsets(path: str, chunk: int = 1 << 20):
    with open(path, "rb") as f:
        while True:
            b = f.read(REC.size * chunk)
            if not b:
                break
            for i in range(0, len(b), REC.size):
                yield REC.unpack_from(b, i)


def sample_sub(path: str, sub: str, offsets_path: str, quota: int, out_path: str,
               rate: float, seen: set, got_chars: int = 0) -> tuple[int, int, int]:
    """One sampling round. Returns (docs_written, chars_written, dup_docs)."""
    docs = chars = dups = 0
    meta = common.SUBGENRE_TO_GENRE[sub]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mode = "at" if got_chars else "wt"
    with open(path, "rb") as src, gzip.open(out_path, mode, encoding="utf-8") as out:
        for off, blen in iter_offsets(offsets_path):
            if chars + got_chars >= quota:
                break
            h = (zlib.crc32(REC.pack(off, blen)) & 0xFFFFFFFF) / 4294967296.0
            if h >= rate:
                continue
            src.seek(off)
            raw = src.read(blen)
            try:
                text = common.clean(raw.decode("utf-8", errors="ignore"))
            except Exception:
                continue
            if not common.length_ok(text, sub) or not common.shape_ok(text):
                continue
            digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
            if digest in seen:
                dups += 1
                continue
            seen.add(digest)
            rec = {"id": digest, "source": "clue", "subgenre": sub, "genre": meta,
                   "chars": len(text), "text": text}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            docs += 1
            chars += len(text)
    return docs, chars, dups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(common.RAW, "CLUECorpusSmall.txt"))
    ap.add_argument("--work", default=os.path.join(common.WORK, "clue"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pass1-only", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    counts_path = os.path.join(args.work, "counts.json")
    if os.path.exists(counts_path):
        counts = json.load(open(counts_path))
        print("[pass1] cached", counts_path)
    else:
        counts = pass1(args.input, os.path.join(args.work, "offsets"), args.limit or None)
        json.dump(counts, open(counts_path, "w"), ensure_ascii=False, indent=1)
        print(json.dumps(counts, ensure_ascii=False, indent=1))
    if args.pass1_only:
        return

    # sampling rounds per sub-genre
    for sub in SUBS:
        quota = common.QUOTA.get(sub, 0)
        total = counts[sub]["chars"]
        if quota <= 0 or total <= 0:
            continue
        offsets_path = os.path.join(args.work, "offsets", f"{sub}.bin")
        out_path = os.path.join(args.work, f"sample_{sub}.jsonl.gz")
        seen: set[str] = set()
        got_docs = got_chars = 0
        for round_i in range(3):
            remaining = quota - got_chars
            if remaining <= 0:
                break
            rate = min(1.0, remaining / max(1, total - got_chars) * 1.15)
            d, c, dup = sample_sub(args.input, sub, offsets_path,
                                   quota, out_path, rate, seen, got_chars)
            got_docs += d
            got_chars += c
            print(f"[sample] {sub} round{round_i+1} rate={rate:.3f} docs+={d:,} "
                  f"chars+={c:,} total={got_chars:,}/{quota:,} dup={dup:,}", flush=True)
            if c == 0:
                break
        json.dump({"subgenre": sub, "docs": got_docs, "chars": got_chars,
                   "quota": quota, "total_chars": total},
                  open(os.path.join(args.work, f"sample_{sub}.json"), "w"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
