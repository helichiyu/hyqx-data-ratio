# 工作包回执 · S0-2 服务协议与错误码

## 状态
完成（本机）

## 完成项
- 五端点契约、统一信封、HTTP 码、reasonCode、路径闸门、10 MiB/超时/幂等写入契约文档
- 统一 400/404/405/413/503/500 响应；未知路由与参数校验也套信封
- 契约测试覆盖成功、业务失败、参数错误、越界、zip-slip、幂等

## 运行命令
```bash
python -m pytest tests/test_contract_all.py tests/test_envelope.py tests/test_path_gate.py -q
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-2/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| contractCases | 22 | — | 本机实测 | metrics.json |
| envelopeCases | 14 | — | 本机实测 | metrics.json |
| pathGateCases | 16 | — | 本机实测 | metrics.json |

## 未决问题
- D-01～D-10 差异项待人工确认（构建上下文/目录层级/权重根/operatorId 语义等）

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
