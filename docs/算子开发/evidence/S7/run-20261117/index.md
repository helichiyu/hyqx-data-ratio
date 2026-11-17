# S7 全链路验收证据索引

> 日期：2026-11-17
> 结论：**本机等价验证通过，状态「待评审」**；Docker/容器探针/平台联调与业务口径待人工门禁。

## 1. 证据文件

| 文件 | 内容 |
| --- | --- |
| `verification.json` | 22 算子证据/runId/版本/产物哈希校验、P0/全量链路、healthz、grep、压缩包 |
| `healthz.json` | 本机 uvicorn 下 22 个 `/{operatorId}/healthz` 与聚合 `/health` 明细 |
| `grep.txt` | production 代码反伪造检索结果（0 命中） |
| `package.txt` | 最小压缩包生成日志、文件数、SHA-256、forbidden 清单（空） |
| [`../../验收报告.md`](../../验收报告.md) | S7 验收报告（S7-A/S7-B、遗留、人工门禁） |
| [`../../FGW追溯矩阵.md`](../../FGW追溯矩阵.md) | FGW 12.x/13.x → 算子 → 证据路径 |

## 2. 关键结果

| 项 | 结果 |
| --- | --- |
| 算子证据 | 22/22 存在；manifest/metrics/summary/result 齐全；artifacts.sha256 校验通过 |
| P0 最小链路 | 11/11 算子证据齐全，`p0ChainComplete=true` |
| 全量链路 | 22/22，`fullChainComplete=true` |
| 上下游消费 | OP-15→17→18→19、OP-02/03→20、OP-08～19→22 全部 `true` |
| healthz | 22/22 通过，聚合 `/health` 通过 |
| 反伪造 grep | 0 命中 |
| 最小压缩包 | 319 文件；无 tests/dataset/output/docs/README；SHA-256 见 `package.txt` |
| 遗留警告 | 13 项旧 `manifest.runId` 口径、57 项旧 metrics 版本字段（见 `verification.json.warnings`） |

## 3. 复算命令

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator
"D:/anaconda3/envs/use/python.exe" scripts/check_registry.py
"D:/anaconda3/envs/use/python.exe" scripts/verify_s7.py
bash scripts/package_docker_bundle.sh
docker build -t op-data-mixing:0.1.0 .   # 待 H-01
```

## 4. 人工门禁

- H-01：Docker 构建、容器内 22 healthz、压缩包空目录独立 build；
- 平台联调：服务 `op-data-mixing`、端口 17025、X-Token、10 MiB、超时、幂等、断点续跑；
- 业务口径：H-02 树版本、H-03 阈值、H-05 真值/专家、H-08 契约、H-11 本体/KG、Q-07 Neo4j/FAISS、Q-08 合规资源。

> 人工门禁未完成前不标「已验收」。
