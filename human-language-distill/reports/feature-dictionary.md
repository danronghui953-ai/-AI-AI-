# 特征字典

| 字段 | 含义 | 算法 |
|---|---|---|
| `sent_mean` | 平均句长（字） | 按 。！？；换行切句，句长取字符数 |
| `sent_cv` | 句长变异系数 | 句长标准差 / 均值；衡量节奏落差 |
| `sent_kurt` | 句长峰度 | 句长分布的尾部厚度 |
| `burstiness` | 句长 burstiness | (σ−μ)/(σ+μ)，越接近 0 越均匀 |
| `para_cv` | 段长变异系数 | 段落字符数的标准差 / 均值 |
| `mtld` | 词汇多样性 | MTLD，窗口 50，前后双向平均 |
| `digit_per100` | 数字密度 | 数字字符数 / 总字符 × 100 |
| `ne_per100` | 专名密度 | jieba 词性 nr/ns/nt/nz / 总字符 × 100 |
| `first_person_per100` | 第一人称密度 | 我/我们/咱/俺/自己 / 总字符 × 100 |
| `marker_per100` | 话语标记密度 | 首先/然而/因此/总之等 / 总字符 × 100 |
| `parallel_ratio` | 排比句占比 | 含三个以上并列项的句子 / 总句数 |
| `opening_template` | 模板开场率 | 前 60 字命中「随着/在当今/近年来/众所周知」 |
| `closing_template` | 模板收尾率 | 后 80 字命中「综上所述/希望/感谢/欢迎」 |
| `hedge_per100` | 限定词密度 | 可能/也许/一定程度上等 / 总字符 × 100 |
| `empty_condition_ratio` | 空条件句率 | 不携带变量、阈值或例外的条件句 / 断言句 |
| `judgment_per100` | 明确判断密度 | 我建议/应该/必须/推荐等 / 总字符 × 100 |
| `both_sides_per100` | 两边都对密度 | 各有优劣/取决于/因人而异等 / 总字符 × 100 |
| `question_ratio` | 疑问句占比 | 以问号结尾的句子 / 总句数 |
| `assertion_per100` | 断言句密度 | 非疑问、长度 ≥8 的句子 / 总字符 × 100 |
| `compression_ratio` | 压缩比 | zlib 压缩后字节 / 原始 UTF-8 字节 |
| `ngram_repeat` | 3-gram 重复率 | 重复出现的字符 3-gram 占比 |
| `adjacent_sim` | 相邻句相似度 | 相邻句字符 bigram Jaccard 均值 |
| `idiom_ratio` | 成语占比 | jieba 词性 i 的词 / 总词数 |
| `noun_ratio` | 名词占比 | jieba 词性 n* / 总词数 |
| `verb_ratio` | 动词占比 | jieba 词性 v* / 总词数 |

所有比率都按字符或词数归一化，便于跨文体比较。`ne_per100`、`idiom_ratio`、`noun_ratio`、`verb_ratio` 依赖 jieba 词性标注，只在一部分分层子样本上计算。
