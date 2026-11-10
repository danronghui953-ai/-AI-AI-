#!/usr/bin/env python3
"""Turn profiles into README, report, rules, exemplars and index."""
from __future__ import annotations
import glob, gzip, hashlib, json, os, random, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, "profile")
REPORTS = os.path.join(ROOT, "reports")
EXEMPLARS = os.path.join(ROOT, "exemplars")

KEYS = ["sent_mean", "sent_cv", "sent_kurt", "mtld", "digit_per100", "ne_per100",
        "first_person_per100", "marker_per100", "parallel_ratio", "opening_template",
        "closing_template", "hedge_per100", "empty_condition_ratio", "judgment_per100",
        "both_sides_per100", "question_ratio", "assertion_per100", "compression_ratio",
        "adjacent_sim", "ngram_repeat", "para_cv", "burstiness"]

LABELS = {
    "sent_mean": "平均句长（字）", "sent_cv": "句长变异系数", "sent_kurt": "句长峰度",
    "mtld": "词汇多样性 MTLD", "digit_per100": "数字/百字", "ne_per100": "专名/百字",
    "first_person_per100": "第一人称/百字", "marker_per100": "话语标记/百字",
    "parallel_ratio": "排比句占比", "opening_template": "模板开场率",
    "closing_template": "模板收尾率", "hedge_per100": "限定词/百字",
    "empty_condition_ratio": "空条件句率", "judgment_per100": "明确判断/百字",
    "both_sides_per100": "两边都对/百字", "question_ratio": "疑问句占比",
    "assertion_per100": "断言句/百字", "compression_ratio": "压缩比",
    "adjacent_sim": "相邻句相似度", "ngram_repeat": "3-gram 重复率",
    "para_cv": "段长变异系数", "burstiness": "句长 burstiness",
}


def load_profiles() -> dict:
    out = {}
    for p in sorted(glob.glob(os.path.join(PROFILE, "genre", "*.json"))):
        d = json.load(open(p))
        out[d["genre"]] = d
    return out


def fnum(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, float):
        if abs(x) >= 100:
            return f"{x:.0f}"
        if abs(x) >= 1:
            return f"{x:.2f}"
        return f"{x:.{nd}f}"
    return str(x)


def feat(prof, key):
    d = prof.get("features", {}).get(key)
    return d if d else {}


def p50(prof, key, default=None):
    return feat(prof, key).get("p50", default)


def p10(prof, key):
    return feat(prof, key).get("p10")


def p90(prof, key):
    return feat(prof, key).get("p90")


def mean(prof, key):
    return feat(prof, key).get("mean")


def key_table(profiles: dict) -> str:
    genres = [g for g in ["im", "longform", "opinion", "news", "codedoc",
                          "literary", "classical"] if g in profiles]
    lines = ["| 指标 | " + " | ".join(genres) + " |", "|---|" + "---|" * len(genres)]
    for k in KEYS:
        vals = []
        for g in genres:
            d = feat(profiles[g], k)
            vals.append(f"{fnum(d.get('p50'))}")
        if any(v != "—" for v in vals):
            lines.append(f"| {LABELS.get(k, k)} | " + " | ".join(vals) + " |")
    return "\n".join(lines)


