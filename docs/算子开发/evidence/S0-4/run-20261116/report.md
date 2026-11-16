# 工作包回执 · S0-4 测试与证据基座

## 状态
完成（本机）

## 完成项
- 根 tests/：契约 22 次参数化、信封、路径闸门、幂等
- 模板 tests/：conftest + contract_smoke
- init_run_evidence.py 一次生成 9 件证据文件
- pytest 58 项：57 passed / 1 skipped（Windows 符号链接权限）

## 运行命令
```bash
python -m pytest tests operator/_template/tests
python scripts/init_run_evidence.py --output-dir docs/算子开发/evidence/S0-4/run-20261116
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-4/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| collected | 58 | — | 本机实测 | metrics.json |
| passed | 57 | — | 本机实测 | metrics.json |
| skipped | 1 | — | 本机实测 | metrics.json |
| evidenceFiles | 9 | — | 本机实测 | metrics.json |

## 未决问题
- 符号链接用例在无权限环境跳过，不影响契约结论

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
