#!/usr/bin/env python3
"""
Network diagnostic — run from inside the Docker container.

Usage:
    docker compose exec app python scripts/network_check.py

Shows which host address can reach the LLM server from inside Docker.
Run this on every new deployment environment to find the correct LLM_HOST value.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axonri_core.utils.network import run_network_check

port = int(os.environ.get("LLM_PORT", "8080"))
current = os.environ.get("LLM_HOST", "not configured")

print(f"\nAxonri — Network Diagnostic")
print(f"LLM port: {port}")
print(f"Current LLM_HOST: {current}")
print("-" * 50)

results = run_network_check(port)
working = []

for label, info in results.items():
    host = info["host"]
    if host == "N/A":
        print(f"  ✗  {label}: N/A")
        continue
    ok = info["reachable"]
    symbol = "✓" if ok else "✗"
    note = f"  ({info.get('error','')[:50]})" if not ok else ""
    print(f"  {symbol}  {label} ({host}:{port}){note}")
    if ok:
        working.append(host)

print("-" * 50)
if working:
    recommended = working[0]
    print(f"\n✓ Recommended: LLM_HOST={recommended}")
    if recommended != current:
        print(f"  Current value ({current}) differs — update docker-compose.yml")
        print(f"  or set: LLM_HOST_DETECT=auto to auto-detect on startup")
else:
    print("\n✗ LLM not reachable from any candidate host.")
    print("  Is llama.cpp or Ollama running on the host machine?")
    print(f"  Check: curl http://localhost:{port}/v1/models")
    sys.exit(1)
