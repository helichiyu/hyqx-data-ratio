# OP-10 文本属性与任务适配（`dm-text-profiling`）

- 语义编码：`corpus_profile_text_taskfit_v1`
- 阶段/优先级：S3 / P0
- 版本：`0.1.0`
- 模型：无（jieba 分词 + 规则），`rule-based-text-metrics-v1`

## 1. 用途与边界

**做**：句长、从句数/深度、被动句、TTR/MSTTR/MTLD、语体分类；输出结构/语义/领域三组六维 0–10 分与低适配清单。

**不做**：不加载依存句法/语体模型；不推测领域（domainMatch 复用 OP-06 结果，缺失即不参与）；不做内容生成。

## 2. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_records` | 1000000 | 最多记录数 |
| `domain_labels_path` | 无 | OP-06 结果目录/文件，须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |

## 3. 指标口径

- **句长**：字符数（分句后取均值/最大值）；**从句数** = 逗号/顿号等分隔段数；
- **从句深度** = 1 + 句内从属连词数（上限 4）；**被动句** = 命中 `被/受到/遭到/给/为…所`；
- **TTR** = 唯一 token / 总 token（长度敏感）；**MSTTR** = 50 token 窗口唯一率均值；**MTLD** 近似（TTR≤0.72 记一个因子，双向平均）；
- **语体**：关键词规则，置信度 = 命中数 / 该语体关键词数，未命中为 `general`；
- **六维**：完整性、复杂度、丰富度、信息密度、领域匹配、语体适配；分组权重 结构 0.4 / 语义 0.3 / 领域 0.3；无领域标签时权重重归一化；
- **低适配**：overall < 3.0（可配置）。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-text-profiling")
print(core.run("operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7", {}, 42,
               "operator/runtime/output/op10-demo")["metrics"]["genreCounts"])
PY
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-text-profiling/tests -q
```

## 5. 已知限制

1. 无句法分析模型，从句深度为连词近似；英文文本分词质量受限；
2. TTR 对长度敏感，主口径以 MSTTR/MTLD 为准；
3. 语体规则为联调初值，长尾语体（剧本、诗歌）可能落到 `general`；
4. 六维权重与低适配阈值需业务确认（H-03）。

## 6. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=rule-based-text-metrics-v1`、`treeVersion=null`；
证据目录 `operator/dm-text-profiling/output/evidence/<runId>/`。
