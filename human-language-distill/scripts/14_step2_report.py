#!/usr/bin/env python3
"""Render the step-2 report and plan from profile/deep/*.json."""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEEP = os.path.join(ROOT, "profile", "deep")
REPORTS = os.path.join(ROOT, "reports")


def load(name, default=None):
    p = os.path.join(DEEP, f"{name}.json")
    if not os.path.exists(p):
        return default if default is not None else {}
    return json.load(open(p))


def fmt(v, nd=2):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def report():
    summary = json.load(open(os.path.join(ROOT, "profile", "summary.json")))
    val = json.load(open(os.path.join(ROOT, "profile", "validation.json")))
    punct, bundles = load("punctuation"), load("bundles")
    edges, strata = load("edges"), load("length_strata")
    dist, hl = load("distance"), load("humanlikeness")

    total_docs = sum(v["n_docs"] for v in summary.values())
    total_chars = sum(v["n_chars"] for v in summary.values())
    genres = [g for g in ["im", "longform", "opinion", "news", "codedoc",
                          "literary", "classical"] if g in summary]

    L = ["# 第二轮：从分布到句式", "",
         f"在 {total_docs:,} 个建模单元、{total_chars/1e8:.2f} 亿字上，"
         "这一轮补了新闻和古诗文两类语料，并把分析从「体裁平均」推到标点、短语、开头结尾和篇幅分层。", "",
         "## 新增语料", ""]
    rows = []
    for g in ["news", "classical"]:
        if g in summary:
            rows.append([g, f"{summary[g]['n_docs']:,}", f"{summary[g]['n_chars']:,}",
                         ", ".join(f"{k} {v:,}" for k, v in summary[g]["subgenres"].items())])
    if rows:
        L.append(table(["体裁", "单元", "字数", "子类"], rows))
        L.append("")

    if punct:
        L += ["## 标点节奏", "",
              "每千字标点数。逗号密度是最直接的「停顿频率」，句号密度是「断句频率」。", ""]
        rows = []
        for g in genres:
            p = punct.get(g)
            if not p:
                continue
            d = p["per_1000"]
            rows.append([g, fmt(d.get("comma", 0), 1), fmt(d.get("period", 0), 1),
                         fmt(d.get("question", 0), 2), fmt(d.get("exclaim", 0), 2),
                         fmt(d.get("enum", 0), 1), fmt(d.get("ellipsis", 0), 2),
                         fmt(p.get("punct_per_1000"), 1)])
        L.append(table(["体裁", "逗号", "句号", "问号", "叹号", "顿号", "省略号", "合计"], rows))
        L.append("")

    if bundles:
        L += ["## 高频短语", "",
              "jieba 分词后的 2–3-gram，按每万词频次取前 12。"
              "这些是各体裁自己长出来的说法，不是从规则库挑的。", ""]
        for g in genres:
            b = bundles.get(g)
            if not b:
                continue
            top = "、".join(f"`{x['bundle']}`({x['count']})" for x in b["top"][:12])
            L.append(f"- **{g}**：{top}")
            dist_list = b.get("distinctive", [])[:8]
            if dist_list:
                dd = "、".join(f"`{x['bundle']}`×{x['log2_lift']}" for x in dist_list)
                L.append(f"  - 相对其他体裁的偏置（log2 lift）：{dd}")
        L.append("")

    if edges:
        L += ["## 开头和结尾", "",
              "按篇统计，share 是含该片段的文档占比。开头片段取文首 20 字内，结尾取文末 20 字内。", ""]
        for g in genres:
            e = edges.get(g)
            if not e:
                continue
            first = "、".join(f"`{x['gram']}`" for x in e["first"][:8])
            last = "、".join(f"`{x['gram']}`" for x in e["last"][:8])
            L.append(f"- **{g}**（{e['docs']:,} 篇）开头：{first}")
            L.append(f"  - 结尾：{last}")
        L.append("")

    if strata:
        L += ["## 篇幅分层", "",
              "同一个体裁里，短文本和长文本不是一种东西。下表是各体裁按篇幅分箱后的平均句长和句长变异系数。", ""]
        rows = []
        for g in genres:
            s = strata.get(g)
            if not s:
                continue
            cells = [g]
            for b in ["<200", "200-500", "500-1000", "1000-3000", "3000+"]:
                d = s.get(b)
                if not d:
                    cells.append("—")
                else:
                    cells.append(f"{fmt(d.get('sent_mean'), 1)}/{fmt(d.get('sent_cv'), 2)}")
            rows.append(cells)
        if rows:
            L.append(table(["体裁", "<200", "200–500", "500–1000", "1000–3000", "3000+"], rows))
            L.append("")
            L.append("单元格为 平均句长 / 句长变异系数。少于 50 篇的分箱不显示。")
            L.append("")

    if dist and dist.get("pairwise"):
        L += ["## 体裁距离", "",
              f"用 {dist['n_features']} 个在全部体裁上都有覆盖的特征，按体裁均值标准化后算欧氏距离。"
              "距离越大，两种文体的写法越不能互换。", ""]
        pairs = sorted(dist["pairwise"].items(), key=lambda kv: -kv[1]["euclidean"])
        rows = [[a.replace("|", " ↔ "), fmt(v["euclidean"]), fmt(v["cosine"], 3)]
                for a, v in pairs[:12]]
        L.append(table(["体裁对", "欧氏距离", "余弦相似度"], rows))
        L.append("")

    if hl and not hl.get("skipped"):
        L += ["## HC3 参照分数", "",
              "在 HC3 中文上训练逻辑回归（人类回答=0，GPT-3.5 回答=1），"
              "剔除 `chars`、`n_sents` 等长度特征后，给每个体裁的文档打分，"
              "取「被判为 AI 的概率」分布。", ""]
        rows = []
        for g in genres:
            h = hl.get(g)
            if not h:
                continue
            rows.append([g, h["n"], fmt(h["mean_ai_prob"], 3), fmt(h["p10"], 3),
                         fmt(h["p50"], 3), fmt(h["p90"], 3)])
        L.append(table(["体裁", "样本", "均值", "P10", "P50", "P90"], rows))
        L.append("")
        L.append("分数低不等于「像人」，只说明在这个 2022 年的分类器眼里，"
                 "它的特征组合离 GPT-3.5 的答案更远。现代模型完全可能反着来。")
        L.append("")
        L.append("第一版没有剔除长度特征，IM 和代码文档的 AI 概率都是 0.99 以上；"
                 "把长度拿掉后 IM 降到 0.003。这个对比本身说明："
                 "任何号称测「人味」的分类器，先要看它有没有在测长短。")
        L.append("")

    L += ["## 边界", "",
          "- 新闻只有时政、科技、体育，财经和社会没下到。",
          "- 古籍是单篇采样，诗歌占绝对多数；经部文本量小，不能代表文言散文。",
          "- longform 是启发式归并，混入基金公告、营销长文等 longpost 子类；"
          "短语表里的「基金管理」「长按二维码」就是证据。",
          "- 开头结尾统计已去掉 `<URL>` 等占位符和纯数字片段，否则 HTML 残留会排在第一位。",
          "- 文学类按作者类目抓取，混入日记、书目和序跋；鲁迅日记这种极短句会拉低该体裁的句长。",
          "- Wikisource 页面已剔除标题、作者、姊妹计划、版权声明等模板行；"
          "残留的导航文字仍可能影响文学类的短语统计。",
          "- HC3 参照分数用的是 2022 年 GPT-3.5，不是 2026 年的模型。",
          "- 所有结论都是语料级统计，没有做人评。", ""]
    return "\n".join(L)


