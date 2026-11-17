# OP-07 输入输出数据契约

## 1. 输入

OP-05 或 OP-06 运行目录（含 `result.jsonl`）或结果文件 `.jsonl`：

| 字段 | 用途 |
| --- | --- |
| `record_id` | 结果主键 |
| `labels` | OP-05 标签列表（`path` / `confidence` / `topK` / `modelVersion` / `treeVersion`） |
| `domainLabels` / `abilityLabels` | OP-06 标签列表（同上） |
| `unclassified` / `reasonCode` | 上游未归类原因，原样汇总 |
| `evidence.preview` | PII 扫描文本（仅提示，脱敏展示） |

树快照为内容/领域/能力三空间并集（`treeVersion=taxonomy-1013-pending`，H-02 待确认）。

## 2. 输出

`result.jsonl`（逐条一行）：

```json
{
  "record_id": "r_…",
  "labels": [{"path": ["…"], "confidence": 0.31, "sourceKey": "labels", "topK": [], "treeVersion": "…"}],
  "legal": true,
  "issues": [
    {"type": "ILLEGAL_PATH", "path": ["…"], "suggestion": ["…"], "detail": "路径不在 taxonomy-1013-pending 中"},
    {"type": "LOW_CONFIDENCE", "path": ["…"], "value": 0.12, "threshold": 0.25}
  ],
  "conflicts": [{"recordId": "r_…", "type": "DUPLICATE_PATH", "paths": [["…"], ["…"]], "detail": "同一记录重复出现 2 次"}],
  "pii": [{"type": "mobile_cn", "value": "13****00", "position": 42}],
  "unclassified": false,
  "reasonCode": null
}
```

- `issues[].type` ∈ `ILLEGAL_PATH`（`suggestion` 为编辑距离 ≤ `nearestNodeMaxDistance=3` 的最近节点，无则 null）、`LOW_CONFIDENCE`（`value` < `threshold`=0.25）；
- `conflicts[].type` ∈ `DUPLICATE_PATH`、`CROSS_DOMAIN_CONFLICT`；
- `pii[].type` ∈ `email` / `mobile_cn` / `id_card_cn` / `bank_card`，`value` 为脱敏值（首尾各保留 2 字符），原文不落盘；
- 治理建议只读：不修改上游标签、不入库。

辅助产物：

```text
illegal.jsonl        # 非法路径与最近节点建议
conflicts.jsonl      # 重复/跨领域冲突
pii.jsonl            # 脱敏命中
unclassified.jsonl   # {record_id, reasonCode, top1, margin}
governance_report.json  # 汇总、suggestions、reviewMetrics（无审核记录时全 null + REVIEW_RECORDS_REQUIRED）
metrics.json / manifest.json / failures.jsonl / input_manifest.json / summary.json
```

## 3. 样例

`dataset/sample/result_demo.jsonl`：1 条含非法路径与低置信标签的构造样例，可直接运行：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-label-governance")
print(core.run("operator/dm-label-governance/dataset/sample/result_demo.jsonl", {}, 42,
               "operator/runtime/output/op07-demo")["metrics"])
PY
```
