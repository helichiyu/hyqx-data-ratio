# OP-17 数据组装与打包（`dm-dataset-packaging`）

- 语义编码：`prod_assembly_package_v1`
- 阶段/优先级：S5 / P0
- 版本：`0.1.1`
- 模型：无

## 1. 用途与边界

**做**：消费 OP-15 配比方案与 OP-02/OP-05 标准产物，按配额确定性选样，
输出选样清单、层实抽/配额、偏差报告、成品 Parquet（zstd、`modal/source/dt` 分区）、
逐文件 manifest（条数/字节/MD5/SHA-256），支持固定 seed 幂等与断点续跑。

**不做**：不做 OP-18 评测；不写数据库/配方状态机；不提供 UI；不改动上游产物；
不把库存不足的缺口用重复样本填满。

## 2. 选样口径

```text
每条记录只归一个标签 = OP-05 labels[] 中 confidence 最高的 path（平票按路径升序）
标签内排序          = sha256(seed | record_id) 升序
入选                = 该标签前 min(配额, 可用记录数) 条
配额                = OP-15 plan.json rows[].feedCount
缺口                = max(0, 配额 − 实抽)
```

- 记录只归一个标签，因此成品无重复；重复记录在读取阶段计入 `RECORD_ID_DUPLICATE`；
- 无标签、低置信未归类、标签不在配方的记录进入 `failures.jsonl`，不静默丢弃；
- 标签内哈希排序等价于固定 seed 的可复现随机抽样，不使用 `random`；
- `checkpoint.json` 每完成一个标签落盘（paramsHash + seed + completedLabels + perLabel + selectedIds），
  重跑从未完成标签继续，不重复、不丢样。

## 3. 成品与 manifest

- Parquet schema：`record_id/label/level1/level2/confidence/selection_rank/modal/source/dt/text/metadata_json/quality_json/partitions_json/hashes_json`；
- 分区：`modal=<modal>/source=<source>/dt=<dt>/part-<NNNNN>.parquet`；
- 压缩 zstd；分片默认 100000 行；row group 默认 50000 行（约 128 MB 目标）；
- `manifest.json` 逐文件记录 `rows/bytes/md5/sha256`，并给出 `dataset.rows/bytes`；
  写出后校验 Parquet 总行数 = 选样数，不一致直接失败；
- 下游读取示例：

```python
import pyarrow.dataset as ds
dataset = ds.dataset("operator/.../dataset", format="parquet", partitioning="hive")
print(dataset.to_table(columns=["record_id", "label", "text"]).num_rows)
```

## 4. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `input_path` | 必填 | OP-15 运行目录（含 `plan.json`） |
| `params.records_path` | 上游 manifest | OP-02 运行目录/`records.jsonl`（须在 `INPUT_DIR`/`OUTPUT_DIR` 内） |
| `params.labels_path` | 上游 manifest | OP-05 运行目录/`result.jsonl` |
| `params.resume` | `true` | 是否复用同 runId 的 checkpoint |

未传 `records_path`/`labels_path` 时，回退读取 OP-15 `input_manifest.json` 中的 `recordsPath`/`labelsPath`。

## 5. 运行与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-dataset-packaging/tests
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator/dm-dataset-packaging/dataset/sample")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-dataset-packaging")
print(core.run("operator/dm-dataset-packaging/dataset/sample/plan",
               {"records_path": "operator/dm-dataset-packaging/dataset/sample/records.jsonl",
                "labels_path": "operator/dm-dataset-packaging/dataset/sample/labels.jsonl"},
               42, "operator/runtime/output/op17-demo")["metrics"])
PY
```

## 6. 指标口径与已知限制

| 指标 | 口径 |
| --- | --- |
| `selectedCount` | 入成品记录数（唯一） |
| `selectionRate` | 实抽 / 配额 |
| `inventoryGap` | Σ max(0, 配额 − 实抽) |
| `bias.maxDeviation` | 配额已满足层的逐标签 `|实抽−配额|/配额` 最大值（抽样代表性） |
| `bias.maxQuotaDeviation` | 全部有配额层的偏差最大值（含库存不足导致的缺口） |
| `bias.maxSourceDeviation` | 实抽来源占比与按配额折算期望占比的最大绝对差 |
| `dataset.rows/bytes` | Parquet 实际行数/字节，与 manifest 逐文件对账 |

1. 小批次库存不足时实抽远低于 10 万配额，如实记录，不重复取样；
2. 一条记录只归一个标签，多标签记录的其它标签不重复计数（避免成品重复）；
3. `records_path`/`labels_path` 的变更不在输入目录指纹内；生产环境应由平台传入内容寻址路径或打包为单一输入目录；
4. 真值与合规资源不参与本算子，由 OP-18 处理。

## 7. 版本与证据

`operatorVersion=0.1.1`、`modelVersion` 取 OP-05 标签模型、`treeVersion` 取 OP-05 树版本、
`paramsHash` 入 manifest/metrics；证据目录 `operator/dm-dataset-packaging/output/evidence/<runId>/`。
