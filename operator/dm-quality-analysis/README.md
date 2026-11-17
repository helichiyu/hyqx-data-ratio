# OP-14 质量、一致性与难度（`dm-quality-analysis`）

- 语义编码：`corpus_profile_quality_difficulty_v1`
- 阶段/优先级：S3 / P0
- 版本：`0.1.0`
- 模型：无（规则 + SimHash），`rule-based-quality-v1`

## 1. 用途与边界

**做**：完整率、跨文档冲突（SimHash 近重复组内不一致）、标签分布基尼、标注覆盖、多模态一致性、难度四档、正/负/中性占比与平衡度、低质量清单。

**不做**：不加载 NLP/情感模型；无 OP-05 标签时不计算基尼/覆盖；不做自动处置。

## 2. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_records` | 1000000 | 最多记录数 |
| `labels_path` | 无 | OP-05 结果目录/文件，须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |

## 3. 指标口径

- **完整率** = 存在必填字段数 / 必填字段总数（文本额外要求非空）；
- **冲突**：64 位 SimHash，汉明距离 ≤3 为近重复组；组内去空白文本不一致计冲突组；
- **基尼**：`G = 2·Σ i·x_i/(n·Σx_i) − (n+1)/n`，阈值 0.6（可配置）；
- **多模态一致性**：`derivedFrom` 配对的双方一级标签集合有交集的比例；
- **难度**：句长(40)+从句(30)+稀有词比例(30) → 0–100 → 简单/中等/较难/困难；
- **极性**：自建词典 + 否定词翻转，`|score|<0.1` 为中性；平衡度 = `1 − |pos−neg|/total`。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-quality-analysis")
print(core.run("operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7", {}, 42,
               "operator/runtime/output/op14-demo")["metrics"]["completeness"])
PY
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-quality-analysis/tests -q
```

## 5. 已知限制

1. 冲突只覆盖近重复组，非近重复的语义矛盾不检测；
2. 极性为词典规则，领域词/反讽识别有限，仅用于占比参考；
3. 难度为文本复杂度代理，不评估知识难度；
4. 多模态一致性依赖 OP-02 的 `derivedFrom` 关联，样例批次仅 1 对。

## 6. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=rule-based-quality-v1`、`treeVersion=null`；
证据目录 `operator/dm-quality-analysis/output/evidence/<runId>/`。
