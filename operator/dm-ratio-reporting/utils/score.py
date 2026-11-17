"""九维综合评分、结论摘要与可选 HTML 渲染。"""

from __future__ import annotations

from html import escape
from typing import Any


def overall(dimensions: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    available = [item for item in dimensions if item.get("score") is not None]
    weight_sum = sum(float(item["weight"]) for item in available)
    score = (
        sum(float(item["score"]) * float(item["weight"]) for item in available) / weight_sum
        if weight_sum > 0
        else None
    )
    thresholds = cfg["overall"]["thresholds"]
    if score is None:
        grade = "no_data"
    elif score >= float(thresholds["excellent"]):
        grade = "excellent"
    elif score >= float(thresholds["good"]):
        grade = "good"
    elif score >= float(thresholds["pass"]):
        grade = "pass"
    else:
        grade = "fail"
    missing = [
        {
            "key": item["key"],
            "nameZh": item["nameZh"],
            "operator": item["operator"],
            "reason": item.get("reason"),
        }
        for item in dimensions
        if item.get("score") is None
    ]
    return {
        "score": round(score, 10) if score is not None else None,
        "grade": grade,
        "weightSumUsed": round(weight_sum, 10),
        "dimensionsAvailable": len(available),
        "dimensionsTotal": len(dimensions),
        "missing": missing,
        "thresholds": thresholds,
        "definition": "综合分 = Σ 可用维度分×权重 / Σ 可用权重；不可用维度剔除并列入 missing，不按 0 计。",
    }


def conclusions(dimensions: list[dict[str, Any]], overall_report: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for dimension in dimensions:
        if dimension.get("score") is None:
            items.append(
                {
                    "key": dimension["key"],
                    "severity": "info",
                    "text": f"{dimension['nameZh']}：缺少 {dimension['operator']} 指标（{dimension.get('reason') or 'no_data'}），未计入综合分。",
                }
            )
            continue
        severity = "info" if dimension["grade"] in {"excellent", "good"} else "warning"
        if dimension["grade"] == "fail":
            severity = "critical"
        suffix = ""
        raw = dimension.get("raw") or {}
        if dimension["key"] == "evaluation_quality" and raw.get("truthStatus") != "ok":
            suffix = "（无人工真值，proxy_only，不等价于准确率）"
            if severity == "info":
                severity = "warning"
        items.append(
            {
                "key": dimension["key"],
                "severity": severity,
                "text": (
                    f"{dimension['nameZh']}：得分 {dimension['score']:.4f}（{dimension['grade']}），"
                    f"来源 {dimension['operator']} · {dimension['metric']}{suffix}。"
                ),
            }
        )
    if overall_report.get("score") is None:
        items.append({"key": "overall", "severity": "critical", "text": "综合评分无可用维度，未生成结论性评分。"})
    else:
        items.append(
            {
                "key": "overall",
                "severity": "info" if overall_report["grade"] in {"excellent", "good"} else "warning",
                "text": (
                    f"综合评分 {overall_report['score']:.4f}（{overall_report['grade']}），"
                    f"使用 {overall_report['dimensionsAvailable']}/{overall_report['dimensionsTotal']} 个维度。"
                ),
            }
        )
    return items


def render_html(report: dict[str, Any], title: str) -> str:
    rows = []
    for dimension in report["dimensions"]:
        score = "-" if dimension.get("score") is None else f"{dimension['score']:.4f}"
        rows.append(
            "<tr>"
            f"<td>{escape(str(dimension['nameZh']))}</td>"
            f"<td>{escape(str(dimension['operator']))}</td>"
            f"<td>{escape(str(dimension['grade']))}</td>"
            f"<td>{score}</td>"
            f"<td>{escape(str(dimension['weight']))}</td>"
            f"<td>{escape(str(dimension.get('reason') or ''))}</td>"
            "</tr>"
        )
    conclusion_items = "".join(
        f"<li class='{escape(item['severity'])}'>{escape(item['text'])}</li>" for item in report["conclusions"]
    )
    overall = report["overall"]
    overall_text = "无可用维度" if overall.get("score") is None else f"{overall['score']:.4f}（{overall['grade']}）"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:32px;color:#1f2933}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:24px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #d9e2ec;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f0f4f8}} .critical{{color:#b42318}} .warning{{color:#b54708}} .info{{color:#334e68}}
</style></head><body>
<h1>{escape(title)}</h1>
<p>综合评分：<strong>{escape(overall_text)}</strong></p>
<p>版本：operator {escape(str(report.get('operatorVersion')))} · tree {escape(str(report.get('treeVersion')))} · seed {escape(str(report.get('seed')))}</p>
<h2>九维状态矩阵</h2>
<table><thead><tr><th>维度</th><th>来源</th><th>等级</th><th>得分</th><th>权重</th><th>缺数据原因</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>结论摘要</h2><ul>{conclusion_items}</ul>
<p>本页由算子数据包渲染；渲染失败不影响 `report_package.json`。</p>
</body></html>
"""
