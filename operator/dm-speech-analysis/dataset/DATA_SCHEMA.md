# OP-11 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl` + `standard/audio/<record_id>.wav`）；只处理 `modal=audio`：

| 字段/参数 | 用途 |
| --- | --- |
| `standard/audio/<rid>.wav` | 转写与声学分析（16 kHz mono） |
| `params.reference_path` | 可选参考转写 jsonl（`{"record_id","text"}`，须在 `INPUT_DIR`/`OUTPUT_DIR` 内） |
| `metadata.durationSec` | 参考时长（可选） |

## 2. 输出

`result.jsonl`：

```json
{
  "record_id": "r_…",
  "transcription": "……",
  "chars": 19,
  "asrSegments": 1,
  "durationSec": 3.38,
  "speechRatio": 0.777,
  "silenceRatio": 0.223,
  "speechSec": 2.63,
  "pauses": 2,
  "pauseSec": 0.75,
  "speechRateCharsPerSec": 7.22,
  "pitchMeanHz": 210.4,
  "pitchMedianHz": 205.0,
  "voicedRatio": 0.64,
  "accent": {"status": "unavailable", "reasonCode": "ACCENT_MODEL_UNAVAILABLE"},
  "wer": null,
  "cer": null,
  "werReasonCode": "REFERENCE_TEXT_REQUIRED",
  "lowQuality": false
}
```

- `wer/cer` 仅在有参考文本时计算；无参考为 `null` + `REFERENCE_TEXT_REQUIRED`；
- 低质量原因 ∈ `ASR_EMPTY`、`NO_SPEECH`、`WER_OVER_THRESHOLD`（>0.2）、`CER_OVER_THRESHOLD`（>0.3）；
- 失败 `reasonCode` ∈ `STANDARD_MEDIA_MISSING`、`ASR_FAILED`、`DECODE_FAILED`、`RECORD_JSON_INVALID`。

辅助产物：`low_quality.jsonl`、`failures.jsonl`、`input_manifest.json`、`manifest.json`、`summary.json`。

## 3. 样例

`dataset/sample/records_demo.jsonl` 只有记录；运行需要 `standard/audio/r_speech_demo_001.wav`
（16 kHz mono）。可用测试中的 `_wav` 生成方式：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference, numpy as np, soundfile
from pathlib import Path
core = inference._import_operator_core("dm-speech-analysis")
base = Path("operator/runtime/output/op11-demo")
(base / "standard/audio").mkdir(parents=True, exist_ok=True)
rate = 16000
tone = (0.4 * np.sin(2*np.pi*220*np.arange(3*rate)/rate)).astype("float32")
soundfile.write(str(base / "standard/audio/r_speech_demo_001.wav"), tone, rate)
import shutil; shutil.copy("operator/dm-speech-analysis/dataset/sample/records_demo.jsonl", base / "records.jsonl")
print(core.run(str(base), {}, 42, str(base / "out"))["metrics"])
PY
```
