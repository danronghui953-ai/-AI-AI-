#!/usr/bin/env python3
"""Sample THUCNews (Apache-2.0 packaging) by topic.

Files are JSONL with {id, title, content}; downloads may be partial, so
incomplete trailing lines are skipped.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

TOPICS = {"时政": "politics", "财经": "finance", "科技": "tech",
          "体育": "sports", "社会": "society"}
QUOTA_PER_TOPIC = 15_000_000
TAIL_RE = re.compile(r"\n\s*(相关阅读|相关稿件|相关新闻|高清大图|原标题|（完）|\(完\))[^\n]*")


def strip_tail(text: str) -> str:
    m = TAIL_RE.search(text)
    if m and m.start() > 300:
        text = text[:m.start()]
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(common.RAW, "thucnews"))
    ap.add_argument("--out", default=os.path.join(common.WORK, "thucnews_sample.jsonl.gz"))
    ap.add_argument("--quota", type=int, default=QUOTA_PER_TOPIC)
    args = ap.parse_args()

    seen: set[str] = set()
    stats = {}
    with gzip.open(args.out, "wt", encoding="utf-8") as out:
        for fn, topic in TOPICS.items():
            path = os.path.join(args.dir, fn + ".jsonl")
            if not os.path.exists(path):
                print("missing", path, flush=True)
                continue
            docs = chars = tried = 0
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    tried += 1
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    text = common.clean((d.get("title") or "") + "\n" + (d.get("content") or ""))
                    text = strip_tail(text)
                    if not (200 <= len(text) <= 20000):
                        continue
                    if common.cjk_ratio(text) < 0.5:
                        continue
                    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
                    if digest in seen:
                        continue
                    seen.add(digest)
                    rec = {"id": digest, "source": "thucnews", "subgenre": topic,
                           "genre": "news", "chars": len(text),
                           "text": text}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    docs += 1
                    chars += len(text)
                    if chars >= args.quota:
                        break
            stats[topic] = {"docs": docs, "chars": chars, "lines_read": tried}
            print(topic, docs, chars, "lines", tried, flush=True)
    json.dump(stats, open(os.path.join(common.WORK, "sample_thucnews.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
