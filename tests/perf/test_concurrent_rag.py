#!/usr/bin/env python3
"""
Quick performance test for RAG endpoint
Tests concurrent requests with proper thread_id handling
"""

import asyncio
import time
import uuid
from typing import List, Dict
import httpx
import statistics


async def test_rag_request(client: httpx.AsyncClient, user_num: int) -> Dict:
    """Send single RAG request and measure latency"""

    user_id = f"perf-user-{user_num}"
    thread_id = str(uuid.uuid4())
    query = "Triệu chứng của cúm là gì?"

    payload = {"user_identifier": user_id, "thread_id": thread_id, "query": query}

    start = time.time()
    try:
        response = await client.post("/v1/rag", json=payload, timeout=60.0)
        latency = (time.time() - start) * 1000  # ms

        if response.status_code == 200:
            data = response.json()
            has_response = bool(data.get("response"))
            return {
                "success": True,
                "latency_ms": latency,
                "status": response.status_code,
                "has_response": has_response,
            }
        else:
            return {
                "success": False,
                "latency_ms": latency,
                "status": response.status_code,
                "error": response.text[:200],
            }

    except Exception as e:
        latency = (time.time() - start) * 1000
        return {"success": False, "latency_ms": latency, "error": str(e)[:200]}


async def run_concurrent_test(num_users: int, base_url: str):
    """Run concurrent RAG requests"""

    print(f"\n{'='*60}")
    print(f"RAG Performance Test - {num_users} concurrent users")
    print(f"Base URL: {base_url}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(base_url=base_url) as client:
        # Warmup request
        print("🔥 Warming up...")
        await test_rag_request(client, 0)

        # Actual test
        print(f"🚀 Launching {num_users} concurrent requests...\n")
        start_time = time.time()

        tasks = [test_rag_request(client, i) for i in range(1, num_users + 1)]
        results = await asyncio.gather(*tasks)

        total_time = time.time() - start_time

        # Analyze results
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        latencies = [r["latency_ms"] for r in successful]

        print(f"⏱️  Total time: {total_time:.2f}s")
        print(f"✅ Successful: {len(successful)}/{num_users}")
        print(f"❌ Failed: {len(failed)}/{num_users}")

        if latencies:
            print(f"\n📊 Latency Statistics:")
            print(f"  Min:    {min(latencies):.0f}ms")
            print(f"  Max:    {max(latencies):.0f}ms")
            print(f"  Mean:   {statistics.mean(latencies):.0f}ms")
            print(f"  Median: {statistics.median(latencies):.0f}ms")
            if len(latencies) > 1:
                print(f"  StdDev: {statistics.stdev(latencies):.0f}ms")

            # Calculate percentiles
            sorted_lat = sorted(latencies)
            p50_idx = int(len(sorted_lat) * 0.50)
            p95_idx = int(len(sorted_lat) * 0.95)
            p99_idx = int(len(sorted_lat) * 0.99)

            print(f"\n📈 Percentiles:")
            print(f"  P50: {sorted_lat[p50_idx]:.0f}ms")
            print(f"  P95: {sorted_lat[p95_idx]:.0f}ms")
            print(f"  P99: {sorted_lat[p99_idx]:.0f}ms")

        if failed:
            print(f"\n⚠️  Failed requests:")
            for i, r in enumerate(failed[:3], 1):
                print(
                    f"  {i}. Status: {r.get('status', 'N/A')} - {r.get('error', 'Unknown')}"
                )

        print(f"\n{'='*60}")

        # Pass/Fail criteria
        success_rate = len(successful) / num_users
        if success_rate >= 0.95:
            print(f"✅ TEST PASSED - Success rate: {success_rate*100:.1f}%")
            return True
        else:
            print(
                f"❌ TEST FAILED - Success rate: {success_rate*100:.1f}% (threshold: 95%)"
            )
            return False


if __name__ == "__main__":
    import sys

    # Default config
    num_users = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

    passed = asyncio.run(run_concurrent_test(num_users, base_url))
    sys.exit(0 if passed else 1)
