# OP-12 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl` + 标准媒体）；只处理 `modal=image/video`：

| 路径 | 用途 |
| --- | --- |
| `standard/images/<record_id>.webp` | 图像熵/清晰度/亮度/色彩/主色 |
| `standard/video/<record_id>.mp4` | 镜头切换、平均镜头时长、光流、关键帧时间 |

## 2. 输出

`result.jsonl`（图像）：

```json
{
  "record_id": "r_…",
  "modal": "image",
  "width": 1280,
  "height": 720,
  "entropy": 7.12,
  "sharpnessLaplacian": 642.3,
  "brightnessMean": 0.51,
  "contrastStd": 0.21,
  "colorfulness": 34.2,
  "dominantColors": [{"hex": "#a1b2c3", "share": 0.31}],
  "scene": {"status": "unavailable", "reasonCode": "SCENE_MODEL_UNAVAILABLE"},
  "objects": {"status": "unavailable", "reasonCode": "OBJECT_MODEL_UNAVAILABLE"}
}
```

`result.jsonl`（视频）：

```json
{
  "record_id": "r_…",
  "modal": "video",
  "fps": 25.0,
  "frameCount": 750,
  "durationSec": 30.0,
  "sampledFrames": 60,
  "shots": 4,
  "cutTimesSec": [7.2, 15.0, 22.4],
  "meanShotDurationSec": 7.5,
  "flowMeanMagnitude": 1.23,
  "dynamicFrameRatio": 0.65,
  "staticFrameRatio": 0.35,
  "actionCoverage": {"status": "unavailable", "reasonCode": "ACTION_MODEL_UNAVAILABLE"},
  "audioVisualBleu": {"status": "unavailable", "reasonCode": "REFERENCE_TRANSCRIPT_REQUIRED"}
}
```

失败 `reasonCode`：`STANDARD_MEDIA_MISSING`、`DECODE_FAILED`、`RECORD_JSON_INVALID`。

辅助产物：`failures.jsonl`、`input_manifest.json`、`manifest.json`、`summary.json`。

## 3. 样例

`dataset/sample/records_demo.jsonl` 只有记录；需要对应的标准媒体文件（可由测试生成）。
真实样例可直接运行 OP-02 证据目录：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-visual-analysis")
print(core.run("operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7", {}, 42,
               "operator/runtime/output/op12-demo")["metrics"])
PY
```
