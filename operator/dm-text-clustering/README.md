# OP-03 句向量与主题聚类（`dm-text-clustering`）

- 语义编码：`corpus_shard_embed_cluster_v1`
- 阶段/优先级：S2 / P0
- 版本：`0.1.0`
- 模型：`BAAI/bge-base-zh-v1.5`（768 维，MIT）；权重 `operator/weights/shared/bge-base-zh-v1.5/`

## 1. 用途与边界

**用途**：消费 OP-02 文本记录，按 512 token 切窗生成 bge 向量，K 搜索选最优簇数，输出记录→簇映射、簇规模与 c-TF-IDF 主题词，向量可供 OP-20 复用。

**做**：

- 只处理 `modal=text` 且文本非空的记录；非文本记录跳过并在 `metrics.skippedNonText` 计数；
- 句末优先打包到 512 token，超长句硬切；
- bge mean pooling + L2 归一化；聚类在 float32 上执行，向量落盘 float16；
- K 搜索：`max(8, ceil(sqrt(N/2)))` 到 `min(64, floor(4*sqrt(N)))`，粗网格（步长 4）+ 最优附近细化；用轮廓系数选 K；
- 固定 seed，KMeans（N>5000 用 MiniBatchKMeans）；
- c-TF-IDF（jieba 分词）输出每簇 top 10 主题词与代表记录。

**不做**：

- 不训练/微调向量模型；不做打标（OP-05）；
- 不产出需要人工主题标注的准确率；主题词可解释性只做人工抽查项；
- 不做向量数据库写入（OP-20）。

## 2. 接口与参数

五端点与平台一致。`input_path` 接受 OP-02 运行目录（含 `records.jsonl`）或 `records.jsonl` 文件。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `k` | 自动 | 指定簇数，跳过 K 搜索（仍写 `search`） |
| `min_k` / `max_k` | 8 / 64 | K 搜索边界 |
| `max_records` | 1,000,000 | 最多读取记录行数 |
| `batch_size` | 16 | 向量批大小 |
| `device` | `cpu` | `cpu`/`cuda`（不假装 GPU） |
| `keep_chunks` | false | 是否保留 chunk 向量与映射 |

`seed` 缺省 42；相同输入/参数/seed 的 `result.jsonl`、`vectors.npy`、`cluster_summary.json` 字节一致（同机、同模型版本）。

## 3. 输出

```text
result.jsonl          # {record_id, cluster, distance_to_centroid, chunk_count, text_chars}
vectors.npy           # (N, 768) float16，与 vector_ids.jsonl 行号对应
vector_ids.jsonl      # {row, record_id}
centroids.npy         # (K, 768) float32
cluster_summary.json  # K、轮廓系数、搜索曲线、每簇规模/主题词/代表记录
chunk_vectors.npy     # 仅 keep_chunks=true
chunk_manifest.jsonl  # 仅 keep_chunks=true：{row, record_id, chunk_index}
metrics.json / manifest.json / failures.jsonl / input_manifest.json / summary.json
```

`predict` 的 `outputFilePath` 指向 `result.jsonl`。

## 4. 指标口径

| 指标 | 口径 |
| --- | --- |
| `textRecords` | 读到的 `modal=text` 记录数（含空文本） |
| `clusteredRecords` | 成功生成向量并聚类的记录数 |
| `chunkCount` | 切窗后的 chunk 总数 |
| `k` / `silhouette` | 选中的簇数与轮廓系数（样本量 ≤5000） |
| `clusterSizes` | 簇大小 min/median/max/mean |
| `searchCandidates` | 实际评估的 K 个数（粗网格 + 细化） |
| `runtimeSec` | 本次运行耗时（不参与复算一致性） |

**未评测**：20 簇人工可解释性、主题词质量（无人工标注，H-05）。

## 5. 复算命令

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-text-clustering")
result = core.run(
    "operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7",
    params={}, seed=42, output_dir="operator/runtime/output/manual-op03")
print(result["runId"], result["metrics"]["k"], result["metrics"]["silhouette"])
PY
```

## 6. 测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-text-clustering/tests -q
```

覆盖：切窗/超长硬切、合成向量 K 选择、常量/小样本边界、c-TF-IDF、真实 bge 向量端到端、幂等、空文本/非文本、模型缺失。

## 7. 已知限制

1. 模型选型为 bge-base 而非任务卡 bge-m3，需人工确认（H-06）；
2. 跨硬件浮点差异可能影响簇边界，同机复算为准；
3. 单次全量向量在内存中（N×768 float32）；百万级需按平台分片调用；
4. CPU K 搜索在 N=426 时约 50 秒，大样本建议指定 K 或用 MiniBatch 阈值以上；
5. 主题词依赖 jieba 词典，专业术语覆盖有限。

## 8. 版本与证据

- `operatorVersion=0.1.0`；`modelVersion=bge-base-zh-v1.5`；`treeVersion=null`；
- 证据目录：`operator/dm-text-clustering/output/evidence/<runId>/`。
