"""元数据宽表、字段缺失清单、异常检测与跨模态关联。"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .writer import mean_brightness

INDEX_SCHEMA = pa.schema(
    [
        ("record_id", pa.string()),
        ("modal", pa.string()),
        ("source", pa.string()),
        ("dt", pa.string()),
        ("format", pa.string()),
        ("size_bytes", pa.int64()),
        ("md5", pa.string()),
        ("sha256", pa.string()),
        ("simhash", pa.string()),
        ("phash", pa.string()),
        ("text_chars", pa.int64()),
        ("empty_text", pa.bool_()),
        ("decodable", pa.bool_()),
        ("completeness", pa.float64()),
        ("standard_path", pa.string()),
        ("duplicate_of", pa.string()),
        ("file", pa.string()),
    ]
)

REQUIRED_METADATA = ("format", "sizeBytes", "sha256")
REQUIRED_QUALITY = ("decodable", "completeness")


def build_metadata_rows(
    records: list[dict[str, Any]],
    standard_paths: dict[str, str],
    duplicate_of: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        metadata = record.get("metadata") or {}
        quality = record.get("quality") or {}
        hashes = record.get("hashes") or {}
        extra = metadata.get("extra") or {}
        rows.append(
            {
                "record_id": record["record_id"],
                "modal": record["modal"],
                "source": record["source"],
                "dt": (record.get("partitions") or {}).get("dt"),
                "format": metadata.get("format"),
                "size_bytes": int(metadata.get("sizeBytes") or 0),
                "md5": hashes.get("md5"),
                "sha256": hashes.get("sha256"),
                "simhash": hashes.get("simhash"),
                "phash": hashes.get("phash"),
                "text_chars": len(record.get("text") or ""),
                "empty_text": bool(quality.get("emptyText")),
                "decodable": bool(quality.get("decodable")),
                "completeness": float(quality.get("completeness") or 0.0),
                "standard_path": standard_paths.get(record["record_id"]),
                "duplicate_of": duplicate_of.get(record["record_id"]),
                "file": extra.get("file"),
            }
        )
    rows.sort(key=lambda item: item["record_id"])
    return rows


def write_index(rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=INDEX_SCHEMA)
    pq.write_table(
        table,
        out_dir / "metadata.parquet",
        compression="zstd",
        row_group_size=65536,
        use_dictionary=True,
        write_statistics=True,
    )
    return {
        "rows": table.num_rows,
        "parquet": (out_dir / "metadata.parquet").as_posix(),
    }


def missing_fields(records: list[dict[str, Any]]) -> dict[str, Any]:
    missing_metadata: Counter[str] = Counter()
    missing_quality: Counter[str] = Counter()
    missing_hashes: Counter[str] = Counter()
    for record in records:
        metadata = record.get("metadata") or {}
        quality = record.get("quality") or {}
        hashes = record.get("hashes") or {}
        for key in REQUIRED_METADATA:
            if metadata.get(key) in (None, ""):
                missing_metadata[key] += 1
        for key in REQUIRED_QUALITY:
            if quality.get(key) is None:
                missing_quality[key] += 1
        for key in ("md5", "sha256"):
            if hashes.get(key) in (None, ""):
                missing_hashes[key] += 1
    return {
        "metadata": dict(sorted(missing_metadata.items())),
        "quality": dict(sorted(missing_quality.items())),
        "hashes": dict(sorted(missing_hashes.items())),
    }


def build_associations(
    records: list[dict[str, Any]], batch_label: str | None = None
) -> list[dict[str, Any]]:
    """三级关联：文件级（含视频拆出的音轨）、归档级、目录/批次级。

    HTTP 层会先把 zip 解压再交给算子，此时记录里没有 ``.zip/`` 前缀，因此再加一层
    「同一目录/批次」聚合，用于表达混合批次的多模态构成。
    """

    base_keys: dict[str, str] = {}
    base_files: dict[str, str] = {}
    for record in records:
        extra = (record.get("metadata") or {}).get("extra") or {}
        if extra.get("derivedFrom"):
            continue
        base_keys[record["record_id"]] = _base_key(extra.get("file"))
        if isinstance(extra.get("file"), str):
            base_files[record["record_id"]] = extra["file"]

    file_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    archive_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    directory_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        extra = (record.get("metadata") or {}).get("extra") or {}
        derived = extra.get("derivedFrom")
        key = base_keys.get(derived) if derived else base_keys.get(record["record_id"])
        if key is None:
            key = _base_key(extra.get("file"))
        file_groups[key].append(record)
        relative = extra.get("file")
        if derived and derived in base_files:
            relative = base_files[derived]
        if isinstance(relative, str) and ".zip/" in relative:
            archive_groups["archive:" + relative.split(".zip/", 1)[0] + ".zip"].append(record)
            directory_key = f"batch:{batch_label or 'archive'}"
        elif isinstance(relative, str):
            parent = str(Path(relative).parent.as_posix())
            directory_key = f"dir:{parent}" if parent not in ("", ".") else f"batch:{batch_label or '.'}"
        else:
            directory_key = f"batch:{batch_label or 'unknown'}"
        directory_groups[directory_key].append(record)

    associations: list[dict[str, Any]] = []
    for key, members in sorted(file_groups.items()):
        modalities = sorted({member["modal"] for member in members})
        has_derived = any(
            (member.get("metadata") or {}).get("extra", {}).get("derivedFrom")
            for member in members
        )
        if len(modalities) < 2 and not has_derived:
            continue
        associations.append(
            {
                "level": "file",
                "key": key,
                "count": len(members),
                "modalities": modalities,
                "recordIds": sorted(member["record_id"] for member in members),
                "hasDerivedStream": has_derived,
            }
        )
    for level, groups in (("archive", archive_groups), ("directory", directory_groups)):
        for key, members in sorted(groups.items()):
            modalities = sorted({member["modal"] for member in members})
            if len(modalities) < 2:
                continue
            modal_counts = Counter(member["modal"] for member in members)
            associations.append(
                {
                    "level": level,
                    "key": key,
                    "count": len(members),
                    "modalities": modalities,
                    "modalCounts": dict(sorted(modal_counts.items())),
                    "sampleRecordIds": sorted(member["record_id"] for member in members)[:20],
                }
            )
    return associations


def detect_anomalies(
    record: dict[str, Any],
    *,
    records_root: Path,
    cfg: dict[str, Any],
    standardization_notes: list[str],
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    record_id = record["record_id"]
    quality = record.get("quality") or {}
    metadata = record.get("metadata") or {}
    extra = metadata.get("extra") or {}
    anomaly_cfg = cfg["anomaly"]

    if quality.get("emptyText"):
        anomalies.append(
            {"recordId": record_id, "type": "EMPTY_TEXT", "detail": "文本为空或仅空白"}
        )
    if quality.get("decodeError"):
        anomalies.append(
            {
                "recordId": record_id,
                "type": "DECODE_ERROR",
                "detail": str(quality["decodeError"]),
            }
        )
    pdf = extra.get("pdf") or {}
    if pdf.get("ocrStatus") == "unavailable":
        anomalies.append(
            {
                "recordId": record_id,
                "type": "SCANNED_PAGES_NO_OCR",
                "detail": f"扫描页 {len(pdf.get('scannedPages') or [])} 个，OCR 后端不可用",
            }
        )
    if record["modal"] == "audio":
        vad = extra.get("vad") or {}
        if float(vad.get("silenceRatio") or 0.0) >= float(anomaly_cfg["silentRatio"]):
            anomalies.append(
                {
                    "recordId": record_id,
                    "type": "SILENT_AUDIO",
                    "detail": f"静音占比 {vad.get('silenceRatio')}",
                }
            )
    brightness_threshold = float(anomaly_cfg["blackFrameMeanBrightness"])
    if record["modal"] == "image":
        source = _source_path(extra, records_root)
        if source:
            brightness = mean_brightness(source)
            if brightness is not None and brightness < brightness_threshold:
                anomalies.append(
                    {
                        "recordId": record_id,
                        "type": "BLACK_FRAME",
                        "detail": f"平均灰度 {brightness} < {brightness_threshold}",
                    }
                )
    if record["modal"] == "video":
        for frame in extra.get("keyframes") or []:
            relative = frame.get("path")
            if not relative:
                continue
            frame_path = records_root / relative
            brightness = mean_brightness(frame_path)
            if brightness is not None and brightness < brightness_threshold:
                anomalies.append(
                    {
                        "recordId": record_id,
                        "type": "BLACK_FRAME",
                        "detail": f"关键帧 {frame.get('index')} 平均灰度 {brightness}",
                        "evidence": relative,
                    }
                )
                break
    if any(note in {"VIDEO_COPIED_ORIGINAL", "VIDEO_TRANSCODE_FAILED"} for note in standardization_notes):
        anomalies.append(
            {
                "recordId": record_id,
                "type": "STANDARDIZATION_FALLBACK",
                "detail": "; ".join(standardization_notes),
            }
        )
    return anomalies


def partition_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    partitions: dict[str, dict[str, int]] = defaultdict(
        lambda: {"records": 0, "bytes": 0}
    )
    for record in records:
        parts = record.get("partitions") or {}
        key = f"modal={parts.get('modal')}/source={parts.get('source')}/dt={parts.get('dt')}"
        partitions[key]["records"] += 1
        partitions[key]["bytes"] += int((record.get("metadata") or {}).get("sizeBytes") or 0)
    return dict(sorted(partitions.items()))


def _base_key(relative: Any) -> str:
    if not isinstance(relative, str) or not relative:
        return "file:unknown"
    if ".zip/" in relative:
        archive = relative.split(".zip/", 1)[0] + ".zip"
        return f"archive:{archive}"
    return f"file:{relative}"


def _source_path(extra: dict[str, Any], records_root: Path) -> Path | None:
    source = extra.get("sourcePath")
    if isinstance(source, str) and source:
        candidate = Path(source)
        if candidate.is_file():
            return candidate
    relative = extra.get("file")
    if isinstance(relative, str) and relative:
        candidate = records_root / relative
        if candidate.is_file():
            return candidate
    return None
