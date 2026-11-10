#!/usr/bin/env python3
"""Fetch public-domain Chinese literature from Wikisource via action=parse.

TextExtracts returns empty for most Wikisource works (content lives in
templates, not <p> tags), so we render each page and strip the HTML.
"""
from __future__ import annotations
import argparse, gzip, hashlib, html.parser, json, os, re, ssl, sys, threading, time
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

API = "https://zh.wikisource.org/w/api.php"
UA = ("humanLanguageDistill/0.1 (https://github.com/danronghui953-ai/-AI-AI-; "
      "research corpus project) python-urllib/3.14")
AUTHORS = ["魯迅", "鲁迅", "老舍", "蕭紅", "萧红", "郁達夫", "郁达夫",
           "朱自清", "胡適", "胡适", "徐志摩", "聞一多", "闻一多"]
CTX = ssl.create_default_context()
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    pass

_lock = threading.Lock()
_last = [0.0]
INTERVAL = 0.25


def api(params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(5):
        with _lock:
            dt = time.time() - _last[0]
            if dt < INTERVAL:
                time.sleep(INTERVAL - dt)
            _last[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("rate limited")


def category_pages(cat: str, limit: int = 2000) -> list[str]:
    pages, cont = [], {}
    while len(pages) < limit:
        p = {"action": "query", "list": "categorymembers", "cmtitle": f"Category:{cat}",
             "cmtype": "page", "cmlimit": "500", **cont}
        d = api(p)
        for m in d.get("query", {}).get("categorymembers", []):
            if m.get("ns") != 0:
                continue
            t = m["title"]
            if t.startswith(("Author:", "Index:", "Page:", "User:", "Category:",
                             "Template:", "Wikisource:", "Portal:", "Help:")):
                continue
            pages.append(t)
        cont = d.get("continue", {})
        if not cont:
            break
    return pages[:limit]


class Text(html.parser.HTMLParser):
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "td", "blockquote"}

    def __init__(self):
        super().__init__()
        self.buf = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "sup"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "sup") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.buf.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def page_text(title: str) -> str | None:
    try:
        d = api({"action": "parse", "page": title, "prop": "text",
                 "disableeditsection": "1", "disabletoc": "1", "redirects": "1"})
    except Exception:
        return None
    h = d.get("parse", {}).get("text")
    if not h:
        return None
    p = Text()
    p.feed(h)
    t = "".join(p.buf)
    t = re.sub(r"\n{2,}", "\n", t)
    t = re.sub(r"[ \t　]+", " ", t).strip()
    return common.clean(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(common.WORK, "literary_sample.jsonl.gz"))
    ap.add_argument("--quota", type=int, default=common.QUOTA_LITERARY)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    owner: dict[str, str] = {}
    for a in AUTHORS:
        try:
            ps = category_pages(a)
        except Exception as e:
            print("skip author", a, type(e).__name__, flush=True)
            continue
        print(a, len(ps), flush=True)
        for t in ps:
            owner.setdefault(t, a)
        time.sleep(1.0)
    titles = list(owner)
    print("titles", len(titles), flush=True)

    seen: set[str] = set()
    docs = chars = 0
    with gzip.open(args.out, "wt", encoding="utf-8") as out, \
            ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(page_text, t): t for t in titles}
        for n, fut in enumerate(as_completed(futs), 1):
            if chars >= args.quota:
                for f in futs:
                    f.cancel()
                break
            t = futs[fut]
            txt = fut.result()
            if not txt or not (300 <= len(txt) <= 60000):
                continue
            if common.cjk_ratio(txt) < 0.5:
                continue
            digest = hashlib.blake2b(txt.encode("utf-8"), digest_size=8).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            rec = {"id": digest, "source": "wikisource", "subgenre": "prose",
                   "genre": "literary", "chars": len(txt), "title": t,
                   "author": owner[t], "text": txt}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            docs += 1
            chars += len(txt)
            if n % 200 == 0:
                print(f"parsed={n} docs={docs} chars={chars:,}", flush=True)
    meta = {"source": "wikisource", "docs": docs, "chars": chars, "titles": len(titles),
            "quota": args.quota, "authors": AUTHORS,
            "note": "author died before 1976; public domain in China; action=parse HTML stripped"}
    json.dump(meta, open(os.path.join(common.WORK, "sample_literary.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
