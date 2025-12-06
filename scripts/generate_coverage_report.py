#!/usr/bin/env python3
"""
Generate comprehensive coverage report with metrics
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_coverage():
    """Run tests with coverage"""
    print("🧪 Running tests with coverage...\n")

    result = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "tests/integration/",
            "-v",
            "--cov=backend/src",
            "--cov-report=json",
            "--cov-report=term-missing",
            "--cov-report=html",
            "--cov-report=xml",
            "--cov-branch",
        ],
        capture_output=False,
    )

    return result.returncode == 0


def parse_coverage_json():
    """Parse coverage.json to extract metrics"""
    coverage_file = Path("coverage.json")

    if not coverage_file.exists():
        print("❌ coverage.json not found!")
        return None

    with open(coverage_file) as f:
        data = json.load(f)

    return data


def generate_report(coverage_data):
    """Generate detailed coverage report"""
    if not coverage_data:
        return

    totals = coverage_data.get("totals", {})
    files = coverage_data.get("files", {})

    print("\n" + "=" * 60)
    print("📊 COVERAGE SUMMARY")
    print("=" * 60)

    print(f"\n📈 Overall Metrics:")
    print(f"  Total Statements: {totals.get('num_statements', 0)}")
    print(f"  Covered: {totals.get('covered_lines', 0)}")
    print(f"  Missing: {totals.get('missing_lines', 0)}")
    print(f"  Coverage: {totals.get('percent_covered', 0):.2f}%")

    if "covered_branches" in totals:
        branch_coverage = (
            totals.get("covered_branches", 0) / totals.get("num_branches", 1)
        ) * 100
        print(f"  Branch Coverage: {branch_coverage:.2f}%")

    # Top 10 files with lowest coverage
    file_coverage = []
    for filepath, file_data in files.items():
        summary = file_data.get("summary", {})
        coverage_pct = summary.get("percent_covered", 0)
        file_coverage.append((filepath, coverage_pct, summary))

    file_coverage.sort(key=lambda x: x[1])

    print(f"\n⚠️  Files Needing Attention (Lowest Coverage):")
    for i, (filepath, pct, summary) in enumerate(file_coverage[:10], 1):
        # Shorten path
        short_path = filepath.replace("backend/src/", "")
        missing = summary.get("missing_lines", 0)
        print(f"  {i}. {short_path}")
        print(f"     Coverage: {pct:.1f}% | Missing: {missing} lines")

    # Files with 100% coverage
    full_coverage = [fp for fp, pct, _ in file_coverage if pct == 100.0]
    if full_coverage:
        print(f"\n✅ Files with 100% Coverage: {len(full_coverage)}")

    print("\n" + "=" * 60)
    print("📁 Report Locations:")
    print("=" * 60)
    print(f"  📊 HTML: htmlcov/index.html")
    print(f"  📄 XML: coverage.xml")
    print(f"  📋 JSON: coverage.json")
    print("")

    # Coverage badge
    coverage_pct = totals.get("percent_covered", 0)
    if coverage_pct >= 90:
        badge = "🟢 Excellent"
    elif coverage_pct >= 80:
        badge = "🟡 Good"
    elif coverage_pct >= 70:
        badge = "🟠 Fair"
    else:
        badge = "🔴 Needs Improvement"

    print(f"Coverage Status: {badge} ({coverage_pct:.1f}%)")
    print("")

    return coverage_pct


def main():
    """Main execution"""
    print("=" * 60)
    print("Vietnamese Medical RAG - Coverage Report Generator")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Run coverage
    success = run_coverage()

    if not success:
        print("\n❌ Tests failed!")
        sys.exit(1)

    # Parse and generate report
    coverage_data = parse_coverage_json()
    coverage_pct = generate_report(coverage_data)

    # Check minimum threshold
    MIN_COVERAGE = 70.0
    if coverage_pct and coverage_pct < MIN_COVERAGE:
        print(
            f"⚠️  Warning: Coverage {coverage_pct:.1f}% is below minimum threshold {MIN_COVERAGE}%"
        )
        sys.exit(1)

    print("✅ Coverage check passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()
