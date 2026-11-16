"""OP-01 纯函数单测：模态判定、编码、解析、哈希、来源、分区。"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from op01_env import CORE


def test_detect_extension_and_magic(tmp_path):
    png = tmp_path / "x.png"
    Image.new("RGB", (8, 8), "red").save(png)
    result = CORE.detect.detect(png)
    assert result["modal"] == "image"
    assert result["confidence"] == 0.99
    assert any(item["rule"] == "magic" for item in result["evidence"])

    renamed = tmp_path / "x.bin"
    renamed.write_bytes(png.read_bytes())
    result = CORE.detect.detect(renamed)
    assert result["modal"] == "image"
    assert result["confidence"] == 0.9


def test_detect_conflict_prefers_magic(tmp_path):
    png = tmp_path / "x.png"
    Image.new("RGB", (8, 8), "green").save(png)
    fake = tmp_path / "x.wav"
    fake.write_bytes(png.read_bytes())
    result = CORE.detect.detect(fake)
    assert result["modal"] == "image"
    assert result["confidence"] == 0.9
    assert result["conflicts"]


def test_decode_utf8_and_gb18030():
    utf8 = CORE.textparse.decode_bytes("数据配比中心".encode("utf-8"), ["utf-8-sig", "utf-8", "gb18030"])
    assert utf8["text"] == "数据配比中心"
    assert utf8["encoding"] in {"utf-8", "utf-8-sig"}
    gbk = CORE.textparse.decode_bytes("数据配比中心".encode("gb18030"), ["utf-8", "gb18030"])
    assert gbk["text"] == "数据配比中心"
    assert gbk["encoding"] == "gb18030"


def test_analyze_text_mojibake():
    assert CORE.textparse.analyze_text("")["empty"] is True
    assert CORE.textparse.analyze_text("正常文本")["mojibakeRate"] == 0.0
    assert CORE.textparse.analyze_text("abc\x00\x01")["mojibakeRate"] > 0


def test_parse_jsonl_valid_and_invalid(tmp_path):
    path = tmp_path / "demo.jsonl"
    path.write_text(
        '{"text": "第一行"}\n'
        'not-json\n'
        '{"content": "第三行"}\n',
        encoding="utf-8",
    )
    cfg = CORE.load_config("parse.json")
    parsed = CORE.textparse.parse_text_file(path, cfg, max_chars=1000)
    assert [item["text"] for item in parsed["records"]] == ["第一行", "第三行"]
    assert parsed["failures"][0]["reasonCode"] == "JSONL_PARSE_FAILED"


def test_simhash_and_phash_deterministic(tmp_path):
    assert CORE.simhash64("") is None
    left = CORE.simhash64("数据配比中心算子开发")
    assert left == CORE.simhash64("数据配比中心算子开发")
    other = CORE.simhash64("完全不同的另一段内容")
    assert (int(left, 16) ^ int(other, 16)).bit_count() > 0

    image = tmp_path / "a.png"
    Image.new("RGB", (64, 64), "blue").save(image)
    first = CORE.phash64(image)
    assert first == CORE.phash64(image)
    assert len(first) == 16


def test_source_rules(tmp_path):
    code = tmp_path / "demo.py"
    code.write_text("import os\n\ndef main():\n    return 1\n", encoding="utf-8")
    assert CORE.source.classify(code, text=code.read_text(encoding="utf-8"))["source"] == "code"

    dialogue = tmp_path / "chat.txt"
    text = "用户：你好\n助手：你好，请问需要什么帮助？\n用户：谢谢"
    assert CORE.source.classify(dialogue, text=text)["source"] == "dialogue"

    wiki = tmp_path / "wiki.jsonl"
    assert (
        CORE.source.classify(wiki, text="来源 https://zh.wikipedia.org/wiki/机器学习")["source"]
        == "wiki"
    )


def test_resolve_dt(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    cfg = CORE.load_config("parse.json")
    day, source = CORE._resolve_dt(path, cfg, {}, None)
    assert source == "file_time"
    assert day == CORE.ts_to_dt(path.stat().st_mtime)
    day, source = CORE._resolve_dt(path, cfg, {"dt_source": "content_time"}, "2020-01-02T03:04:05+00:00")
    assert source == "content_time"
    assert day == "2020-01-01" or day == "2020-01-02"


def test_validate_record_rejects_bad_hash():
    record = {
        "record_id": "r_x",
        "modal": "text",
        "source": "web_text",
        "metadata": {"format": "txt", "sizeBytes": 1, "sha256": "bad"},
        "quality": {"decodable": True, "completeness": 1.0},
        "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": "bad", "sha256": "bad"},
    }
    errors = CORE.records.validate_record(record)
    assert errors
