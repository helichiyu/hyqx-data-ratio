"""生成样例批次清单与混合 zip（S0-0 / S0-5）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/gen_sample_manifest.py

输出：
    docs/算子开发/samples/MANIFEST.json     每个样例的来源、大小、SHA-256、授权状态
    docs/算子开发/samples/mixed/mixed_batch_2026-11-16.zip
                                            四模态混合批次（固定成员顺序与时间戳，可复现）

样例只用于 S0 流程验证，不作为效果验收证据；授权状态待人工确认（H-04）。
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "docs" / "算子开发" / "samples"
MIXED_ZIP = SAMPLES / "mixed" / "mixed_batch_2026-11-16.zip"
MANIFEST = SAMPLES / "MANIFEST.json"
ZIP_DATE = (2026, 11, 16, 0, 0, 0)

ENTRIES = [
    {
        "path": "text/machine_learning.jsonl",
        "modal": "text",
        "format": "jsonl",
        "source": "../后训练系统/commoncrawl_test_dataset/machine_learning.jsonl",
        "sourceUrl": "https://en.wikipedia.org/wiki/Machine_learning",
        "license": "CC BY-SA（维基百科内容，经 Common Crawl 采集）",
        "authorization": "public-license",
        "note": "维基百科单页抓取样本，425 段；来源 SHA-256 见随附 manifest。",
    },
    {
        "path": "image/530384988814704640.jpg",
        "modal": "image",
        "format": "jpg",
        "source": "../平行语料/4个算子源码/图片OCR知识库相似度匹配算子/dataset/530384988814704640.jpg",
        "sourceUrl": None,
        "license": "内部项目素材，授权待确认",
        "authorization": "pending",
        "note": "内部 OCR 算子样例图；仅用于流程验证。",
    },
    {
        "path": "audio/0_0.mp3",
        "modal": "audio",
        "format": "mp3",
        "source": "../平行语料/4个算子源码/音频转文本知识库相似度匹算子/dataset/0_0.mp3",
        "sourceUrl": None,
        "license": "内部项目素材，授权待确认",
        "authorization": "pending",
        "note": "3.38 秒、24 kHz 单声道。",
    },
    {
        "path": "audio/asr_example_hotword.wav",
        "modal": "audio",
        "format": "wav",
        "source": "../平行语料/4个算子源码/音频转文本知识库相似度匹算子/models/paraformer-zh/asr_example_hotword.wav",
        "sourceUrl": None,
        "license": "内部项目素材/FunASR 示例，授权待确认",
        "authorization": "pending",
        "note": "WAV 格式样例，覆盖第二种音频容器。",
    },
    {
        "path": "video/image__00260.mp4",
        "modal": "video",
        "format": "mp4",
        "source": "../平行语料/4个算子源码/视频抽帧OCR知识库相似度匹配算子/dataset/image__00260.mp4",
        "sourceUrl": None,
        "license": "内部项目素材，授权待确认",
        "authorization": "pending",
        "note": "5.04 秒、512x512、24 fps、无音轨。",
    },
    {
        "path": "video/60b5695ab2f0_with_audio.mp4",
        "modal": "video",
        "format": "mp4",
        "source": "../平行语料/4个算子源码/视频抽帧视觉特征匹配算子/dataset/60b5695ab2f0.mp4",
        "sourceUrl": None,
        "license": "内部项目素材，授权待确认",
        "authorization": "pending",
        "note": "10.01 秒、1280x720、24 fps、含 mp3 音轨（音视频拆流样本）。",
    },
    {
        "path": "pdf/noches_blancas_1905.pdf",
        "modal": "image+text",
        "format": "pdf",
        "source": "https://upload.wikimedia.org/wikipedia/commons/7/75/Antonio_de_Zayas_-_Noches_blancas_%281905%29.pdf",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Antonio_de_Zayas_-_Noches_blancas_(1905).pdf",
        "license": "Public domain（Wikimedia Commons，PD-scan）",
        "authorization": "public-domain",
        "note": "326 页扫描书；第 3 页文本层为空、仅有图像，用于 PDF 扫描页 OCR 触发验证。",
    },
]

MIXED_MEMBERS = [
    "text/machine_learning.jsonl",
    "image/530384988814704640.jpg",
    "audio/0_0.mp3",
    "video/60b5695ab2f0_with_audio.mp4",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    records = []
    for entry in ENTRIES:
        path = SAMPLES / entry["path"]
        if not path.is_file():
            print(f"缺少样例：{path}")
            return 1
        records.append(
            {
                **entry,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )

    MIXED_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(MIXED_ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in MIXED_MEMBERS:
            source = SAMPLES / member
            info = zipfile.ZipInfo(member, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())

    manifest = {
        "batchId": "samples-2026-11-16",
        "generatedAt": "2026-11-16",
        "generatedBy": "scripts/gen_sample_manifest.py",
        "purpose": "S0 流程验证；不作为效果验收证据。",
        "authorizationNote": "内部项目素材授权状态待人工确认（H-04）；公有领域素材已标注来源。",
        "entries": records,
        "mixedBatch": {
            "path": MIXED_ZIP.relative_to(SAMPLES).as_posix(),
            "members": MIXED_MEMBERS,
            "bytes": MIXED_ZIP.stat().st_size,
            "sha256": _sha256(MIXED_ZIP),
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"已生成 {MANIFEST.relative_to(ROOT)}（{len(records)} 个样例）")
    for record in records:
        print(f"  {record['path']}  {record['bytes']} B  {record['sha256']}")
    print(f"已生成 {MIXED_ZIP.relative_to(ROOT)}  {manifest['mixedBatch']['bytes']} B  {manifest['mixedBatch']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
