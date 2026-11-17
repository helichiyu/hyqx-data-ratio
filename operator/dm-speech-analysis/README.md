# OP-11 语音质量与声学属性（`dm-speech-analysis`）

- 语义编码：`corpus_profile_speech_quality_v1`
- 阶段/优先级：S3 / P1
- 版本：`0.1.0`
- 模型：FunASR `paraformer-zh`（Apache-2.0，CPU）

## 1. 用途与边界

**做**：ASR 转写、WER/CER（需参考文本）、语速、基频、停顿/静音占比、低质量语音清单。

**不做**：无参考文本时不计算 WER，只给转写与声学统计；口音分类无模型，标 `unavailable`；不做降噪/增强。

## 2. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `max_records` | 100000 | 最多记录数 |
| `reference_path` | 无 | 参考转写 jsonl（`record_id`/`text`），须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |

## 3. 指标口径

- **WER**：拉丁按词、中文按字符，编辑距离 / 参考长度；**CER**：去标点空白后按字符；
- **VAD**：30 ms 帧 RMS，低于 P20 视为静音；`speechRatio = 有效语音帧 / 总帧`；
- **语速** = 转写字符数 / 有效语音秒；**停顿** = 连续静音 ≥0.1 s 的段数；
- **基频**：librosa pyin（60–400 Hz），仅统计有声帧；正弦测试音可能出现倍频误差；
- **低质量**：`NO_SPEECH`（speechRatio<0.1）、`ASR_EMPTY`、`WER>0.2`、`CER>0.3`。

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-speech-analysis")
print(core.run("operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7", {}, 42,
               "operator/runtime/output/op11-demo")["metrics"])
PY
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-speech-analysis/tests -q
```

## 5. 已知限制

1. ASR 为神经模型，`deterministic=false`（同机稳定，跨硬件可能有差异）；
2. 无参考文本时不产出识别错误率，仅转写与声学统计；
3. 口音/方言无模型，标 `unavailable`；
4. 长音频 >60 s 用 ffmpeg 分片，>30 min 需平台分片（返回 `ASR_FAILED`）。

## 6. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=paraformer-zh`、`treeVersion=null`；
证据目录 `operator/dm-speech-analysis/output/evidence/<runId>/`。
