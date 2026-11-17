# OP-19 配比分析与报告（`dm-ratio-reporting`）

- 语义编码：`prod_ratio_report_v1`
- 阶段/优先级：S5 / P1
- 版本：`0.1.1`
- 模型：无

## 1. 用途与边界

**做**：消费 OP-05/07/08/09/10/14/15/17/18 的真实 `metrics.json`，聚合九维结果、
综合评分、状态矩阵、结论摘要，输出平台可渲染的报告数据包；可选生成 HTML。

**不做**：不重新计算上游指标；不编造缺失数据；不做 UI 排版交付；
渲染失败不影响数据包；报告结论措辞为模板化事实描述，不含人工判断。

## 2. 九维映射（全部来自真实算子输出）

| 维度 | 来源 | 指标口径 | 归一化 |
| --- | --- | --- | --- |
| 规模与来源 | OP-08 | 六类来源占比 | 归一化熵（log 6） |
| 领域覆盖 | OP-08 | 内容树一级覆盖率 | 原值 |
| 语言、地域与时效 | OP-09 | 新鲜度指数 | 原值；地域状态单列 |
| 文本属性与任务适配 | OP-10 | 六维总分 p50 | /10 |
| 质量与一致性 | OP-14 | 完整率、1−基尼、极性平衡度 | 三者均值 |
| 标签合法与治理 | OP-05/OP-07 | 路径合法率、合法率 | 两者均值；标注覆盖率单列 |
| 配比合规 | OP-15 | 校验单通过数/总数 | 比例 |
| 组装与打包一致性 | OP-17 | 重复数、Parquet 行数、选样数 | 无重复且行数一致记 1 |
| 评测与风险 | OP-18 | 综合质量分 | 原值；真值状态/合规状态单列 |

- 权重与分级阈值见 `configs/reporting.json`（联调初值，H-03）；
- 某维度来源缺失/字段缺失：`score=null`、`status=no_data`、`grade=no_data`，列入 `missing`；
- 综合分 = Σ 可用维度分×权重 / Σ 可用权重，不把缺失维度按 0 计。

## 3. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `input_path` | 必填 | `bundle.json`（含 `operator_results`）或目录下的 `bundle.json` |
| `params.operator_results` | 无 | `{ "OP-08": "/path/to/run", ... }`，优先于 bundle |
| `params.render_html` | 配置 | 是否生成 `report.html`（默认 true） |

每个路径指向算子运行目录（含 `metrics.json`）或直接指向 `metrics.json`。

## 4. 运行与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-ratio-reporting/tests
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-ratio-reporting")
print(core.run("operator/dm-ratio-reporting/dataset/sample/bundle.json", {}, 42,
               "operator/runtime/output/op19-demo")["metrics"])
PY
```

## 5. 产物

| 文件 | 内容 |
| --- | --- |
| `report_package.json` | 九维明细、状态矩阵、综合分、结论、证据索引、版本 |
| `status_matrix.json` | 维度/等级/得分/权重/缺数据原因 |
| `conclusions.jsonl` | 逐维度结论与严重度（info/warning/critical） |
| `report.html` | 可选渲染产物；失败时 `render.status=failed`，数据包不受影响 |
| `metrics.json` / `manifest.json` / `summary.json` / `input_manifest.json` | 指标、版本四件套、输入指纹 |

## 6. 已知限制

1. 九维映射、权重、阈值是联调初值，需业务确认（H-03）；
2. 缺失维度不参与综合分，评级会因可用维度减少而变化，报告逐项列出；
3. HTML 只是数据包的展示，正式排版由平台负责；
4. 结论为规则模板，不含主观质量判断。

## 7. 版本与证据

`operatorVersion=0.1.1`、`modelVersion=null`、`treeVersion` 取上游一致版本、`paramsHash` 入 manifest/metrics；
证据目录 `operator/dm-ratio-reporting/output/evidence/<runId>/`。
