import json
import sys
import os
from pathlib import Path
import requests
import csv


def load_queries(path: Path):
    queries = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                queries.append(json.loads(line))
    return queries


def validate_answer(resp_json: dict, keywords: list[str], expect_sources: bool):
    ok = True
    reasons = []

    answer = resp_json.get("answer") or resp_json.get("text") or ""
    sources = resp_json.get("sources") or resp_json.get("documents") or []

    # Basic checks
    if not answer:
        ok = False
        reasons.append("empty answer")

    # Keyword presence (heuristic)
    lower = answer.lower()
    missing = [kw for kw in keywords if kw.lower() not in lower]
    if missing:
        reasons.append(f"missing keywords: {', '.join(missing)}")

    # Sources expected
    if expect_sources and not sources:
        reasons.append("missing sources")

    return ok and not reasons, reasons


def main():
    base_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    data_path = Path("data/golden_queries.jsonl")
    if len(sys.argv) > 1:
        data_path = Path(sys.argv[1])

    queries = load_queries(data_path)
    print(f"Loaded {len(queries)} queries from {data_path}")

    passed = 0
    results = []
    for item in queries:
        q = item["query"]
        body = {"query": q, "top_k": 5, "return_sources": True}
        try:
            r = requests.post(f"{base_url}/v1/rag", json=body, timeout=60)
            r.raise_for_status()
            ok, reasons = validate_answer(r.json(), item.get("keywords", []), item.get("expect_sources", True))
        except Exception as e:
            ok = False
            reasons = [f"request error: {e}"]

        results.append({"query": q, "ok": ok, "reasons": reasons})
        if ok:
            passed += 1

    # Print console summary
    print("Summary:")
    for res in results:
        status = "PASS" if res["ok"] else "FAIL"
        reason_text = "; ".join(res["reasons"]) if res["reasons"] else ""
        print(f"- {status} | {res['query']} | {reason_text}")

    print(f"Passed {passed}/{len(queries)}")

    # Persist results to JSON and CSV for reporting
    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "test_results.json"
    csv_path = out_dir / "test_results.csv"

    with json_path.open("w", encoding="utf-8") as jf:
        json.dump({
            "total": len(queries),
            "passed": passed,
            "failed": len(queries) - passed,
            "results": results,
        }, jf, ensure_ascii=False, indent=2)

    with csv_path.open("w", newline="", encoding="utf-8") as cf:
        writer = csv.writer(cf)
        writer.writerow(["status", "query", "reasons"])
        for res in results:
            status = "PASS" if res["ok"] else "FAIL"
            reason_text = "; ".join(res["reasons"]) if res["reasons"] else ""
            writer.writerow([status, res["query"], reason_text])

    print(f"Saved results to {json_path} and {csv_path}")


if __name__ == "__main__":
    main()
