# 工作包回执 · S0-8 部署编排

## 状态
完成（本机）；容器内验证待人工（H-01）

## 完成项
- docker-compose.yml：单服务 op-data-mixing、17025、输入输出卷、健康检查
- docker compose config 解析通过，build context=operator/
- 本机 uvicorn + 22 个 healthz 通过

## 运行命令
```bash
docker compose -f operator/docker-compose.yml config
python -m uvicorn inference:app --host 127.0.0.1 --port 17025
python scripts/check_healthz.py --base-url http://127.0.0.1:17025
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-8/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| services | 1 | — | 本机实测 | metrics.json |
| port | 17025 | — | 本机实测 | metrics.json |
| healthzReady | 22 | — | 本机实测 | metrics.json |

## 未决问题
- Docker 守护进程未启动，容器内 22 healthz 待人工执行（H-01）

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
