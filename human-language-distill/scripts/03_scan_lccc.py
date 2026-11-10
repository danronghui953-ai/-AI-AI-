#!/usr/bin/env python3
"""Sample LCCC dialogues (one list of utterances per line) into JSONL.gz."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="+", default=[os.path.join(common.RAW, "lccc_large.jsonl.gz"),
                                                   os.path.join(common.RAW, "lccc_base_train.jsonl.gz")])
    ap.add_argument("--out", default=os.path.join(common.WORK, "lccc_sample.jsonl.gz"))
    ap.add_argument("--quota", type=int, default=common.QUOTA_LCCC)
    ap.add_argument("--rate", type=float, default=0.0, help="0 = auto from quota")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # pass 1: total chars
    total = 0
    for path in args.input:
        if not os.path.exists(path):
            print("missing", path); continue
        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    turns = json.loads(line)
                except Exception:
                    continue
                total += sum(len(t.replace(" ", "")) for t in turns)
    rate = args.rate or min(1.0, args.quota / max(1, total) * 1.15)
    print(f"total_chars={total:,} rate={rate:.4f}")

    seen: set[str] = set()
    docs = chars = dups = 0
    with gzip.open(args.out, "wt", encoding="utf-8") as out:
        for path in args.input:
            if not os.path.exists(path):
                continue
            with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if chars >= args.quota:
                        break
                    h = (zlib.crc32(line.encode("utf-8", errors="ignore")) & 0xFFFFFFFF) / 4294967296.0
                    if h >= rate:
                        continue
                    try:
                        turns = json.loads(line)
                    except Exception:
                        continue
                    turns = [t.replace(" ", "").strip() for t in turns if t.strip()]
                    if not (2 <= len(turns) <= 30):
                        continue
                    text = "\n".join(turns)
                    text = common.clean(text)
                    if not (20 <= len(text) <= 3000) or common.cjk_ratio(text) < 0.5:
                        continue
                    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
                    if digest in seen:
                        dups += 1
                        continue
                    seen.add(digest)
                    rec = {"id": digest, "source": "lccc", "subgenre": "im", "genre": "im",
                           "chars": len(text), "turns": len(turns), "text": text}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    docs += 1
                    chars += len(text)
    meta = {"source": "lccc", "docs": docs, "chars": chars, "quota": args.quota,
            "total_chars": total, "rate": rate, "dups": dups}
    json.dump(meta, open(os.path.join(common.WORK, "sample_im.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
