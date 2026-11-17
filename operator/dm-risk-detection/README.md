# OP-22 风险检测与分级（`dm-risk-detection`）

- 语义编码：`risk_metric_rule_v1`
- 阶段/优先级：S6 / P1
- 版本：`0.1.0`
- 模型：无

## 1. 用途与边界

**做**：消费 OP-08～OP-19 的 `metrics.json`，按 JSON 规则 DSL 判定风险等级，
输出去重/抑制后的风险条目（类型/等级/指标/证据/建议），并给出过时知识检测状态。

**不做**：不重复计算指标；不做风险工单/处置流程；不部署知识库；
过时知识库缺失时 `unavailable`，不编造过时率。

## 2. 规则 DSL

```json
{
  "id": "R-01", "type": "时效过时", "operator": "OP-09",
  "metric": "time.freshnessMean", "op": "lt",
  "warn": 0.4, "critical": 0.2, "minSample": 0,
  "scope": "corpus", "suggestion": "补充近 1–3 年语料..."
}
```

- `op`：`lt/gt/le/ge/eq/ne`；数值指标先判 `critical` 再判 `warn`；
- `minSample`：按 `samplePaths` 从上游 metrics 取样本量，不足时规则不执行并单列；
- `eq` 用于状态类指标（如 `truth.status=unavailable`），`level` 指定 info/warning；
- 去重：同一 `operator+type` 保留最高等级并合并证据；
- 抑制：同类型最多 `maxPerType` 条，超出记入 `suppressed`，保留高等级；
- 每条风险 `evidence` 引用上游 `metrics.json` 的路径、指标路径与值，不重复计算。

## 3. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `input_path` | 必填 | `bundle.json`（`operator_results`）或目录下 `bundle.json` |
| `params.operator_results` | 无 | `{ "OP-08": "/path/to/run", ... }`，优先于 bundle |

路径须在 `INPUT_DIR`/`OUTPUT_DIR` 内；支持算子目录名或 `OP-xx` 键。

## 4. 运行与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-risk-detection/tests
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-risk-detection")
print(core.run("operator/dm-risk-detection/dataset/sample/bundle.json", {}, 42,
               "operator/runtime/output/op22-demo")["metrics"])
PY
```

## 5. 产物

| 文件 | 内容 |
| --- | --- |
| `risks.jsonl` | 风险条目：`id/type/level/operator/metric/value/threshold/evidence/suggestion` |
| `risk_report.json` | 完整报告：`risks/evaluatedRules/rawHits/dedupedCount/suppressed/noData/insufficientSample/outdated` |
| `metrics.json` | 风险计数、规则数、无数据/样本不足/抑制计数、过时状态 |
| `manifest.json` / `summary.json` / `input_manifest.json` | 版本四件套、输入指纹 |

## 6. 已知限制

1. 规则与阈值为联调初值（H-03），需业务书面确认；
2. 过时知识检测依赖知识库/时间敏感领域清单（H-11），当前 `unavailable`；
3. 风险工单、处置、通知归平台；算子只产风险条目；
4. 规则只读取上游指标，不重新计算。

## 7. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=null`、`paramsHash`/`seed` 入 manifest/metrics；
证据目录 `operator/dm-risk-detection/output/evidence/<runId>/`。
