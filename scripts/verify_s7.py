"""S7 全链路本机验收：证据一致性、P0/全量链路、22 healthz、反伪造 grep、最小压缩包。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/verify_s7.py

输出：
    docs/算子开发/evidence/S7/run-<date>/verification.json
    docs/算子开发/evidence/S7/run-<date>/healthz.json
    docs/算子开发/evidence/S7/run-<date>/grep.txt
    docs/算子开发/evidence/S7/run-<date>/package.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DIR = ROOT / "operator"
REGISTRY = ROOT / "docs" / "算子开发" / "registry.json"
TRANSPORT = OPERATOR_DIR / "runtime" / "transport"
P0_OPERATORS = ["OP-01", "OP-02", "OP-03", "OP-05", "OP-08", "OP-09", "OP-10", "OP-14", "OP-15", "OP-17", "OP-18"]


def _load_registry() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["operators"]


def _check_artifacts(evidence: Path) -> list[str]:
    problems = []
    path = evidence / "artifacts.sha256"
    if not path.is_file():
        return ["artifacts.sha256 缺失"]
    for line in path.read_text(encoding="utf-8").splitlines():
        checksum, _, name = line.partition("  ")
        file = evidence / name
        if not file.is_file():
            problems.append(f"产物缺失：{name}")
            continue
        if hashlib.sha256(file.read_bytes()).hexdigest() != checksum:
            problems.append(f"产物哈希不一致：{name}")
    return problems


def _check_operator(row: dict) -> dict:
    evidence_path = row.get("evidencePath")
    result = {
        "opId": row["opId"],
        "operatorId": row["operatorId"],
        "status": row.get("status"),
        "evidencePath": evidence_path,
        "errors": [],
        "warnings": [],
    }
    if not evidence_path:
        result["errors"].append("evidencePath 为空")
        return result
    evidence = ROOT / evidence_path
    if not evidence.is_dir():
        result["errors"].append("证据目录不存在")
        return result
    for name in ("manifest.json", "metrics.json", "summary.json", "result.json"):
        if not (evidence / name).is_file():
            result["errors"].append(f"{name} 缺失")
    manifest = {}
    if (evidence / "manifest.json").is_file():
        try:
            manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result["errors"].append("manifest.json 不可解析")
    if manifest:
        result_run_id = None
        if (evidence / "result.json").is_file():
            try:
                envelope = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
                result_run_id = (envelope.get("data") or {}).get("runId")
            except json.JSONDecodeError:
                result["errors"].append("result.json 不可解析")
        if manifest.get("runId") != evidence.name:
            if result_run_id == evidence.name:
                # S1～S3 早期算子 manifest 使用 records 文件指纹，HTTP 结果/目录为输入目录指纹；
                # 二者都可复算，但口径不一致，登记为遗留警告，不覆盖历史证据。
                result["warnings"].append(
                    f"legacy manifest.runId={manifest.get('runId')} 与 HTTP 目录 {evidence.name} 不一致（result.json 一致）"
                )
            else:
                result["errors"].append(
                    f"manifest.runId={manifest.get('runId')} 与目录名 {evidence.name} 不一致，且 result.json 也不一致"
                )
        if manifest.get("operatorId") != row["operatorId"]:
            result["errors"].append("manifest.operatorId 与 registry 不一致")
        for field in ("operatorVersion", "paramsHash"):
            if not manifest.get(field):
                result["warnings"].append(f"manifest.{field} 缺失")
    metrics = {}
    if (evidence / "metrics.json").is_file():
        try:
            metrics = json.loads((evidence / "metrics.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result["errors"].append("metrics.json 不可解析")
    if metrics:
        for field in ("operatorVersion", "modelVersion", "treeVersion", "paramsHash", "seed"):
            if field not in metrics:
                result["warnings"].append(f"metrics.{field} 缺失")
    result["errors"].extend(_check_artifacts(evidence))
    result["manifestVersion"] = manifest.get("operatorVersion")
    result["treeVersion"] = manifest.get("treeVersion")
    result["modelVersion"] = manifest.get("modelVersion")
    return result


def _chain_checks() -> dict:
    def read_manifest(op_dir: Path) -> dict:
        path = op_dir / "manifest.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def read_input_manifest(op_dir: Path) -> dict:
        path = op_dir / "input_manifest.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    op17 = OPERATOR_DIR / "dm-dataset-packaging" / "output" / "evidence" / "347d6365d8457c91"
    op18 = OPERATOR_DIR / "dm-dataset-evaluation" / "output" / "evidence" / "020fe881d78849c0"
    op19 = OPERATOR_DIR / "dm-ratio-reporting" / "output" / "evidence" / "bf9ce91b0a82182b"
    op20 = OPERATOR_DIR / "dm-graph-indexing" / "output" / "evidence" / "e5f5df6ab0857e5f"
    op22 = OPERATOR_DIR / "dm-risk-detection" / "output" / "evidence" / "8a156871249e49f4"
    checks = {}
    inp17 = read_input_manifest(op17)
    checks["OP-17_consumes_OP-15"] = "cab32b6cd497cac3" in str(inp17.get("planPath"))
    inp18 = read_input_manifest(op18)
    checks["OP-18_consumes_OP-17"] = "347d6365d8457c91" in str(inp18.get("datasetRunDir"))
    inp19 = read_input_manifest(op19)
    results19 = inp19.get("operatorResults") or {}
    checks["OP-19_consumes_OP-15/17/18"] = all(
        fragment in " ".join(str(value) for value in results19.values())
        for fragment in ("cab32b6cd497cac3", "347d6365d8457c91", "020fe881d78849c0")
    )
    inp20 = read_input_manifest(op20)
    checks["OP-20_consumes_OP-02/03"] = (
        "10a342ae92595ab7" in str(inp20.get("recordsPath"))
        and "e53b5d9093388fe5" in str(inp20.get("vectorsPath"))
    )
    inp22 = read_input_manifest(op22)
    results22 = inp22.get("operatorResults") or {}
    checks["OP-22_consumes_OP-08..19"] = all(
        fragment in " ".join(str(value) for value in results22.values())
        for fragment in ("73e001cb4f8e5aed", "f979e048a3250253", "cab32b6cd497cac3", "020fe881d78849c0")
    )
    return checks


def _healthz(port: int) -> dict:
    env = dict(os.environ)
    env.update({"INPUT_DIR": str(TRANSPORT / "input"), "OUTPUT_DIR": str(TRANSPORT / "output"), "PYTHONIOENCODING": "utf-8"})
    log_path = TRANSPORT / "s7-service.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "inference:app", "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
        cwd=str(OPERATOR_DIR), env=env, stdout=handle, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                    if json.loads(response.read()).get("code") == 0:
                        break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        else:
            return {"error": "服务未就绪", "log": log_path.as_posix()}
        operators = [row["operatorId"] for row in _load_registry()]
        probes = {}
        for operator in operators:
            try:
                with urllib.request.urlopen(f"{base}/{operator}/healthz", timeout=5) as response:
                    payload = json.loads(response.read())
                probes[operator] = {
                    "http": response.status,
                    "code": payload.get("code"),
                    "ready": (payload.get("data") or {}).get("ready"),
                }
            except Exception as exc:  # noqa: BLE001
                probes[operator] = {"error": f"{type(exc).__name__}: {exc}"}
        with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
            aggregate = json.loads(response.read())
        return {"probes": probes, "aggregate": aggregate, "log": log_path.as_posix()}
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        handle.close()


def _grep() -> list[str]:
    pattern = re.compile(r"\brandom\.|np\.random|Math\.random|time\.sleep|FAKE|MOCK_|TODO:")
    hits = []
    for path in sorted(OPERATOR_DIR.glob("dm-*/*/**/*.py")):
        parts = set(path.parts)
        if parts & {"tests", "dataset", "output", "runtime"}:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}")
    return hits


def _package() -> dict:
    output = []
    dist = ROOT / "dist"
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = git_bash.as_posix() if git_bash.is_file() else "bash"
    try:
        completed = subprocess.run(
            [bash, "scripts/package_docker_bundle.sh"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        output.append(completed.stdout or "")
        output.append(completed.stderr or "")
        tarballs = sorted(dist.glob("op-data-mixing-*.tar.gz"))
        listing = []
        if tarballs:
            listing = subprocess.run(
                ["tar", "-tzf", str(tarballs[-1])], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
            ).stdout.splitlines()
        forbidden = [
            name for name in listing
            if "/tests/" in name or "/dataset/" in name or "/output/" in name or name.endswith(".md")
        ]
        return {
            "returncode": completed.returncode,
            "tarball": tarballs[-1].as_posix() if tarballs else None,
            "fileCount": len(listing),
            "forbidden": forbidden[:20],
            "log": "\n".join(output),
        }
    except Exception as exc:  # noqa: BLE001
        return {"returncode": None, "error": f"{type(exc).__name__}: {exc}", "log": "\n".join(output)}


def main() -> int:
    parser = argparse.ArgumentParser(description="S7 全链路本机验收")
    parser.add_argument("--stage-date", default=time.strftime("%Y%m%d"))
    parser.add_argument("--port", type=int, default=17031)
    args = parser.parse_args()

    rows = _load_registry()
    results = [_check_operator(row) for row in rows]
    errors = [f"{item['opId']}: {error}" for item in results for error in item["errors"]]
    warnings = [f"{item['opId']}: {warning}" for item in results for warning in item["warnings"]]
    p0 = [item["opId"] for item in results if item["opId"] in P0_OPERATORS and not item["errors"]]
    chain = _chain_checks()
    health = _healthz(args.port)
    grep_hits = _grep()
    package = _package()

    stage = ROOT / "docs" / "算子开发" / "evidence" / "S7" / f"run-{args.stage_date}"
    stage.mkdir(parents=True, exist_ok=True)
    health_ok = 0
    if "probes" in health:
        health_ok = sum(1 for probe in health["probes"].values() if probe.get("code") == 0 and probe.get("ready"))
    else:
        health_ok = 0
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "operatorCount": len(results),
        "operators": results,
        "errors": errors,
        "warnings": warnings,
        "p0ChainOperators": P0_OPERATORS,
        "p0ChainVerified": sorted(p0),
        "p0ChainComplete": set(p0) == set(P0_OPERATORS),
        "fullChainComplete": not errors,
        "chainChecks": chain,
        "healthz": {
            "passed": health_ok,
            "total": len(results),
            "allPassed": health_ok == len(results),
            "detail": health,
        },
        "grep": {"hits": grep_hits, "clean": not grep_hits},
        "package": package,
        "manualGates": [
            "H-01 Docker 构建与容器内 22 healthz",
            "平台联调（17025/X-Token/10 MiB/超时/幂等/断点）",
            "H-02 树版本 / H-03 阈值 / H-05 真值与专家 / H-11 本体/KG / Q-07 Neo4j/FAISS 许可",
        ],
    }
    (stage / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (stage / "healthz.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (stage / "grep.txt").write_text("\n".join(grep_hits) + "\n" if grep_hits else "(no hits)\n", encoding="utf-8", newline="\n")
    (stage / "package.txt").write_text(
        json.dumps({key: value for key, value in package.items() if key != "log"}, ensure_ascii=False, indent=2)
        + "\n\n"
        + (package.get("log") or ""),
        encoding="utf-8", newline="\n",
    )
    print(json.dumps({
        "operators": len(results),
        "errors": len(errors),
        "warnings": len(warnings),
        "p0Complete": report["p0ChainComplete"],
        "fullChainComplete": report["fullChainComplete"],
        "healthz": f"{health_ok}/{len(results)}",
        "grepHits": len(grep_hits),
        "package": {"returncode": package.get("returncode"), "fileCount": package.get("fileCount"), "forbidden": package.get("forbidden")},
        "chainChecks": chain,
    }, ensure_ascii=False, indent=2))
    return 0 if report["fullChainComplete"] and report["healthz"]["allPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
