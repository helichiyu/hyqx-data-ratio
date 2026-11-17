# OP-08 规模、来源与领域画像（`dm-corpus-profiling`）

- 语义编码：`corpus_profile_scale_source_domain_v1`
- 阶段/优先级：S3 / P0
- 版本：`0.1.0`
- 模型：无（纯统计 + 配置基线）

## 1. 用途与边界

**做**：从 OP-02 标准记录计算条数、字符、时长、帧数、存储、压缩比与分位数；统计 FGW 六类来源占比，并用 AHP 计算来源可信度（四项分 + 总分 + CR）；可选消费 OP-06 领域标签，计算领域覆盖四种口径、缺口与 rollup。

**不做**：不读取原型常量；无领域标签时不推测分布；不写数据库、不做 UI。

## 2. 接口与参数

`input_path` 接受 OP-02 运行目录或 `records.jsonl`。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_records` | 1000000 | 最多记录数 |
| `percentiles` | `[50,90,99]` | 分位数列表 |
| `domain_labels_path` | 无 | OP-06 结果目录/文件，须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |
| `as_of` | 批次最大 `dt` | 新鲜度基准日 |

## 3. 指标口径

- **分位数**：nearest-rank（排序后取 `ceil(p/100·N)` 位），不插值；
- **来源占比**：`count / N × 100`，6 位小数；`shareSumPercent` 用于校验合计 100；
- **AHP**：权重 = 判断矩阵主特征向量（幂迭代），`λmax = mean((A·w)/w)`，`CI=(λmax-n)/(n-1)`，`CR=CI/0.90`（n=4），CR<0.1 一致；
- **来源四项分**：authority/transparency 来自 `configs/profile.json`（联调初值）；freshness = `近1年×0.6+近3年×0.3+3年以上×0.1`；evaluation = 该类 `quality.completeness` 均值；
- **类总分** = Σ 维度权重 × 维度分；**语料总分** = Σ 类占比 × 类总分；
- **领域覆盖**：level1/level2/leaf 覆盖率 = 出现节点数/树节点总数；labeledRecordRate = 有领域标签的文本记录数/文本记录数；
- **无领域标签**：`domainCoverage.status=unavailable`，`reasonCode=DOMAIN_LABELS_UNAVAILABLE`。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-corpus-profiling")
print(core.run("operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7", {}, 42,
               "operator/runtime/output/op08-demo")["metrics"]["scale"])
PY
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-corpus-profiling/tests -q
```

## 5. 已知限制

1. 六类来源依赖 OP-02 的 `source` 归类；样例批次以 `web_text` 回退为主；
2. authority/transparency 为联调初值，需业务书面确认（H-03）；
3. 领域覆盖依赖 OP-06；未提供时标 `unavailable`；
4. 分位数精确计算需缓存数值列（O(N) 数值内存），大规模批次由平台分片。

## 6. 版本与证据

`operatorVersion=0.1.0`、`treeVersion=taxonomy-1013-pending`、无模型；
证据目录 `operator/dm-corpus-profiling/output/evidence/<runId>/`。
