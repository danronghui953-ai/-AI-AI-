#!/usr/bin/env python3
"""Fetch READMEs at HEAD for repos with pushed_at < 2022-01-01, filter Chinese, sample."""
from __future__ import annotations
import argparse, base64, gzip, hashlib, json, os, ssl, subprocess, sys, time, urllib.request, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def remaining() -> int:
    try:
        out = subprocess.run(["gh", "api", "rate_limit", "--jq", ".resources.core.remaining"],
                             capture_output=True, text=True, timeout=30)
        return int(out.stdout.strip() or 9999)
    except Exception:
        return 9999


def reset_in() -> int:
    try:
        out = subprocess.run(["gh", "api", "rate_limit", "--jq", ".resources.core.reset"],
                             capture_output=True, text=True, timeout=30)
        return max(0, int(out.stdout.strip()) - int(time.time())) + 5
    except Exception:
        return 300


TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
CTX = ssl.create_default_context()
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    pass


def fetch_readme(full: str) -> str | None:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{full}/readme",
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Accept": "application/vnd.github.raw",
                 "User-Agent": "human-language-distill/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", default=os.path.join(common.WORK, "github_repos.json"))
    ap.add_argument("--out", default=os.path.join(common.WORK, "codedoc_sample.jsonl.gz"))
    ap.add_argument("--quota", type=int, default=common.QUOTA_CODEDOC)
    ap.add_argument("--max-repos", type=int, default=5000)
    args = ap.parse_args()
    repos = json.load(open(args.repos))
    candidates = [v for v in repos.values() if (v.get("pushed_at") or "") < "2022-01-01"]
    candidates.sort(key=lambda x: -(x.get("stars") or 0))
    candidates = candidates[:args.max_repos]
    print("candidates", len(candidates))

    seen: set[str] = set()
    docs = chars = tried = 0
    tried_path = args.out + ".tried"
    tried_repos: set[str] = set()
    if os.path.exists(tried_path):
        tried_repos = set(open(tried_path).read().split())
    if os.path.exists(args.out):
        with gzip.open(args.out, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                seen.add(r["id"]); docs += 1; chars += r.get("chars", 0)
        print(f"resume: {docs} docs, {chars:,} chars")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tried_fh = open(tried_path, "a")
    pending = [r for r in candidates if r["full_name"] not in tried_repos]
    print("pending", len(pending), flush=True)

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    lock = threading.Lock()
    last = [0.0]
    interval = 0.75

    def job(r):
        with lock:
            dt = time.time() - last[0]
            if dt < interval:
                time.sleep(interval - dt)
            last[0] = time.time()
        return r, fetch_readme(r["full_name"])

    def accept(r, txt):
        nonlocal docs, chars
        if not txt:
            return
        txt = common.clean(txt)
        if not (300 <= len(txt) <= 20000):
            return
        if common.cjk_ratio(txt) < 0.30:
            return
        digest = hashlib.blake2b(txt.encode("utf-8"), digest_size=8).hexdigest()
        if digest in seen:
            return
        seen.add(digest)
        rec = {"id": digest, "source": "github", "subgenre": "readme", "genre": "codedoc",
               "chars": len(txt), "repo": r["full_name"], "license": r.get("license"),
               "stars": r.get("stars"), "text": txt}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        docs += 1
        chars += len(txt)

    with gzip.open(args.out, "at", encoding="utf-8") as out, \
            ThreadPoolExecutor(max_workers=8) as pool:
        for i in range(0, len(pending), 24):
            if chars >= args.quota:
                break
            if remaining() < 200:
                w = reset_in()
                print(f"rate limit low, sleeping {w}s", flush=True)
                time.sleep(w)
            batch = pending[i:i + 24]
            for fut in as_completed([pool.submit(job, r) for r in batch]):
                r, txt = fut.result()
                tried += 1
                tried_repos.add(r["full_name"])
                tried_fh.write(r["full_name"] + "\n")
                accept(r, txt)
            tried_fh.flush()
            out.flush()
            print(f"tried={tried} docs={docs} chars={chars:,}", flush=True)
    meta = {"source": "github", "docs": docs, "chars": chars, "tried": tried,
            "candidates": len(candidates), "quota": args.quota,
            "note": "pushed_at < 2022-01-01; HEAD README fetched; biased to inactive repos"}
    json.dump(meta, open(os.path.join(common.WORK, "sample_codedoc.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
