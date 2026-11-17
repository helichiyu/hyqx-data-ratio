# OP-13 知识覆盖、热点与风格（`dm-knowledge-analysis`）

- 语义编码：`corpus_profile_knowledge_style_v1`
- 阶段/优先级：S3 / P1
- 版本：`0.1.0`
- 模型：无（Aho–Corasick 术语匹配 + 关键词规则），`rule-based-knowledge-v1`

## 1. 用途与边界

**做**：术语覆盖率与知识密度、事实/推理/创意占比、热点/长尾、语体占比。

**不做**：无 KG 不产出实体覆盖率（标 `KG_UNAVAILABLE`）；无术语表不产出术语覆盖率；不做实体链接、不生成知识条目。

## 2. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_records` | 100000 | 最多记录数 |
| `glossary_path` | 无 | 术语表 jsonl，须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |
| `as_of` | 批次最大年份 12-31 | 热点窗口基准日 |

## 3. 指标口径

- **术语**：Aho–Corasick 单遍匹配；覆盖率 = 命中的不同术语 / 术语表术语数；密度 = 命中次数 / 字数 × 100；
- **知识类型**：三类关键词命中占比（命中数/总命中），全 0 标 `unknown`；
- **热点/长尾**：距基准日 365 天内为 `hot`，否则 `long_tail`，无时间 `unknown`；
- **语体**：五类关键词规则，置信度 = 命中数 / 该类关键词数。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-knowledge-analysis/tests -q
```

## 5. 已知限制

1. 术语表/KG 未提供时覆盖率不可用，这是数据依赖而非实现缺失；
2. 关键词规则对反讽/长尾知识类型识别有限；
3. 热点窗口与语体规则为联调初值（H-03）。

## 6. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=rule-based-knowledge-v1`、`treeVersion=null`；
证据目录 `operator/dm-knowledge-analysis/output/evidence/<runId>/`。