def make_rules(profiles: dict, validation: dict) -> str:
    im = profiles.get("im", {})
    lf = profiles.get("longform", {})
    op = profiles.get("opinion", {})
    out = ["# 人类写作基线规则", "",
           "每条规则后面是语料里测出来的数，不是审美判断。括号内为人类样本的 10–90 分位区间。",
           "生成时按文体取对应一节。", ""]

    def rule(title, body):
        out.extend([f"## {title}", "", body, ""])

    if im:
        rule("日常对话：短句，允许不完整",
             f"- 平均句长 {fnum(p50(im,'sent_mean'),1)} 字（P10–P90：{fnum(p10(im,'sent_mean'),1)}–{fnum(p90(im,'sent_mean'),1)}）。\n"
             f"- 句长变异系数 {fnum(p50(im,'sent_cv'),2)}；低于 {fnum(p10(im,'sent_cv'),2)} 说明句子太齐。\n"
             f"- 第一人称密度 {fnum(p50(im,'first_person_per100'),1)}/百字；对话里主语常省略，不必每句补全。\n"
             f"- 疑问句占比均值 {fnum(mean(im,'question_ratio'),3)}（P90 {fnum(p90(im,'question_ratio'),3)}）；对话靠上下文承接，不必每段都下结论。")
    if lf:
        rule("长文：句长要有落差，结构不要外露",
             f"- 平均句长 {fnum(p50(lf,'sent_mean'),1)} 字（P10–P90：{fnum(p10(lf,'sent_mean'),1)}–{fnum(p90(lf,'sent_mean'),1)}）。\n"
             f"- 句长变异系数 {fnum(p50(lf,'sent_cv'),2)}（P10–P90：{fnum(p10(lf,'sent_cv'),2)}–{fnum(p90(lf,'sent_cv'),2)}）。每段至少一句很短、一句较长。\n"
             f"- 模板开场率均值 {fnum(mean(lf,'opening_template'),3)}，模板收尾率均值 {fnum(mean(lf,'closing_template'),3)}；人类样本里很少见。\n"
             f"- 话语标记 {fnum(p50(lf,'marker_per100'),1)}/百字；超过 {fnum(p90(lf,'marker_per100'),1)} 就是模板腔。")
    if op:
        rule("观点：先给判断，再给条件",
             f"- 明确判断密度 {fnum(p50(op,'judgment_per100'),2)}/百字（P10–P90：{fnum(p10(op,'judgment_per100'),2)}–{fnum(p90(op,'judgment_per100'),2)}）。\n"
             f"- 空条件句率 {fnum(p50(op,'empty_condition_ratio'),3)}；P90 是 {fnum(p90(op,'empty_condition_ratio'),3)}，超过这条线就是免责话术。\n" +
             (f"- 「两边都对」句式均值 {fnum(mean(op,'both_sides_per100'),2)}/百字（P90 {fnum(p90(op,'both_sides_per100'),2)}）；高于 P90 说明不敢表态。\n"
              if (p90(op,'both_sides_per100') or 0) > 0 else "") +
             f"- 限定词均值 {fnum(mean(op,'hedge_per100'),2)}/百字（P90 {fnum(p90(op,'hedge_per100'),2)}）；只放在低置信断言上，不要平均撒。")
    nw = profiles.get("news")
    if nw:
        rule("新闻：先给可以核查的事实",
             f"- 数字密度中位数 {fnum(p50(nw,'digit_per100'),2)}/百字（P10–P90：{fnum(p10(nw,'digit_per100'),2)}–{fnum(p90(nw,'digit_per100'),2)}）。\n"
             f"- 专名密度中位数 {fnum(p50(nw,'ne_per100'),2)}/百字；低于 P10 通常说明消息源不清楚。\n"
             f"- 明确判断密度中位数 {fnum(p50(nw,'judgment_per100'),2)}/百字，低于观点类"
             f"（{fnum(p50(op,'judgment_per100'),2)}）；新闻里判断越少，可信度越高。")
    rule("所有文体：具体压抽象",
         f"- 数字密度：长文 {fnum(p50(lf,'digit_per100'),2)}/百字，观点 {fnum(p50(op,'digit_per100'),2)}/百字（P10 分别为 {fnum(p10(lf,'digit_per100'),2)}、{fnum(p10(op,'digit_per100'),2)}）。低于 P10 通常是空话。\n"
         f"- 专名密度：长文 {fnum(p50(lf,'ne_per100'),2)}/百字，观点 {fnum(p50(op,'ne_per100'),2)}/百字。\n"
         "- 一句不能被反对的话，信息量为零；删掉它，看看信息少了没有。")
    rule("所有文体：不要收尾总结",
         f"- 模板收尾率均值：长文 {fnum(mean(lf,'closing_template'),3)}，观点 {fnum(mean(op,'closing_template'),3)}。\n"
         "- 停在最后一个论点上。不写「综上所述」「希望对你有所帮助」。")
    rule("所有文体：控制重复",
         f"- 3-gram 重复率：长文 {fnum(p50(lf,'ngram_repeat'),2)}，观点 {fnum(p50(op,'ngram_repeat'),2)}。\n"
         f"- 相邻句相似度：长文 {fnum(p50(lf,'adjacent_sim'),2)}，观点 {fnum(p50(op,'adjacent_sim'),2)}。\n"
         "- 相邻两句说同一件事，删一句。")
    if validation.get("top_contrasts"):
        out.extend(["## 人类与 GPT-3.5 的最大差异", "",
                    "HC3 同题对照，Cohen's d 绝对值最大的几项。只作方向参考，AI 侧是 2022 年的模型。", "",
                    "| 特征 | 人类均值 | GPT-3.5 均值 | d |", "|---|---|---|---|"])
        for k, v in list(validation["top_contrasts"].items())[:10]:
            out.append(f"| {LABELS.get(k, k)} | {fnum(v['human_mean'])} | {fnum(v['ai_mean'])} | {v['cohen_d']:+.2f} |")
        out.append("")
    return "\n".join(out)


