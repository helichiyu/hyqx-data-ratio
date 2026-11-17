# OP-20 知识图谱与向量索引（`dm-graph-indexing`）

- 语义编码：`tool_graph_vector_index_v1`
- 阶段/优先级：S6 / P1
- 版本：`0.1.0`
- 模型：复用 OP-03 的 bge 向量，不重新训练

## 1. 用途与边界

**做**：消费 OP-02 记录与 OP-03 向量；规则抽取实体/关系，导出图谱（JSONL + Neo4j Cypher）；
复用 bge 向量构建确定性 IVF 索引，输出 topK 检索、recall@k、QPS；如实报告 Neo4j/FAISS 服务状态。

**不做**：不部署 Neo4j/FAISS/健康度面板；不做本体实体链接金标；不联网下载模型；
不把规则抽取冒充人工标注的实体/关系。

## 2. 图谱口径

| 节点/边 | 说明 |
| --- | --- |
| `Record` | OP-02 记录（modal/source/dt） |
| `Label` | OP-05 最高置信标签路径；含 `SUBCLASS_OF` 层级边 |
| `Entity` | 规则抽取：日期/数字/机构后缀/引号术语，`ruleBased=true` |
| `ABOUT` | Record → Label |
| `MENTIONS` | Record → Entity |
| `CO_OCCURS` | 同记录实体共现，weight=次数（每记录上限 20 对） |

- 图谱计数以 `graph_stats.json` 与 nodes/edges 文件为准，逐项对账；
- Neo4j 导入：`neo4j_import.cypher`（MERGE 节点与关系，字符串已转义）。

## 3. 向量索引与检索

```text
L2 归一化 → MiniBatchKMeans(nlist, seed) 建簇 → 查询取 nprobe 个最近簇
近似 topK 与精确内积 topK 对比 → recall@k = |交集| / min(k, 精确结果数)
QPS = 查询数 / 查询耗时
```

- 参数：`nlist=16`、`nprobe=4`、`topK=10`、`queryCount=20`、`recallK=[1,5,10]`（联调初值）；
- 固定 seed 重建索引与检索结果一致；索引文件：`index/vectors.npy`、`centroids.npy`、`assignments.npy`、`meta.json`；
- 查询结果逐条写 `query_results.jsonl`（精确与近似 topK 对照）。

## 4. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `input_path` | 必填 | OP-02 运行目录/`records.jsonl`，或 bundle.json |
| `params.records_path` | `input_path` | 记录文件/目录 |
| `params.labels_path` | 无 | OP-05 运行目录/`result.jsonl`（无标签时只建实体图） |
| `params.vectors_path` | 无（必填） | OP-03 运行目录（`vectors.npy` + `vector_ids.jsonl`） |

服务地址：`NEO4J_URL` / `FAISS_URL` 环境变量；未配置时 `status=unavailable`、`reasonCode=SERVICE_NOT_CONFIGURED`。

## 5. 运行与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-graph-indexing/tests
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-graph-indexing")
print(core.run("operator/dm-graph-indexing/dataset/sample/records.jsonl",
               {"records_path": "operator/dm-graph-indexing/dataset/sample/records.jsonl",
                "labels_path": "operator/dm-graph-indexing/dataset/sample/labels.jsonl",
                "vectors_path": "operator/dm-graph-indexing/dataset/sample/vectors"},
               42, "operator/runtime/output/op20-demo")["metrics"]["vector"])
PY
```

## 6. 已知限制

1. 本体/KG/词表缺失（H-11），实体/关系为规则抽取，不能作为实体链接金标；
2. Neo4j/FAISS 服务由平台部署；算子只产文件，不发起网络连接；
3. 检索为本地 IVF 近似，recall@k 以精确内积为金标准；生产 FAISS 参数需联调；
4. 小样本下 `nlist` 会自动降到向量数，recall 分母取 min(k, 精确结果数)。

## 7. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=null`（沿用 OP-03 bge）、`paramsHash`/`seed` 入 manifest/metrics；
证据目录 `operator/dm-graph-indexing/output/evidence/<runId>/`。
