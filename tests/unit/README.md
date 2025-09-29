# Unit Tests

This directory contains unit tests for individual components:

- `test_api.py` - API endpoint tests
- `test_models.py` - Database model tests
- `test_services.py` - Business logic tests
- `test_utils.py` - Utility function tests

## Running Unit Tests

```bash
# Run all unit tests
pytest tests/unit/

# Run specific test file
pytest tests/unit/test_api.py -v
```

## Adding New Unit Tests

1. Create test file following `test_*.py` pattern
2. Import the module to test
3. Write focused tests for specific functions/classes
4. Use mocks for external dependencies
