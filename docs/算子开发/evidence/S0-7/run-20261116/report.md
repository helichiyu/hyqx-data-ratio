# 工作包回执 · S0-7 安全与合规基线

## 状态
完成（文档）；授权/许可证待人工审批

## 完成项
- 权重/密钥/语料/样例授权规则
- 许可证清单：基础镜像、系统包、Python 依赖、样例、模型预登记
- .gitignore 排除权重、dist、runtime、.env、缓存
- 仓库无权重文件、无 .env

## 运行命令
```bash
find operator/weights -type f ! -name '.gitkeep' ! -name 'SHA256SUMS'
git status --short
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-7/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| weightFiles | 0 | — | 本机实测 | metrics.json |
| envFiles | 0 | — | 本机实测 | metrics.json |
| licenseDocs | 2 | — | 本机实测 | metrics.json |
| pendingItems | 5 | — | 本机实测 | metrics.json |

## 未决问题
- 内部样例授权（H-04）、模型许可证（Q-07）待审批
- Debian ffmpeg GPL 组件待复核

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
