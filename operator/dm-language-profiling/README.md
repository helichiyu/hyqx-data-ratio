# OP-09 语言、地域与时效画像（`dm-language-profiling`）

- 语义编码：`corpus_profile_language_region_time_v1`
- 阶段/优先级：S3 / P0
- 版本：`0.1.0`
- 模型：无（Unicode 文字体系 + 功能词规则，`unicode-script-heuristics-v1`）

## 1. 用途与边界

**做**：语种/混合语识别与置信度；地域分布（仅显式 metadata 字段）；正文/拍摄时间抽取、年季分布、新鲜度指数与过时风险。

**不做**：不加载 fastText/CLD3/方言模型；不从 IP 或文本推断地域；无时间不猜测；不写数据库。

## 2. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_records` | 1000000 | 最多记录数 |
| `as_of` | 批次最大年份 12-31 | 新鲜度基准日 |

## 3. 指标口径

- **语种**：逐字符归类（汉字/假名/谚文/西里尔/阿拉伯/拉丁），按优先级判定；置信度 = 主导语言文字占比；`<0.85` 或第二文字占比 `≥0.15` → `mixed/unknown`；
- **拉丁语系**：英文/德文/法文/西文按功能词命中率选择，命中率 `<0.02` 时默认 `en`；
- **时间**：`capturedAt` > 正文 ISO 日期 > 正文年份；`partitions.dt` 只是接入日期，不参与新鲜度；
- **新鲜度**：近 1 年 0.6 + 近 3 年 0.3 + 3 年以上 0.1；`<0.4` 计为过时风险；均值只对有时间记录计算；
- **地域**：只统计 `metadata.region/country/timezone`，全缺失时 `unavailable` + `GEO_SOURCE_UNAVAILABLE`。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-language-profiling")
print(core.run("operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7", {}, 42,
               "operator/runtime/output/op09-demo")["metrics"]["language"])
PY
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-language-profiling/tests -q
```

## 5. 已知限制

1. 规则分类对短文本、代码/URL 混排、拼音/罗马化中文区分能力有限；
2. 拉丁语系仅区分 en/de/fr/es，其它拉丁语言默认 `en` 并在 `confidence` 上体现；
3. 方言未支持（无模型），需要时另行审批；
4. 样例批次为英文为主，语种分布随真实语料变化。

## 6. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=unicode-script-heuristics-v1`、`treeVersion=null`；
证据目录 `operator/dm-language-profiling/output/evidence/<runId>/`。
