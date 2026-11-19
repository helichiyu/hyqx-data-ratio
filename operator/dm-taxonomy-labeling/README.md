# OP-06 领域/能力多标签（`dm-taxonomy-labeling`）

- 语义编码：`corpus_label_taxonomy_multilabel_v1`
- 阶段/优先级：S2 / P1
- 版本：`0.1.0`
- 模型：`bge-base-zh-v1.5`（768 维，MIT，与 OP-03/05 共用权重）

## 1. 用途与边界

**用途**：文本支持任意层级的多标签分类，输出两个**严格分离**的标签空间：

- 领域空间：16 行业树（209 叶子）；
- 能力空间：8 大类能力树（65 叶子）。

**方法**：内容与标签统一 bge 向量；每个空间独立余弦相似度、topK 内 softmax、相似度/置信度阈值裁剪，每空间最多 3 个标签；未达阈值输出「未明确」。路径必须命中 `treeVersion=taxonomy-1013-pending`。

**不做**：不训练分类器；不合并两个空间；不处理非文本模态（跳过并计数）；准确率不在本算子输出范围。

## 2. 接口与参数

`input_path` 接受 OP-02 运行目录（`records.jsonl`）或记录文件；只消费 `modal=text`。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_labels` | 3 | 每个空间最多标签数 |
| `min_similarity` | 0.45 | 余弦相似度下限 |
| `max_records` | 100000 | 最多记录数 |
| `device` | cpu | 向量设备 |
| `tree_snapshot_path` | 无 | 分类树快照路径（须在 `INPUT_DIR`/`OUTPUT_DIR` 内）；缺省用镜像内基线 |
| `tree_version` | 无 | 期望的树版本；与快照不一致直接失败 |

## 3. 输出

```text
result.jsonl              # {record_id, domainLabels[], abilityLabels[], domainUnknown, abilityUnknown, topK, unclassified, reasonCode, evidence}
label_vectors_domain.npy  # (209,768) float16
label_vectors_ability.npy # (65,768) float16
label_ids_{domain,ability}.jsonl
metrics.json / manifest.json / failures.jsonl / input_manifest.json / summary.json
```

标签项：`{path, confidence, similarity, topK, evidence, modelVersion, treeVersion}`。

## 4. 指标口径

- `labelSpaceSizes`：领域 209 / 能力 65；
- `spacesSeparated=true`：两个空间独立计算、独立裁剪；
- `labeledCounts` / `unknownCounts`：按空间统计；
- `meanLabelsPerRecord` / `meanConfidence`：按空间统计；
- `pathLegalRate`：命中树的标签占比（应为 1.0）；
- 不输出 accuracy 字段；只输出标注率、置信度、路径合法率等过程指标。

## 5. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-taxonomy-labeling")
print(core.run("operator/dm-taxonomy-labeling/dataset/sample/records_demo.jsonl", {}, 42,
               "operator/runtime/output/op06-demo")["metrics"])
PY
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-taxonomy-labeling/tests -q
```

## 6. 已知限制

1. 零样本多标签，专业/长尾领域区分度有限，阈值需人工确认；
2. 领域树/能力树权威源与版本待 H-02/Q-01 确认；
3. 只处理文本记录；图像/音频/视频的领域/能力标签需先转写（后续可接 OP-05 证据）；
4. 准确率/混淆矩阵不在本算子输出范围。

## 7. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=bge-base-zh-v1.5`、`treeVersion=taxonomy-1013-pending`；
证据目录 `operator/dm-taxonomy-labeling/output/evidence/<runId>/`。
