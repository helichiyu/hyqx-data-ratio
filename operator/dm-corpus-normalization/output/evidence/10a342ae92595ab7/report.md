# 工作包回执 · dm-corpus-normalization

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
- 结果目录：`operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7/`
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
| standardized | {"images": 1, "audio": 3, "video": 2, "text": 426} |
| parquet | {"files": 7, "rows": 432, "partitions": 7, "compression": "zstd"} |
| dedup | {"groups": 3, "exactGroups": 3, "nearGroups": 0, "duplicateRecords": 3, "textPairs": 12, "imagePairs": 0, "simhashMaxDistance": 3, "phashMaxDistance": 8} |
| anomalies | {"BLACK_FRAME": 1, "EMPTY_TEXT": 6, "SCANNED_PAGES_NO_OCR": 1} |
| associations | {"fileGroups": 1, "archiveGroups": 0, "directoryGroups": 1, "multiModalGroups": 2, "derivedStreamGroups": 1} |

- 与人工标注比对的准确率/F1：`null`（无人工真值，blockedReason=H-05）。
- 证据全部来自真实样例与真实解码统计；无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-02 树版本（本算子未消费树）、H-03 阈值口径（`dt`/去重/VAD 阈值为联调初值）、H-04 内部样例授权、H-05 人工标注、H-06 模型许可证（本阶段未加载模型）。
- 已知限制：无 OCR/ASR 后端；ffprobe 未安装（用 ffmpeg stderr 解析）；视频转码依赖 ffmpeg libx264。

## 补充
- runId：`10a342ae92595ab7`
- inputFingerprint：`sha256:e99430ecfd9acb33c1d6112bd87fa282a892d74351961b1273fb96d1466036c3`
- paramsHash：`sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
- seed：42
- operatorVersion：0.1.0
- downloadFile：文件与目录（zip）均校验通过
- 上游：{'operatorId': 'dm-multimodal-analysis', 'runId': 'add117fbb422d09f', 'sampleCount': 432, 'successCount': 432, 'failedCount': 0, 'countsMatch': True}

