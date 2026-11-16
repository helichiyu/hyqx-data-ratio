# 工作包回执 · S0-3 数据契约与 JSON Schema

## 状态
完成（本机）

## 完成项
- record/manifest/result 三份 Draft 2020-12 Schema
- 每份 1 个正样例 + 4～5 个反样例
- 正样例全部通过、反样例全部被拒

## 运行命令
```bash
python scripts/validate_schemas.py
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-3/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| schemas | 3 | — | 本机实测 | metrics.json |
| validSamples | 3 | — | 本机实测 | metrics.json |
| invalidSamples | 13 | — | 本机实测 | metrics.json |

## 未决问题
- 无

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
