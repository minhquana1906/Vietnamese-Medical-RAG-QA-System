# Tests

This directory contains tests for the Vietnamese Medical RAG-QA System.

## Structure

```
tests/
├── conftest.py          # Pytest configuration and fixtures
├── test_*.py           # Main test files
├── unit/               # Unit tests (for future expansion)
└── integration/        # Integration tests (for future expansion)
```

## Running Tests

```bash
# Install dependencies
make install

# Run all tests
make test

# Run tests with coverage
make test-cov

# Run only unit tests
make test-unit

# Run specific test file
uv run pytest tests/test_main.py -v
```

## Test Categories

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions (future expansion)

## Writing Tests

1. Follow the naming convention: `test_*.py`
2. Use descriptive test names: `test_function_behavior`
3. Keep tests simple and focused
4. Mock external dependencies
5. Use fixtures from `conftest.py`

## Test Environment

Tests automatically use:
- SQLite in-memory database
- Mocked external services
- Test environment variables

No additional setup required - just run the tests!
