#!/usr/bin/env python3
"""Extract classical Chinese (poetry and canonical prose) from chinese-poetry.

The repo (MIT) stores every collection in a slightly different JSON shape:
lists of {title, paragraphs}, lists of {title, content}, or dicts wrapping
those. Walk each document and pull every "content"/"paragraphs" value.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

# directory -> subgenre; duplicates and variants are skipped on purpose
DIRS = {
    "全唐诗": "tang_poetry",
    "宋词": "song_ci",
    "元曲": "yuan_qu",
    "诗经": "canon",
    "楚辞": "canon",
    "论语": "canon",
    "四书五经": "canon",
    "蒙学": "canon",
    "五代诗词": "five_dynasties",
    "曹操诗集": "canon",
    "纳兰性德": "song_ci",
    "幽梦影": "canon",
}
KEYS = {"content", "paragraphs", "para", "text"}

# per-subgenre budget: Tang poetry dominates the repo, cap it so canonical
# prose and ci/qu keep enough weight for genre contrast
SUBQUOTA = {
    "tang_poetry": 12_000_000,
    "song_ci": 10_000_000,
    "yuan_qu": 4_000_000,
    "canon": 8_000_000,
    "five_dynasties": 2_000_000,
}


def strings(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in KEYS:
                if isinstance(v, str):
                    out.append(v)
                elif isinstance(v, list):
                    out.extend(x for x in v if isinstance(x, str))
            elif isinstance(v, (dict, list)):
                out.extend(strings(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(strings(v))
    return out


def docs_from(obj):
    """Yield document dicts from a parsed collection file."""
    if isinstance(obj, list):
        for item in obj:
            yield item
    elif isinstance(obj, dict):
        if any(k in obj for k in KEYS):
            yield obj
        else:
            for v in obj.values():
                if isinstance(v, list):
                    for item in v:
                        yield item
                elif isinstance(v, dict):
                    yield v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(common.RAW, "chinese-poetry"))
    ap.add_argument("--out", default=os.path.join(common.WORK, "classical_sample.jsonl.gz"))
    ap.add_argument("--quota", type=int, default=40_000_000)
    args = ap.parse_args()

    seen: set[str] = set()
    stats = {}
    docs = chars = 0
    with gzip.open(args.out, "wt", encoding="utf-8") as out:
        for d, sub in DIRS.items():
            root = os.path.join(args.root, d)
            if not os.path.isdir(root):
                continue
            d_docs = d_chars = 0
            for dirpath, _, files in os.walk(root):
                for fn in sorted(files):
                    if not fn.endswith(".json"):
                        continue
                    # the repo also keeps simplified/traditional variants of
                    # the same collection in sibling files; keep one of them
                    if fn.endswith("traditional.json"):
                        continue
                    if stats.get(sub, {}).get("chars", 0) >= SUBQUOTA.get(sub, args.quota):
                        continue
                    path = os.path.join(dirpath, fn)
                    try:
                        obj = json.load(open(path, encoding="utf-8"))
                    except Exception:
                        continue
                    for item in docs_from(obj):
                        if stats.get(sub, {}).get("chars", 0) >= SUBQUOTA.get(sub, args.quota):
                            break
                        parts = strings(item)
                        text = "\n".join(p.strip() for p in parts if p and p.strip())
                        if not (10 <= len(text) <= 30000):
                            continue
                        if common.cjk_ratio(text) < 0.5:
                            continue
                        digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
                        if digest in seen:
                            continue
                        seen.add(digest)
                        rec = {"id": digest, "source": "chinese-poetry", "subgenre": sub,
                               "genre": "classical", "chars": len(text), "text": text}
                        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        docs += 1
                        chars += len(text)
                        d_docs += 1
                        d_chars += len(text)
                        s = stats.setdefault(sub, {"docs": 0, "chars": 0})
                        s["docs"] += 1
                        s["chars"] += len(text)
            print(d, sub, d_docs, d_chars, "total", chars, flush=True)
    meta = {"source": "chinese-poetry", "docs": docs, "chars": chars,
            "quota": args.quota, "by_subgenre": stats,
            "license": "MIT repo; texts are public domain"}
    json.dump(meta, open(os.path.join(common.WORK, "sample_classical.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
