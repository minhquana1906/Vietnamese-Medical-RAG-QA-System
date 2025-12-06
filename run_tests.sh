#!/bin/bash
# Script chạy integration tests và performance tests
# Usage: ./run_tests.sh [integration|perf|all]

set -e

TEST_TYPE="${1:-all}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================================="
echo "Vietnamese Medical RAG - Test Runner"
echo "=================================================="
echo "Project root: $PROJECT_ROOT"
echo "Test type: $TEST_TYPE"
echo ""

# Check if backend service is running
check_backend() {
    echo "Checking backend service..."
    if curl -s http://localhost:8000/v1/health > /dev/null 2>&1; then
        echo "✓ Backend service is running"
        return 0
    else
        echo "✗ Backend service is NOT running"
        echo ""
        echo "Please start backend service first:"
        echo "  cd backend && docker compose up -d"
        return 1
    fi
}

# Run integration tests
run_integration_tests() {
    echo ""
    echo "=================================================="
    echo "Running Integration Tests"
    echo "=================================================="
    
    if ! check_backend; then
        exit 1
    fi
    
    echo ""
    echo "Running pytest..."
    pytest tests/integration/ -v -s --tb=short
    
    echo ""
    echo "✓ Integration tests completed"
}

# Run integration tests with coverage
run_integration_tests_with_coverage() {
    echo ""
    echo "=================================================="
    echo "Running Integration Tests with Coverage"
    echo "=================================================="
    
    if ! check_backend; then
        exit 1
    fi
    
    echo ""
    echo "Running pytest with coverage..."
    pytest tests/integration/ -v -s --tb=short \
        --cov=backend/src \
        --cov-report=html \
        --cov-report=term-missing
    
    echo ""
    echo "✓ Integration tests completed"
    echo "Coverage report: htmlcov/index.html"
}

# Run performance tests
run_perf_tests() {
    echo ""
    echo "=================================================="
    echo "Running Performance Tests (Locust)"
    echo "=================================================="
    
    if ! check_backend; then
        exit 1
    fi
    
    echo ""
    echo "Starting Locust load test..."
    echo "Duration: 2 minutes"
    echo "Users: 50"
    echo "Spawn rate: 5 users/sec"
    echo ""
    
    locust -f tests/perf/locustfile.py \
        --host=http://localhost:8000 \
        --users 50 \
        --spawn-rate 5 \
        --run-time 2m \
        --headless \
        --html tests/perf/locust_report.html
    
    echo ""
    echo "✓ Performance tests completed"
    echo "Report: tests/perf/locust_report.html"
}

# Run performance tests (web UI mode)
run_perf_tests_ui() {
    echo ""
    echo "=================================================="
    echo "Running Performance Tests (Web UI)"
    echo "=================================================="
    
    if ! check_backend; then
        exit 1
    fi
    
    echo ""
    echo "Starting Locust web UI..."
    echo "Open browser: http://localhost:8089"
    echo ""
    
    locust -f tests/perf/locustfile.py \
        --host=http://localhost:8000
}

# Main execution
case "$TEST_TYPE" in
    integration)
        run_integration_tests
        ;;
    integration-cov)
        run_integration_tests_with_coverage
        ;;
    perf)
        run_perf_tests
        ;;
    perf-ui)
        run_perf_tests_ui
        ;;
    all)
        run_integration_tests
        echo ""
        echo "Waiting 5 seconds before performance tests..."
        sleep 5
        run_perf_tests
        ;;
    *)
        echo "Unknown test type: $TEST_TYPE"
        echo ""
        echo "Usage: $0 [integration|integration-cov|perf|perf-ui|all]"
        echo ""
        echo "Options:"
        echo "  integration      - Run integration tests only"
        echo "  integration-cov  - Run integration tests with coverage"
        echo "  perf            - Run performance tests (headless, 2 min)"
        echo "  perf-ui         - Run performance tests (web UI)"
        echo "  all             - Run both integration and performance tests"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
echo "All tests completed successfully!"
echo "=================================================="
