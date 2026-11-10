# 蒸馏人类语言

2022-01-01 之前的中文人类文本，486,101 个建模单元，4.25 亿字。
按体裁测 50 多个可复现特征，产出分布画像、范例和规则。没有训练模型。短对话和短评论按 ~800 字打包后计。

## 产物

| 路径 | 内容 |
|---|---|
| `profile/genre/*.json` | 每个体裁的特征分布、分位数、bootstrap 置信区间 |
| `profile/validation.json` | HC3 人机对照的 AUC 和效应量 |
| `profile/reliability.json` | 单篇折半信度诊断 |
| `rules.md` | 由画像数字生成的写作规则 |
| `exemplars/` | 许可干净的短范例，每条 ≤300 字 |
| `reports/distill-report.md` | 方法、结果、边界 |
| `reports/feature-dictionary.md` | 特征定义 |
| `sources.yaml` | 语料来源、许可、校验和 |

## 关键数字

- **codedoc**：2,112 篇 / 6,108,000 字；29/55 个特征 CI 宽度 <10%。
- **im**：70,072 篇 / 60,796,818 字；49/55 个特征 CI 宽度 <10%。
- **literary**：2,135 篇 / 6,871,472 字；30/53 个特征 CI 宽度 <10%。
- **longform**：182,133 篇 / 220,003,923 字；46/53 个特征 CI 宽度 <10%。
- **opinion**：229,649 篇 / 131,376,241 字；48/56 个特征 CI 宽度 <10%。
- HC3 人类 vs GPT-3.5：AUC 0.958。

## 语料

- CLUECorpusSmall（MIT，2016/2019）：新闻、社区、百科、评论。
- LCCC（MIT，2020）：微博多轮对话。
- GitHub 中文 README（2022 年前已停止推送的仓库，按仓库许可）。
- Wikisource 公版文学（作者去世超过 50 年）。
- HC3 中文（CC BY-SA 4.0）：只做验证，不进主语料。

原始语料不进仓库。仓库只放统计结果和 ≤300 字范例。

## 复现

```bash
cd scripts
python3 02_scan_clue.py
python3 03_scan_lccc.py
python3 04a_collect_repos.py && python3 04b_fetch_readmes.py
python3 05_scan_literary.py
python3 06_features.py
python3 07_profile.py && python3 07b_reliability.py
python3 08_validate.py
python3 09_report.py
```

需要先按 `sources.yaml` 下载原始语料，路径写在 `scripts/common.py`。