def make_report(profiles, validation, reliability, counts) -> str:
    lines = ["# 人味写作：人类语料蒸馏报告", "",
             "2026-11-10 · 中文 · 2022-01-01 之前的人类文本", "",
             "## 做了什么", "",
             "把 2022 年前的中文人类文本按体裁切开，测 50 多个可复现的文本特征，"
             "给每个体裁一份分布画像。没有训练模型，也没有做风格迁移。", "",
             "## 语料", ""]
    for g, p in sorted(profiles.items()):
        subs = ", ".join(f"{k} {v.get('n_docs', 0):,}" for k, v in p.get("subgenres", {}).items())
        lines.append(f"- **{g}**：{p['n_docs']:,} 篇，{p['n_chars']:,} 字（{subs}）。")
    lines.extend(["", "来源与许可见 `sources.yaml`。新闻、社区、评论来自 CLUECorpusSmall；"
                  "对话来自 LCCC；代码文档来自 2022 年前已停止推送的 GitHub 仓库；"
                  "文学来自 Wikisource 公版作者；新闻专版来自 THUCNews；"
                  "古诗文来自 chinese-poetry（公版文本）。", "", "## 核心画像", "",
                  key_table(profiles), "",
                  "数字是各体裁的中位数（P50）。完整的分位数、均值和 bootstrap 置信区间在 `profile/genre/*.json`。",
                  "", "## 关键发现", ""])
    im, lf, op = profiles.get("im"), profiles.get("longform"), profiles.get("opinion")
    if im and lf:
        lines.append(f"- 日常对话平均句长 {fnum(p50(im,'sent_mean'),1)} 字，长文 {fnum(p50(lf,'sent_mean'),1)} 字。"
                     f"拿同一套句长规则套两种文体，一定会失真。")
    if op:
        lines.append(f"- 观点类文本的空条件句率中位数 {fnum(p50(op,'empty_condition_ratio'),3)}，"
                     f"P90 为 {fnum(p90(op,'empty_condition_ratio'),3)}。人类不是不写条件，是不写不携带信息的条件。")
    if lf:
        lines.append(f"- 长文的模板开场率和收尾率都接近 {fnum(p50(lf,'opening_template'),2)}。"
                     "「随着……的发展」「综上所述」在人类样本里是少数派。")
    news = profiles.get("news")
    if news and lf:
        lines.append(f"- 新闻的数字密度中位数 {fnum(p50(news,'digit_per100'),2)}/百字，"
                     f"长文 {fnum(p50(lf,'digit_per100'),2)}/百字；"
                     f"专名密度 {fnum(p50(news,'ne_per100'),2)} vs {fnum(p50(lf,'ne_per100'),2)}。"
                     "新闻靠可核查的具体信息立住，观点文章靠判断立住，两者的具体性不能用同一把尺。")
    cl = profiles.get("classical")
    if cl:
        lines.append(f"- 古诗文的平均句长 {fnum(p50(cl,'sent_mean'),1)} 字，"
                     f"句长变异系数 {fnum(p50(cl,'sent_cv'),2)}。"
                     "它的节奏由格律决定，不适合拿现代散文的句长规则去套，单列出来是为了给「短句」一个历史参照。")
    if validation.get("models"):
        auc = max(v["auc"] for v in validation["models"].values())
        lines.append(f"- 用这些特征区分 HC3 的人类回答和 GPT-3.5 回答，AUC 最高 {auc:.3f}。"
                     "指标不是噪声，但 AI 侧是 2022 年的模型，不能当现代检测器。")
    lines.extend(["", "## 信度与精度", ""])
    if validation.get("models"):
        for name, v in validation["models"].items():
            lines.append(f"- {name}：AUC {v['auc']:.3f}，准确率 {v['accuracy']:.3f}。")
    for g, p in sorted(profiles.items()):
        lines.append(f"- {g}：{p.get('n_features_ci_lt10pct',0)}/{p.get('n_features_ci_measured',0)} "
                     f"个特征的 bootstrap 相对置信区间宽度 <10%。")
    if reliability:
        lines.append("- 单篇折半信度只作诊断：短文本的句长类特征天然不稳定，"
                     "所以规则只使用语料级分布，不用单篇分数做判定。")
    lines.extend(["", "## 边界", "",
                  "- 体裁标签是启发式分类，不是原始来源标签。CLUECorpusSmall 是逐行混合文件，"
                  "news/wiki/review/qa/comment 由规则判定，抽样人工复核过，但仍有误差。",
                  "- HC3 的 AI 侧是 2022 年 GPT-3.5。它只能证明指标有区分力，不能证明对 2026 年的模型有效。",
                  "- 代码文档规模最小，且偏向 2022 年前已停止推送的仓库，存在选择偏差。",
                  "- CLUECorpusSmall 每行一篇，长文没有换行，`para_cv` 在 longform / opinion 上恒为 0，不参与规则。",
                  "- classical 的建模单元是单首诗或单段古文，中位长度不到百字。"
                  "依赖长上下文的指标（MTLD、相邻句相似度）在短文本上大量缺失，只按有效样本统计。",
                  "- news 只有时政、科技、体育三类。财经和社会的源文件下载中断，话题分布有偏。",
                  "- 没有人类盲测。结论是语料级分布，不是「读者觉得像人」的因果证据。",
                  "- 新闻、社区原文有版权，仓库只放统计结果和 ≤300 字范例。",
                  "", "## 复现", "",
                  "```bash",
                  "cd human-language-distill/scripts",
                  "python3 02_scan_clue.py      # 需要先下载 CLUECorpusSmall",
                  "python3 03_scan_lccc.py",
                  "python3 04a_collect_repos.py && python3 04b_fetch_readmes.py",
                  "python3 05_scan_literary.py && python3 05b_clean_literary.py",
                  "python3 11_extract_thucnews.py && python3 12_extract_classical.py",
                  "python3 06_features.py",
                  "python3 07_profile.py",
                  "python3 07b_reliability.py",
                  "python3 08_validate.py",
                  "python3 09_report.py",
                  "python3 13_deep.py && python3 14_step2_report.py",
                  "```", ""])
    return "\n".join(lines)


