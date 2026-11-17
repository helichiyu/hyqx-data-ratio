"""六维任务适配评分（0–10）与分组加权。

六个子指标分三组：
- structure（0.4）：sentenceCompleteness、clauseComplexity；
- semantic（0.3）：lexicalRichness、informationDensity；
- domain（0.3）：domainMatch、genreFit。

无领域标签时 domainMatch=null，domain 组整体不参与，权重在 structure/semantic 上
重新归一化，并写 ``reasonCode=DOMAIN_LABELS_UNAVAILABLE``。
"""

from __future__ import annotations

from typing import Any


def _clip(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 6)


def score(
    lexical: dict[str, Any],
    syntax: dict[str, Any],
    genre: dict[str, Any],
    domain_confidence: float | None,
    char_count: int,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    fit = cfg["taskfit"]
    completeness = _clip((syntax.get("completeSentenceRate") or 0.0) * 10)
    clauses = syntax.get("clausesPerSentenceMean") or 1.0
    complexity = _clip(((clauses - 1.0) / 4.0) * 10)
    richness = _clip((lexical.get("msttr") or 0.0) * 10)
    tokens = lexical.get("tokenCount") or 0
    density = _clip((tokens / char_count * 100) / 2) if char_count else 0.0
    genre_fit = _clip((genre.get("confidence") or 0.0) * 10)
    domain_match = None if domain_confidence is None else _clip(domain_confidence * 10)

    sub_weights = fit["subWeights"]
    structure = (
        sub_weights["structure"]["sentenceCompleteness"] * completeness
        + sub_weights["structure"]["clauseComplexity"] * complexity
    )
    semantic = (
        sub_weights["semantic"]["lexicalRichness"] * richness
        + sub_weights["semantic"]["informationDensity"] * density
    )
    dimensions = {
        "sentenceCompleteness": completeness,
        "clauseComplexity": complexity,
        "lexicalRichness": richness,
        "informationDensity": density,
        "domainMatch": domain_match,
        "genreFit": genre_fit,
    }
    groups = {"structure": round(structure, 6), "semantic": round(semantic, 6)}
    reason = None
    if domain_match is None:
        weight_total = fit["groupWeights"]["structure"] + fit["groupWeights"]["semantic"]
        overall = (
            structure * fit["groupWeights"]["structure"]
            + semantic * fit["groupWeights"]["semantic"]
        ) / weight_total
        groups["domain"] = None
        reason = "DOMAIN_LABELS_UNAVAILABLE"
    else:
        domain = (
            sub_weights["domain"]["domainMatch"] * domain_match
            + sub_weights["domain"]["genreFit"] * genre_fit
        )
        groups["domain"] = round(domain, 6)
        overall = sum(fit["groupWeights"][name] * groups[name] for name in groups)
    overall = _clip(overall)
    return {
        "dimensions": dimensions,
        "groups": groups,
        "overall": overall,
        "lowFit": overall < float(fit["lowFitThreshold"]),
        "lowFitThreshold": float(fit["lowFitThreshold"]),
        "reasonCode": reason,
    }
