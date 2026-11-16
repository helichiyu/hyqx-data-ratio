# 工作包回执 · S0-1 算子目录骨架与注册表

## 状态
完成（本机）

## 完成项
- 生成 22 个算子包骨架（core.run + configs + utils），目录=包名，不嵌套
- 写 map.json 22 条；根 inference.py 单入口五端点 + /health
- Dockerfile / .dockerignore / docker-compose.yml / requirements.txt
- 本机 uvicorn 启动，22/22 healthz code=0

## 运行命令
```bash
python scripts/scaffold_operators.py
python -m pytest tests operator/_template/tests -q
python -m uvicorn inference:app --host 127.0.0.1 --port 17025
python scripts/check_healthz.py --base-url http://127.0.0.1:17025
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-1/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| operators | 22 | — | 本机实测 | metrics.json |
| healthzReady | 22 | — | 本机实测 | metrics.json |
| pytestPassed | 57 | — | 本机实测 | metrics.json |
| pytestSkipped | 1 | — | 本机实测 | metrics.json |

## 未决问题
- Docker 构建待人工执行（H-01）；本机等价验证已通过

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