def feature_dict() -> str:
    rows = [
        ("sent_mean", "平均句长（字）", "按 。！？；换行切句，句长取字符数"),
        ("sent_cv", "句长变异系数", "句长标准差 / 均值；衡量节奏落差"),
        ("sent_kurt", "句长峰度", "句长分布的尾部厚度"),
        ("burstiness", "句长 burstiness", "(σ−μ)/(σ+μ)，越接近 0 越均匀"),
        ("para_cv", "段长变异系数", "段落字符数的标准差 / 均值"),
        ("mtld", "词汇多样性", "MTLD，窗口 50，前后双向平均"),
        ("digit_per100", "数字密度", "数字字符数 / 总字符 × 100"),
        ("ne_per100", "专名密度", "jieba 词性 nr/ns/nt/nz / 总字符 × 100"),
        ("first_person_per100", "第一人称密度", "我/我们/咱/俺/自己 / 总字符 × 100"),
        ("marker_per100", "话语标记密度", "首先/然而/因此/总之等 / 总字符 × 100"),
        ("parallel_ratio", "排比句占比", "含三个以上并列项的句子 / 总句数"),
        ("opening_template", "模板开场率", "前 60 字命中「随着/在当今/近年来/众所周知」"),
        ("closing_template", "模板收尾率", "后 80 字命中「综上所述/希望/感谢/欢迎」"),
        ("hedge_per100", "限定词密度", "可能/也许/一定程度上等 / 总字符 × 100"),
        ("empty_condition_ratio", "空条件句率", "不携带变量、阈值或例外的条件句 / 断言句"),
        ("judgment_per100", "明确判断密度", "我建议/应该/必须/推荐等 / 总字符 × 100"),
        ("both_sides_per100", "两边都对密度", "各有优劣/取决于/因人而异等 / 总字符 × 100"),
        ("question_ratio", "疑问句占比", "以问号结尾的句子 / 总句数"),
        ("assertion_per100", "断言句密度", "非疑问、长度 ≥8 的句子 / 总字符 × 100"),
        ("compression_ratio", "压缩比", "zlib 压缩后字节 / 原始 UTF-8 字节"),
        ("ngram_repeat", "3-gram 重复率", "重复出现的字符 3-gram 占比"),
        ("adjacent_sim", "相邻句相似度", "相邻句字符 bigram Jaccard 均值"),
        ("idiom_ratio", "成语占比", "jieba 词性 i 的词 / 总词数"),
        ("noun_ratio", "名词占比", "jieba 词性 n* / 总词数"),
        ("verb_ratio", "动词占比", "jieba 词性 v* / 总词数"),
    ]
    out = ["# 特征字典", "", "| 字段 | 含义 | 算法 |", "|---|---|---|"]
    out += [f"| `{a}` | {b} | {c} |" for a, b, c in rows]
    out += ["", "所有比率都按字符或词数归一化，便于跨文体比较。"
            "`ne_per100`、`idiom_ratio`、`noun_ratio`、`verb_ratio` 依赖 jieba 词性标注，"
            "只在一部分分层子样本上计算。", ""]
    return "\n".join(out)