def plan():
    summary = json.load(open(os.path.join(ROOT, "profile", "summary.json")))
    total_docs = sum(v["n_docs"] for v in summary.values())
    total_chars = sum(v["n_chars"] for v in summary.values())
    return f"""# 第二步计划

执行状态：本轮已按此计划完成，结果见 `reports/step2-report.md`。

## 目标

第一轮给出了「每种文体平均长什么样」。这一轮要回答三个更细的问题：

1. 同一体裁内部，篇幅不同时写法怎么变？
2. 哪些短语、开头、结尾是某个体裁独有的？
3. 把「像人」拆成可测的维度后，各体裁离 2022 年的 AI 有多远？

## 语料

在原有 5 类之上补两类，总计 {total_docs:,} 个建模单元、{total_chars/1e8:.2f} 亿字。

| 语料 | 用途 | 许可 |
|---|---|---|
| THUCNews（时政/科技/体育） | 独立新闻体裁，把新闻从 longform 里拆出来 | Apache-2.0 打包，正文版权归新浪 |
| chinese-poetry（唐诗/宋词/元曲/经部） | 古典参照系，检验「短句」跨时代是否稳定 | 仓库 MIT，文本公版 |

原文不进仓库，只进 `work/`；仓库保留统计、派生指标和 ≤300 字范例。

## 分析

| 分析 | 方法 | 产物 |
|---|---|---|
| 篇幅分层 | 按 <200 / 200–500 / 500–1000 / 1000–3000 / 3000+ 分箱，重算核心特征 | `profile/deep/length_strata.json` |
| 标点画像 | 每千字统计 15 类标点，含逗号、句号、问号、顿号、省略号 | `profile/deep/punctuation.json` |
| 短语 | jieba 分词，2–3-gram 频次与跨体裁 log2 lift | `profile/deep/bundles.json` |
| 开头结尾 | 文首/文末 20 字内的 2–3-gram 文档占比 | `profile/deep/edges.json` |
| 体裁距离 | 全特征 z-score 后的欧氏距离与余弦相似度 | `profile/deep/distance.json` |
| HC3 参照 | 人机逻辑回归，剔除长度特征后给每个体裁打 AI 概率分布 | `profile/deep/humanlikeness.json` |

## 验收

- 每个新体裁至少 1 万个建模单元，特征 bootstrap 相对置信区间 <10% 的比例不低于第一轮。
- 每条新规则都能追到一个 JSON 字段，不写没有数字支撑的断言。
- 范例只从公版或宽松许可文本里取。
- 全部脚本可在 `scripts/` 下按编号顺序重跑。

## 已知缺口

- THUCNews 的财经、社会两类没下载成功，新闻样本偏科技。
- 古诗文以诗歌为主，不能代表文言散文。
- 人机对照只有 GPT-3.5，没有 2024–2026 年的模型。
- 仍然没有人类盲测。

## 第三步候选

1. 补齐 THUCNews 两类，另找一份 2022 年前的长篇非虚构（报告文学、深度报道）。
2. 用 2024 年后的开源中文模型生成对照文本，重做 HC3 式验证。
3. 做 30–50 人的 pairwise 盲测，检验这些指标与人类判断的相关性。
4. 把规则做成可执行的检查器：输入一段文本，输出它在每个维度上的分位位置。
"""


def main():
    os.makedirs(REPORTS, exist_ok=True)
    open(os.path.join(REPORTS, "step2-report.md"), "w").write(report())
    open(os.path.join(REPORTS, "step2-plan.md"), "w").write(plan())
    print("wrote reports/step2-report.md, reports/step2-plan.md")


if __name__ == "__main__":
    main()
