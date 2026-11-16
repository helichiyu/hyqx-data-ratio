# 工作包回执 · S0-5 基线数据与配置

## 状态
完成（本机）；树版本/阈值待业务确认（H-02/H-03）

## 完成项
- 解析分类体系 1013 xlsx：内容 423 节点、领域 272（16 行业根）、能力 99
- 六类来源映射与原型三类展示层映射
- 阈值口径表 26 项，逐项标来源与状态
- 四模态样例批次与混合 zip

## 运行命令
```bash
python scripts/gen_tree_snapshot.py
python scripts/gen_sample_manifest.py
```

## 证据路径
- 结果目录：E:/HYQX/数据配比/docs/算子开发/evidence/S0-5/run-20261116
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 口径 | 证据 |
| --- | --- | --- | --- | --- |
| contentNodes | 423 | — | 本机实测 | metrics.json |
| domainNodes | 272 | — | 本机实测 | metrics.json |
| abilityNodes | 99 | — | 本机实测 | metrics.json |
| treeVersion | taxonomy-1013-pending | — | 本机实测 | metrics.json |
| thresholds | 23 | — | 本机实测 | metrics.json |

## 未决问题
- treeVersion=taxonomy-1013-pending，待 Q-01
- 阈值待 Q-03 书面确认

## 下一步
按任务书 10.3 进入下一工作包；待人工项见任务书 10.8。