def select_exemplars(profiles):
    """Pick short, license-clean excerpts for each genre."""
    random.seed(20261110)
    os.makedirs(EXEMPLARS, exist_ok=True)
    sources = {
        "im": [(os.path.join(common.WORK, "lccc_sample.jsonl.gz"), "lccc", "MIT")],
        "longform": [(os.path.join(common.WORK, "clue", "sample_wiki.jsonl.gz"), "clue-wiki", "CC BY-SA 4.0")],
        "literary": [(os.path.join(common.WORK, "literary_sample.jsonl.gz"), "wikisource", "Public Domain")],
        "classical": [(os.path.join(common.WORK, "classical_sample.jsonl.gz"), "chinese-poetry", "Public Domain")],
        "codedoc": [(os.path.join(common.WORK, "codedoc_sample.jsonl.gz"), "github", None)],
    }
    index = []
    for genre, srcs in sources.items():
        gdir = os.path.join(EXEMPLARS, genre)
        os.makedirs(gdir, exist_ok=True)
        for old in os.listdir(gdir):
            if old.endswith(".md"):
                os.remove(os.path.join(gdir, old))
        picked = []
        for path, source, lic in srcs:
            if not os.path.exists(path):
                continue
            cands = []
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    if r.get("genre") and r["genre"] != genre:
                        continue
                    t = r.get("text", "")
                    if len(t) < 150:
                        continue
                    if "<URL>" in t or "<PHONE>" in t or "<EMAIL>" in t:
                        continue
                    if common.cjk_ratio(t) < 0.5:
                        continue
                    if genre == "codedoc":
                        lic = (r.get("license") or "").upper()
                        if lic not in {"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE",
                                       "CC0-1.0", "UNLICENSE", "CC-BY-4.0", "CC-BY-SA-4.0",
                                       "WTFPL", "ZLIB", "MPL-2.0"}:
                            continue
                    cands.append((r, t))
            random.shuffle(cands)
            per = max(1, 20 // max(1, len(srcs)))
            for r, t in cands[:per]:
                picked.append((source, lic, r, t[:300].rstrip()))
        for i, (source, lic, r, t) in enumerate(picked, 1):
            name = f"{i:03d}.md"
            lic_out = r.get("license") if source == "github" else lic
            meta = {"source": source, "license": lic_out, "subgenre": r.get("subgenre"),
                    "chars": len(t), "id": r.get("id"), "repo": r.get("repo"),
                    "title": r.get("title")}
            with open(os.path.join(gdir, name), "w", encoding="utf-8") as fh:
                fh.write("---\n")
                for k, v in meta.items():
                    if v is not None:
                        fh.write(f"{k}: {v}\n")
                fh.write("---\n\n" + t.strip() + "\n")
            index.append({"file": f"exemplars/{genre}/{name}", "genre": genre,
                          "subgenre": r.get("subgenre"), "chars": len(t),
                          "source": source, "license": lic_out, "id": r.get("id")})
    json.dump({"count": len(index), "items": index}, open(os.path.join(ROOT, "index.json"), "w"),
              ensure_ascii=False, indent=1)
    print("exemplars", len(index))
    return index




def make_readme(profiles, validation) -> str:
    total_docs = sum(p["n_docs"] for p in profiles.values())
    total_chars = sum(p["n_chars"] for p in profiles.values())
    lines = ["# 蒸馏人类语言", "",
             f"2022-01-01 之前的中文人类文本，{total_docs:,} 个建模单元，{total_chars/1e8:.2f} 亿字。",
             "按体裁测 50 多个可复现特征，产出分布画像、范例和规则。没有训练模型。短对话和短评论按 ~800 字打包后计。", "",
             "## 产物", "",
             "| 路径 | 内容 |", "|---|---|",
             "| `profile/genre/*.json` | 每个体裁的特征分布、分位数、bootstrap 置信区间 |",
             "| `profile/validation.json` | HC3 人机对照的 AUC 和效应量 |",
             "| `profile/deep/*.json` | 标点、短语、开头结尾、篇幅分层、体裁距离、人味分数 |",
             "| `reports/step2-report.md` | 第二轮分析结果 |",
             "| `reports/step2-plan.md` | 第二步计划与已知缺口 |",
             "| `profile/reliability.json` | 单篇折半信度诊断 |",
             "| `rules.md` | 由画像数字生成的写作规则 |",
             "| `exemplars/` | 许可干净的短范例，每条 ≤300 字 |",
             "| `reports/distill-report.md` | 方法、结果、边界 |",
             "| `reports/feature-dictionary.md` | 特征定义 |",
             "| `sources.yaml` | 语料来源、许可、校验和 |", "",
             "## 关键数字", ""]
    for g, p in sorted(profiles.items()):
        lines.append(f"- **{g}**：{p['n_docs']:,} 篇 / {p['n_chars']:,} 字；"
                     f"{p.get('n_features_ci_lt10pct',0)}/{p.get('n_features_ci_measured',0)} 个特征 CI 宽度 <10%。")
    if validation.get("models"):
        best = max(v["auc"] for v in validation["models"].values())
        lines.append(f"- HC3 人类 vs GPT-3.5：AUC {best:.3f}。")
    lines.extend(["", "## 语料", "",
                  "- CLUECorpusSmall（MIT，2016/2019）：新闻、社区、百科、评论。",
                  "- LCCC（MIT，2020）：微博多轮对话。",
                  "- GitHub 中文 README（2022 年前已停止推送的仓库，按仓库许可）。",
                  "- Wikisource 公版文学（作者去世超过 50 年）。",
                  "- THUCNews 新闻（时政 / 科技 / 体育，2007–2011 年新浪新闻）。",
                  "- chinese-poetry 古诗文（唐诗、宋词、元曲、四书五经，公版文本）。",
                  "- HC3 中文（CC BY-SA 4.0）：只做验证，不进主语料。", "",
                  "原始语料不进仓库。仓库只放统计结果和 ≤300 字范例。", "",
                  "## 复现", "",
                  "```bash",
                  "cd scripts",
                  "python3 02_scan_clue.py",
                  "python3 03_scan_lccc.py",
                  "python3 04a_collect_repos.py && python3 04b_fetch_readmes.py",
                  "python3 05_scan_literary.py && python3 05b_clean_literary.py",
                  "python3 11_extract_thucnews.py && python3 12_extract_classical.py",
                  "python3 06_features.py",
                  "python3 07_profile.py && python3 07b_reliability.py",
                  "python3 08_validate.py",
                  "python3 09_report.py",
                  "python3 13_deep.py && python3 14_step2_report.py",
                  "```", "",
                  "需要先按 `sources.yaml` 下载原始语料，路径写在 `scripts/common.py`。", ""])
    return "\n".join(lines)


def main():
    os.makedirs(REPORTS, exist_ok=True)
    profiles = load_profiles()
    val = json.load(open(os.path.join(PROFILE, "validation.json"))) if os.path.exists(os.path.join(PROFILE, "validation.json")) else {}
    rel = json.load(open(os.path.join(PROFILE, "reliability.json"))) if os.path.exists(os.path.join(PROFILE, "reliability.json")) else {}
    counts = {}
    for p in glob.glob(os.path.join(common.WORK, "sample_*.json")):
        counts[os.path.basename(p)] = json.load(open(p))

    open(os.path.join(REPORTS, "distill-report.md"), "w").write(make_report(profiles, val, rel, counts))
    open(os.path.join(ROOT, "README.md"), "w").write(make_readme(profiles, val))
    open(os.path.join(ROOT, "rules.md"), "w").write(make_rules(profiles, val))
    open(os.path.join(REPORTS, "feature-dictionary.md"), "w").write(feature_dict())
    select_exemplars(profiles)
    print("wrote report, rules, feature dictionary, exemplars")


if __name__ == "__main__":
    main()
