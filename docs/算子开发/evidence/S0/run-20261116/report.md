# 工作包回执 · S0 S0 阶段门禁自检

## 状态
本机自测通过，状态待评审

## 完成项
- 9 个工作包全部完成本机可执行部分
- pytest 57 passed / 1 skipped；Schema 正反样例通过；registry 22 行一致
- uvicorn 22/22 healthz；压缩包清单干净并可解压核对
- Docker 构建/容器内探针/压缩包独立构建待人工执行

## 运行命令
```bash
python -m pytest tests operator/_template/tests
python scripts/validate_schemas.py
python scripts/check_registry.py
python scripts/check_healthz.py --base-url http://127.0.0.1:17025
bash scripts/package_docker_bundle.sh --version 0.1.0
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| workPackages | 9 | — | 本机实测 | metrics.json |
| pytestPassed | 57 | — | 本机实测 | metrics.json |
| pytestSkipped | 1 | — | 本机实测 | metrics.json |
| healthzReady | 22 | — | 本机实测 | metrics.json |
| registryRows | 22 | — | 本机实测 | metrics.json |
| bundleCoreFiles | 22 | — | 本机实测 | metrics.json |

## 未决问题
- H-01 Docker 三项待人工
- H-02/H-03/H-04 业务确认待人工

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
