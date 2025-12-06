import json
from pathlib import Path


def print_table(results_json: Path):
    data = json.loads(results_json.read_text(encoding="utf-8"))
    total = data.get("total", 0)
    passed = data.get("passed", 0)
    failed = data.get("failed", 0)
    rows = data.get("results", [])

    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print("Status | Query | Reasons")
    print("-------|-------|--------")
    for r in rows:
        status = "PASS" if r.get("ok") else "FAIL"
        reasons = "; ".join(r.get("reasons", []))
        query = r.get("query", "")
        print(f"{status} | {query} | {reasons}")


if __name__ == "__main__":
    path = Path("data/test_results.json")
    if not path.exists():
        print("data/test_results.json not found. Run quick_validate_answers.py first.")
    else:
        print_table(path)
