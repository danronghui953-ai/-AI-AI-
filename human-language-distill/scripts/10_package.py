"""Assemble the repository folder: sources.yaml, checksums, git commit."""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from common import RAW, WORK

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# files that are not single top-level sources but still belong in the checksum
# manifest (the THUCNews downloads are partial on purpose)
EXTRA_HASH = [
    ("poetry.tgz", "chinese-poetry.tgz"),
    ("thucnews/时政.jsonl", "thucnews_时政.jsonl"),
    ("thucnews/科技.jsonl", "thucnews_科技.jsonl"),
    ("thucnews/体育.jsonl", "thucnews_体育.jsonl"),
]

RAW_FILES = [
    ("CLUECorpusSmall.txt", "clue", "CLUECorpusSmall（allenai/CLUECorpusSmall 镜像）",
     "https://huggingface.co/datasets/austenjs/ClueCorpusSmallDataset", "MIT（数据集打包）；文本版权归原作者"),
    ("lccc_large.jsonl.gz", "lccc", "LCCC large", "https://huggingface.co/datasets/thu-coai/lccc", "MIT"),
    ("lccc_base_train.jsonl.gz", "lccc", "LCCC base train", "https://huggingface.co/datasets/thu-coai/lccc", "MIT"),
    ("HC3-Chinese-all.jsonl", "hc3", "HC3 Chinese", "https://huggingface.co/datasets/Hello-SimpleAI/HC3-Chinese", "CC BY-SA 4.0"),
]


def sha256(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sources_yaml(checksums):
    lines = [
        "project: human-language-distill",
        "cutoff: 2022-01-01",
        f"generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "note: 原始语料不进仓库，只记录来源、许可和校验和。",
        "sources:",
    ]
    seen = set()
    for fn, sid, name, url, lic in RAW_FILES:
        if sid in seen:
            continue
        seen.add(sid)
        path = os.path.join(RAW, fn)
        size = os.path.getsize(path) if os.path.exists(path) else 0
        lines += [
            f"  - id: {sid}",
            f'    name: "{name}"',
            f"    url: {url}",
            f'    license: "{lic}"',
            f"    bytes: {size}",
            f"    sha256: {checksums.get(fn, 'MISSING')}",
        ]
    lines += [
        "  - id: thucnews",
        '    name: "THUCNews（2007–2011 新浪新闻，时政/科技/体育）"',
        "    url: https://huggingface.co/datasets/Tongjilibo/THUCNews",
        '    license: "Apache-2.0 打包；新闻正文版权归新浪及原作者"',
        "    selection: 每类最多 1500 万字，200-20000 字，CJK>=0.50",
        "    note: 财经、社会两类源文件下载中断，未纳入",
        "    file: work/thucnews_sample.jsonl.gz",
        "  - id: chinese-poetry",
        '    name: "chinese-poetry 古诗文（唐诗/宋词/元曲/四书五经）"',
        "    url: https://github.com/chinese-poetry/chinese-poetry",
        '    license: "MIT（仓库代码）；文本为公版"',
        "    selection: 唐诗 1200 万字，宋词 1000 万字上限（实际 187 万），元曲 400 万（实际 100 万），经部 800 万（实际 17 万）",
        "    file: work/classical_sample.jsonl.gz",
        "  - id: github-readme",
        '    name: "GitHub 中文 README（2022-01-01 前最后推送的仓库）"',
        "    url: https://api.github.com/search/repositories",
        '    license: "逐仓库，只收 MIT / Apache-2.0 / BSD / CC-BY / CC0 / 未声明"',
        "    selection: stars>=20, pushed:<2022-01-01, README 正文 300-20000 字，CJK>=0.30",
        "    exemplars: 只取 MIT/Apache-2.0/BSD/CC0/CC-BY/Unlicense/MPL-2.0 等宽松许可仓库",
        "    file: work/codedoc_sample.jsonl.gz",
        "  - id: wikisource",
        '    name: "Wikisource 中文公版文学"',
        "    url: https://zh.wikisource.org/w/api.php",
        '    license: "Public domain（作者去世超过 50 年）"',
        "    authors: 鲁迅, 老舍, 萧红, 郁达夫, 朱自清, 胡适, 徐志摩, 闻一多",
        "    file: work/literary_sample.jsonl.gz",
        "  - id: hc3",
        '    name: "HC3 Chinese（只做验证，不进主语料）"',
        "    url: https://huggingface.co/datasets/Hello-SimpleAI/HC3-Chinese",
        '    license: "CC BY-SA 4.0"',
        "    role: known-groups validation（人类 vs GPT-3.5）",
    ]
    return "\n".join(lines) + "\n"


def main():
    print("[package] hashing raw files")
    checksums = {}
    for fn, *_ in RAW_FILES:
        if fn in checksums:
            continue
        p = os.path.join(RAW, fn)
        if os.path.exists(p):
            checksums[fn] = sha256(p)
            print(f"  {fn} {checksums[fn][:16]}…")
    for src, label in EXTRA_HASH:
        p = os.path.join(RAW, src)
        if os.path.exists(p):
            checksums[label] = sha256(p)
            print(f"  {label} {checksums[label][:16]}…")

    with open(os.path.join(ROOT, "sources.yaml"), "w") as f:
        f.write(sources_yaml(checksums))

    os.makedirs(os.path.join(ROOT, "manifest"), exist_ok=True)
    with open(os.path.join(ROOT, "manifest", "checksums.sha256"), "w") as f:
        for fn, h in checksums.items():
            f.write(f"{h}  {fn}\n")

    gi = os.path.join(ROOT, ".gitignore")
    with open(gi, "w") as f:
        f.write("__pycache__/\n*.pyc\n.DS_Store\n")

    env = dict(os.environ, GIT_AUTHOR_NAME="Trump", GIT_AUTHOR_EMAIL="danronghui953@gmail.com",
               GIT_COMMITTER_NAME="Trump", GIT_COMMITTER_EMAIL="danronghui953@gmail.com")
    def run(*a):
        return subprocess.run(a, cwd=ROOT, env=env, check=True, capture_output=True, text=True)

    run("git", "add", "-A")
    msg = "蒸馏人类语言\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>\n"
    run("git", "commit", "-m", msg)
    print("[package] committed")
    r = run("git", "push", "origin", "main")
    print(r.stdout, r.stderr)


if __name__ == "__main__":
    main()
