"""OP-10 单测与端到端：分词/句法/语体/六维评分/边界/幂等。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from op10_env import CORE, OP02_EVIDENCE

cfg = CORE.load_config()
segment = CORE.segment
lexical = CORE.lexical
syntax = CORE.syntax
genre = CORE.genre_util
taskfit = CORE.taskfit


def test_segment_sentences_and_words():
    text = "机器学习的核心是从数据中学习规律。深度学习使用多层神经网络。"
    sentences = segment.split_sentences(text, cfg)
    assert len(sentences) == 2
    tokens = segment.words("机器学习 model training 数据", cfg)
    assert "机器学习" in tokens or "机器" in tokens
    assert "model" in tokens and "training" in tokens


def test_lexical_metrics():
    tokens = ["a", "b", "a", "c", "b"]
    assert lexical.ttr(tokens) == 0.6
    assert lexical.msttr(tokens, 5) == 0.6
    assert lexical.mtld(tokens) > 0
    assert lexical.ttr([]) is None


def test_syntax_passive_and_clause():
    result = syntax.analyze("因为下雨，所以比赛被取消了。虽然他来了，但是没有发言。", cfg)
    assert result["sentenceCount"] == 2
    assert result["passiveSentences"] == 1
    assert result["clausesPerSentenceMean"] > 1
    assert result["clauseDepthMean"] > 1


def test_genre_rules():
    academic = genre.classify("本文在参考文献中列出了研究表明与实验方法。", cfg)
    assert academic["genre"] == "academic"
    assert academic["confidence"] > 0
    general = genre.classify("今天天气不错。", cfg)
    assert general["genre"] == "general"


def test_taskfit_renormalizes_without_domain():
    lex = {"ttr": 0.8, "msttr": 0.7, "mtld": 30.0, "tokenCount": 100}
    syn = {"completeSentenceRate": 1.0, "clausesPerSentenceMean": 2.0}
    gen = {"genre": "general", "confidence": 0.0}
    result = taskfit.score(lex, syn, gen, None, 200, cfg)
    assert result["dimensions"]["domainMatch"] is None
    assert result["groups"]["domain"] is None
    assert result["reasonCode"] == "DOMAIN_LABELS_UNAVAILABLE"
    assert 0 <= result["overall"] <= 10

    with_domain = taskfit.score(lex, syn, gen, 0.5, 200, cfg)
    assert with_domain["dimensions"]["domainMatch"] == 5.0
    assert with_domain["groups"]["domain"] is not None
    assert with_domain["reasonCode"] is None


def _record(record_id: str, text: str, modal: str = "text") -> dict:
    return {
        "record_id": record_id,
        "modal": modal,
        "source": "web_text",
        "text": text if modal == "text" else None,
        "metadata": {"format": "txt"},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": not (text or "").strip()},
        "partitions": {"modal": modal, "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": None, "sha256": None, "simhash": None, "phash": None},
    }


def test_core_mixed_batch(tmp_path: Path):
    records = [
        _record("r1", "机器学习是人工智能的分支。它从数据中学习规律，并进行预测。"),
        _record("r2", "   "),
        _record("r3", None, modal="image"),
    ]
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8"
    )
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert result["sampleCount"] == 2
    assert metrics["textRecords"] == 2
    assert metrics["skippedNonText"] == 1
    assert metrics["failuresByReason"] == {"EMPTY_TEXT": 1}
    assert metrics["domainMatchStatus"] == "unavailable"
    assert metrics["distributions"]["overall"]["p50"] is not None
    assert (tmp_path / "out" / "low_fit.jsonl").is_file()


def test_core_idempotent(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        json.dumps(_record("r1", "测试幂等的文本。第二句。"), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    CORE.run(str(input_dir), {}, 42, str(tmp_path / "a"))
    CORE.run(str(input_dir), {}, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_core_real_op02_batch(tmp_path: Path):
    if not (OP02_EVIDENCE / "records.jsonl").is_file():
        import pytest

        pytest.skip("缺少 OP-02 证据目录")
    result = CORE.run(str(OP02_EVIDENCE), {}, 42, str(tmp_path / "real"))
    metrics = result["metrics"]
    assert metrics["textRecords"] == 426
    assert metrics["evaluatedRecords"] > 400
    assert metrics["genreCounts"]
    assert metrics["distributions"]["overall"]["p50"] is not None
