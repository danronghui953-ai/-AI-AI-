#!/usr/bin/env python3
"""Strip Wikisource navigation and licence boilerplate from the literary sample.

action=parse returns the whole rendered page: title, author, sister-project
links, licence footer. Those templates repeat on every page and would dominate
the lexical statistics, so remove them without touching the body text.
"""
from __future__ import annotations
import argparse, gzip, json, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

DROP_EXACT = {"←", "→", "姊妹计划: 数据项", "姊妹计划：数据项", "数据项"}
DROP_PREFIX = ("作者:", "作者：", "姊妹计划", "本作品收錄於《", "本作品收录于《",
               "此條目缺少頁面分類", "此条目缺少页面分类")
DROP_CONTAINS = ("屬於公有領域", "属于公有领域", "Public domain", "公有領域",
                 "版权期限", "版權期限")
YEAR_RE = re.compile(r"^\d{4}年$")


def clean_page(text: str) -> str:
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if s in DROP_EXACT or s.startswith(DROP_PREFIX):
            continue
        if i < 8 and YEAR_RE.match(s):
            continue
        if any(k in s for k in DROP_CONTAINS):
            # licence footer; everything after it is boilerplate
            break
        out.append(s)
    return common.clean("\n".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.join(common.WORK, "literary_sample.jsonl.gz"))
    ap.add_argument("--backup-suffix", default=".orig")
    args = ap.parse_args()
    tmp = args.path + ".tmp"
    kept = dropped = 0
    before = after = 0
    with gzip.open(args.path, "rt", encoding="utf-8") as f, \
            gzip.open(tmp, "wt", encoding="utf-8") as out:
        for line in f:
            r = json.loads(line)
            t0 = r["text"]
            t = clean_page(t0)
            before += len(t0)
            if len(t) < 300 or common.cjk_ratio(t) < 0.5:
                dropped += 1
                continue
            r["text"] = t
            r["chars"] = len(t)
            r["cleaned"] = "wikisource-nav-and-licence"
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            after += len(t)
            kept += 1
    bak = args.path + args.backup_suffix
    if not os.path.exists(bak):
        shutil.move(args.path, bak)
    else:
        os.remove(args.path)
    shutil.move(tmp, args.path)
    print(f"kept {kept}, dropped {dropped}, chars {before:,} -> {after:,}")
    meta_path = os.path.join(common.WORK, "sample_literary.json")
    if os.path.exists(meta_path):
        m = json.load(open(meta_path))
        m.update({"docs": kept, "chars": after,
                  "cleaned": "wikisource nav/licence boilerplate removed"})
        json.dump(m, open(meta_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
