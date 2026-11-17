"""语种识别：Unicode 文字体系统计 + 功能词画像（可解释规则，不加载模型）。

口径：
- 逐字符归类到 han/kana/hangul/cyrillic/arabic/latin/other；
- 主导语种按规则优先：韩文 > 日文（含假名）> 俄文 > 阿拉伯文 > 中文（纯汉字）> 拉丁语系；
- 置信度 = 主导语种文字字数 / 字母类字符总数；
- 第二语种占比 >= ``mixedSecondShare`` 或置信度 < ``minConfidence`` 时标 mixed/unknown。
"""

from __future__ import annotations

import re
from typing import Any

HAN = re.compile(r"[一-鿿㐀-䶿]")
HIRA = re.compile(r"[぀-ゟ]")
KATA = re.compile(r"[゠-ヿ]")
HANGUL = re.compile(r"[가-힯ᄀ-ᇿ]")
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
WORD = re.compile(r"[A-Za-z']+")
CJK = re.compile(r"[一-鿿㐀-䶿぀-ゟ゠-ヿ]")


def _script_counts(text: str) -> dict[str, int]:
    return {
        "han": len(HAN.findall(text)),
        "hiragana": len(HIRA.findall(text)),
        "katakana": len(KATA.findall(text)),
        "hangul": len(HANGUL.findall(text)),
        "cyrillic": len(CYRILLIC.findall(text)),
        "arabic": len(ARABIC.findall(text)),
        "latin": len(LATIN.findall(text)),
    }


def _stopword_scores(text: str, words: dict[str, list[str]]) -> dict[str, float]:
    tokens = [token.lower() for token in WORD.findall(text)]
    cjk_tokens = CJK.findall(text)
    scores: dict[str, float] = {}
    for language, items in words.items():
        if language in {"zh", "ja"}:
            hits = sum(1 for item in items if item in text)
            denominator = max(1, len(cjk_tokens))
            scores[language] = hits / denominator
        else:
            if not tokens:
                scores[language] = 0.0
                continue
            hit = sum(1 for token in tokens if token in set(items))
            scores[language] = hit / len(tokens)
    return scores


def detect(text: str | None, cfg: dict[str, Any]) -> dict[str, Any]:
    if not text or not text.strip():
        return {
            "language": "unknown",
            "confidence": 0.0,
            "status": "unknown",
            "scripts": {},
            "reasonCode": "EMPTY_TEXT",
        }
    limit = int(cfg["language"]["maxTextChars"])
    value = text[:limit]
    counts = _script_counts(value)
    total = sum(counts.values())
    if total == 0:
        return {
            "language": "unknown",
            "confidence": 0.0,
            "status": "unknown",
            "scripts": counts,
            "reasonCode": "NO_LETTERS",
        }
    shares = {name: count / total for name, count in counts.items()}

    min_script = float(cfg["language"]["minScriptShare"])
    kana = shares["hiragana"] + shares["katakana"]
    if shares["hangul"] >= min_script:
        language, share = "ko", shares["hangul"]
    elif kana >= float(cfg["language"]["kanaMinShare"]):
        language, share = "ja", shares["han"] + kana
    elif shares["cyrillic"] >= min_script:
        language, share = "ru", shares["cyrillic"]
    elif shares["arabic"] >= min_script:
        language, share = "ar", shares["arabic"]
    elif shares["han"] >= min_script:
        language, share = "zh", shares["han"]
    elif shares["latin"] >= min_script:
        scores = _stopword_scores(value, cfg["language"]["functionWords"])
        latin_scores = {name: score for name, score in scores.items() if name in {"en", "de", "fr", "es"}}
        best = max(latin_scores, key=lambda name: (latin_scores[name], name))
        language = best if latin_scores[best] >= 0.02 else "en"
        share = shares["latin"]
    else:
        return {
            "language": "unknown",
            "confidence": 0.0,
            "status": "unknown",
            "scripts": counts,
            "reasonCode": "LOW_SCRIPT_COVERAGE",
        }

    if language in {"en", "de", "fr", "es"}:
        second = shares["latin"] - share
    else:
        second = max(
            (value for name, value in shares.items() if name not in _owned_scripts(language)),
            default=0.0,
        )
    confidence = round(float(share), 6)
    min_confidence = float(cfg["language"]["minConfidence"])
    if confidence >= min_confidence and second < float(cfg["language"]["mixedSecondShare"]):
        status = "identified"
    elif second >= float(cfg["language"]["mixedSecondShare"]):
        status = "mixed"
    else:
        status = "unknown"
    return {
        "language": language,
        "confidence": confidence,
        "status": status,
        "scripts": counts,
        "shares": {name: round(value, 6) for name, value in shares.items()},
        "secondShare": round(float(second), 6),
        "reasonCode": None if status == "identified" else f"LOW_CONFIDENCE_{status.upper()}",
    }


def _owned_scripts(language: str) -> set[str]:
    return {
        "zh": {"han"},
        "ja": {"han", "hiragana", "katakana"},
        "ko": {"hangul"},
        "ru": {"cyrillic"},
        "ar": {"arabic"},
    }.get(language, {"latin"})
