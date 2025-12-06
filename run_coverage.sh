#!/bin/bash
# Run tests with coverage report

set -e

echo "==================================="
echo "Running Tests with Coverage"
echo "==================================="

# Clean previous coverage data
echo "Cleaning previous coverage data..."
rm -rf .coverage coverage.xml htmlcov/ .pytest_cache/

# Run integration tests with coverage
echo "Running integration tests..."
uv run pytest tests/integration/ -v \
    --cov=backend/src \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-report=xml \
    --cov-branch

echo ""
echo "==================================="
echo "Coverage Summary"
echo "==================================="

# Display coverage summary
uv run coverage report --skip-covered

echo ""
echo "==================================="
echo "Coverage Reports Generated"
echo "==================================="
echo "📊 Terminal: Displayed above"
echo "📁 HTML: htmlcov/index.html"
echo "📄 XML: coverage.xml"
echo ""
echo "To view HTML report:"
echo "  open htmlcov/index.html"
echo ""
