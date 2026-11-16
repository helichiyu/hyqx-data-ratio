# 工作包回执 · dm-label-governance

## 状态
完成（本机真实产物）

## 变更文件
- 见 git 提交 `feat(s2)` 的 diff。

## 运行命令
```bash
python - <<PY
import sys; sys.path.insert(0,"operator"); import inference
core=inference._import_operator_core("dm-label-governance")
core.run("operator/runtime/output/op05-run", {}, 42, "operator/runtime/output/op07-run")
PY
```

## 证据路径
- 结果目录：`operator/dm-label-governance/output/evidence/522eb4f27eee2c3b/`
- 指标文件：`metrics.json`
- 日志：`logs/service.log`（直接调用 core.run，无 HTTP 服务日志）
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| modelVersion | null |
| treeVersion | taxonomy-1013-pending |
| illegalLabels | 0 |
| legalRate | 1.0 |
| reviewMetrics | {"accuracy": null, "adoptionRate": null, "alpha": null, "blockedReason": "REVIEW_RECORDS_REQUIRED", "kappa": null, "modificationRate": null, "note": "无人工审核记录（H-05）；不填 Kappa/准确率/采纳率。"} |
| unclassifiedByReason | {"UNCLASSIFIED_LOW_CONFIDENCE": 35, "UNCLASSIFIED_LOW_SIMILARITY": 4, "UNCLASSIFIED_NO_SPEECH": 1, "UNCLASSIFIED_SMALL_MARGIN": 114} |

- 效果指标（与人工标注比对）：`null`，`blockedReason=MATCHING_ANNOTATION_REQUIRED`（H-05）。
- 证据来自真实模型/真实样例；无随机数/常量伪造。

## 未决问题
- 阻塞项：无（本机链路）。
- 需人工确认：H-02 树版本、H-05 人工标注、H-06 模型许可与算力、Docker/容器探针（H-01）。
- 已知限制：纯规则治理；无人工审核记录时 Kappa/准确率/采纳率为 null。

## 下一步
人工标注到位后补准确率/Wilson/混淆矩阵；阶段门禁复核。
