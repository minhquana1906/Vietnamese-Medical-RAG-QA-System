# Load Testing (Locust)

Run Locust against the backend API using the perf profile in `tests/perf/locustfile.py`.

```powershell
Push-Location tests\perf; locust; Pop-Location
```

Adjust host to your backend (default Chainlit proxy or direct API).
