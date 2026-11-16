# 工作包回执 · dm-multimodal-analysis

## 状态
完成（本机真实样例链路）；效果验收待人工真值（H-05），不阻塞后续阶段。

## 变更文件
- 新增：见 git 提交 `feat(s1)` 的 diff。
- 修改：`operator/map.json`、`docs/算子开发/registry.json`、任务书第 10 节。
- 删除：无。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s1_chain.py --batch "docs/算子开发/samples/mixed/full_batch_2026-11-16.zip"
```

## 证据路径
- 结果目录：`operator/dm-multimodal-analysis/output/evidence/add117fbb422d09f/`
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 432 |
| successCount | 432 |
| failedCount | 0 |
| modalCounts | {"audio": 3, "image": 1, "text": 426, "video": 2} |
| failureRate | 0.0 |
| text | {"records": 426, "emptyTextRecords": 0, "emptyTextRate": 0.0, "mojibakeWarnRecords": 0, "mojibakeRate": 0.0, "decodeFailureRecords": 0, "mojibakeWarnThreshold": 0.02} |
| pdf | {"documents": 1, "pages": 326, "scannedPages": 106, "emptyPages": 86, "ocrStatus": "unavailable", "ocrAttempted": 0, "ocrSucceeded": 0, "note": "未接入 OCR 后端；扫描页只统计不伪造文本。"} |
| media | {"images": 1, "audioFiles": 3, "silentAudio": 0, "videoFiles": 2, "videosWithAudio": 1, "keyframes": 49} |
| detection | {"lowConfidenceFiles": 0, "conflictFiles": 0, "minConfidence": 0.6, "byModal": {"audio": 2, "image": 1, "text": 2, "video": 2}} |

- 与人工标注比对的准确率/F1：`null`（无人工真值，blockedReason=H-05）。
- 证据全部来自真实样例与真实解码统计；无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-02 树版本（本算子未消费树）、H-03 阈值口径（`dt`/去重/VAD 阈值为联调初值）、H-04 内部样例授权、H-05 人工标注、H-06 模型许可证（本阶段未加载模型）。
- 已知限制：无 OCR/ASR 后端；ffprobe 未安装（用 ffmpeg stderr 解析）；视频转码依赖 ffmpeg libx264。

## 补充
- runId：`add117fbb422d09f`
- inputFingerprint：`sha256:26f26bf9a5105933444a501d6b6dcf846477fd6971be9cdb97e4fd03a6ff6d68`
- paramsHash：`sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
- seed：42
- operatorVersion：0.1.0
- downloadFile：文件与目录（zip）均校验通过
- 上游：—

