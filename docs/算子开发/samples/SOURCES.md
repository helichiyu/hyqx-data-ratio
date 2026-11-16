# S0 样例批次来源与授权登记

> 批次：`samples-2026-11-16`；生成脚本：`scripts/gen_sample_manifest.py`；机器可读清单：[MANIFEST.json](MANIFEST.json)
> 用途：仅用于 S0 目录骨架、契约测试与四模态/混合文件解析流程验证，**不作为效果验收证据**。
> 授权：内部项目素材的授权状态待人工确认（H-04）；公有领域素材已注明来源与许可证。

## 1. 文件清单

| 路径 | 模态/格式 | 大小（B） | SHA-256 | 来源 | 授权状态 |
| --- | --- | --- | --- | --- | --- |
| `text/machine_learning.jsonl` | 文本 / jsonl | 195,538 | `e9814887434f4f2da1970322978d6dd6f67aedf6d8dd3b476e646a4ccbde67c7` | `../后训练系统/commoncrawl_test_dataset/machine_learning.jsonl`；原文 <https://en.wikipedia.org/wiki/Machine_learning> | CC BY-SA（公开许可） |
| `image/530384988814704640.jpg` | 图像 / jpg | 246,616 | `fb1a93eab3908af56fe7f7fca071e1ad1afa80585ecf0625ff91f05f06d655fc` | `../平行语料/4个算子源码/图片OCR知识库相似度匹配算子/dataset/` | 内部素材，待确认 |
| `audio/0_0.mp3` | 音频 / mp3 | 27,072 | `180961720fdf7d1c4d49ec5f23c0fdabb6058b72396b431d5eb70db788112c77` | `../平行语料/4个算子源码/音频转文本知识库相似度匹算子/dataset/` | 内部素材，待确认 |
| `audio/asr_example_hotword.wav` | 音频 / wav | 253,642 | `51792bc95be33075c1a8abb9afb76ad9f72943e84cd723cc8825b2678799b004` | `../平行语料/4个算子源码/音频转文本知识库相似度匹算子/models/paraformer-zh/` | 内部素材，待确认 |
| `video/image__00260.mp4` | 视频 / mp4（无音轨） | 340,281 | `9f2797708457233f57014ced095faf7cac0660f05a7cc6c6fd4a98473ef39b43` | `../平行语料/4个算子源码/视频抽帧OCR知识库相似度匹配算子/dataset/` | 内部素材，待确认 |
| `video/60b5695ab2f0_with_audio.mp4` | 视频 / mp4（含 mp3 音轨） | 831,693 | `03bdfd257f273e87f6e3c9b9055c27d265aa1d5fd72b2c3d71c413d7ed7a966e` | `../平行语料/4个算子源码/视频抽帧视觉特征匹配算子/dataset/60b5695ab2f0.mp4` | 内部素材，待确认 |
| `pdf/noches_blancas_1905.pdf` | PDF 扫描书（326 页） | 4,466,151 | `e6635e182b13c6eeb1ea1198ffc32a802a2e4ada0bd15d8d8221ab0b2db8c8bc` | <https://commons.wikimedia.org/wiki/File:Antonio_de_Zayas_-_Noches_blancas_(1905).pdf> | Public domain（PD-scan） |

## 2. 混合批次

| 文件 | 成员 | 大小（B） | SHA-256 |
| --- | --- | --- | --- |
| `mixed/mixed_batch_2026-11-16.zip` | 文本 + 图像 + 音频 + 含音轨视频 | 1,120,290 | `7f826ceed2bef81e6d7438bdbc30f72622eaa2c14d94310867ebacb8ca6455e3` |

混合 zip 使用固定成员顺序与固定时间戳（2026-11-16 00:00:00）生成，同一脚本重跑哈希一致。

## 3. 覆盖度与人工核对说明

| 要求 | 覆盖情况 |
| --- | --- |
| 四模态 | 文本（jsonl）、图像（jpg）、音频（mp3/wav）、视频（mp4 有/无音轨）各至少 1 个 |
| 同一模态多格式 | 音频 mp3 + wav；视频有音轨/无音轨 |
| PDF 扫描页 | 第 3 页 `get_text()` 为空且含 2 张图像，可触发 OCR 分支 |
| 混合文件 | `mixed_batch_2026-11-16.zip` 内含四模态，可验证归档展开与 zip-slip 防护 |
| 视频拆流 | `60b5695ab2f0_with_audio.mp4` 含 `mp4a` 音轨，可验证音轨转音频分支 |

PDF 扫描页核对命令（PyMuPDF 1.28.2）：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import pymupdf
doc = pymupdf.open("docs/算子开发/samples/pdf/noches_blancas_1905.pdf")
print(doc.page_count, len(doc[2].get_text().strip()), len(doc[2].get_images(full=True)))
# 326 0 2
PY
```

## 4. 授权与再分发约束

1. 内部项目素材（图像/音频/视频）未取得书面授权前不得对外分发；入仓仅为 S0 开发与联调，人工确认后按 H-04 结论处理。
2. 维基百科文本遵循 CC BY-SA，使用时保留来源与许可信息。
3. 《Noches blancas (1905)》为公有领域扫描件，保留 Wikimedia Commons 来源链接。
4. 样例不得替代真实批次做效果验收；效果类指标缺失时写 `null` + `blockedReason`。
