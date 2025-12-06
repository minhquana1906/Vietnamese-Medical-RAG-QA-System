import requests
import os


def query_prometheus(prom_url: str, prom_query: str):
    r = requests.get(f"{prom_url}/api/v1/query", params={"query": prom_query}, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    prom_url = os.environ.get("PROM_URL", "http://localhost:9090")
    # Example: summarize p50/p95 for rag pipeline duration (adjust metric names if different)
    queries = {
        "p50": "histogram_quantile(0.5, sum(rate(rag_search_duration_seconds_bucket[5m])) by (le))",
        "p95": "histogram_quantile(0.95, sum(rate(rag_search_duration_seconds_bucket[5m])) by (le))",
        "p99": "histogram_quantile(0.99, sum(rate(rag_search_duration_seconds_bucket[5m])) by (le))",
    }

    print(f"Prometheus: {prom_url}")
    for k, q in queries.items():
        try:
            resp = query_prometheus(prom_url, q)
            result = resp.get("data", {}).get("result", [])
            value = result[0]["value"][1] if result else "N/A"
            print(f"{k.upper()} latency (s): {value}")
        except Exception as e:
            print(f"{k.upper()} query failed: {e}")


if __name__ == "__main__":
    main()
