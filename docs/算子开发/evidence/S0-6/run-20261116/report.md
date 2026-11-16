# 工作包回执 · S0-6 算子台账

## 状态
完成（本机）

## 完成项
- registry.json 22 行，含状态机字段；publishId=null
- check_registry 比对 xlsx/map/registry 逐行一致，依赖无环
- 状态均为「未开始」，AI 不标已验收

## 运行命令
```bash
python scripts/gen_registry.py
python scripts/check_registry.py
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-6/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| rows | 22 | — | 本机实测 | metrics.json |
| publishIdNonNull | 0 | — | 本机实测 | metrics.json |
| cycles | 0 | — | 本机实测 | metrics.json |

## 未决问题
- 无

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
