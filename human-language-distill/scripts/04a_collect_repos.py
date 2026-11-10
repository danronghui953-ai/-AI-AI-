#!/usr/bin/env python3
"""Collect pre-2022 Chinese GitHub repos via the search API (gh CLI)."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

QUERIES = [
    "中文 in:readme stars:>2000 pushed:<2022-01-01",
    "中文 in:readme stars:500..2000 pushed:<2022-01-01",
    "中文 in:readme stars:100..500 pushed:<2022-01-01",
    "中文 in:readme stars:20..100 pushed:<2022-01-01",
    "教程 in:readme stars:>50 pushed:<2022-01-01",
    "文档 in:readme stars:>50 pushed:<2022-01-01",
    "指南 in:readme stars:>50 pushed:<2022-01-01",
]


def gh(path: str) -> dict:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(common.WORK, "github_repos.json"))
    ap.add_argument("--pages", type=int, default=10)
    args = ap.parse_args()
    repos = {}
    for q in QUERIES:
        for page in range(1, args.pages + 1):
            enc = urllib.parse.quote(q, safe="")
            path = f"search/repositories?q={enc}&sort=stars&order=desc&per_page=100&page={page}"
            try:
                d = gh(path)
            except Exception as e:
                print("query failed", q, page, e)
                break
            items = d.get("items", [])
            if not items:
                break
            for r in items:
                full = r["full_name"]
                repos[full] = {
                    "full_name": full,
                    "stars": r.get("stargazers_count"),
                    "pushed_at": r.get("pushed_at"),
                    "license": (r.get("license") or {}).get("spdx_id"),
                    "description": (r.get("description") or "")[:200],
                }
            print(f"{q} page{page}: +{len(items)}, total {len(repos)}", flush=True)
            time.sleep(0.5)
    json.dump(repos, open(args.out, "w"), ensure_ascii=False, indent=1)
    print("repos", len(repos), "->", args.out)


if __name__ == "__main__":
    main()
