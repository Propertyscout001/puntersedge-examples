#!/usr/bin/env python3
"""Refresh openapi-subset.json from the public schema (no key needed). Run, then re-run each
starter's tests: a failing contract test means the API renamed or removed a field a starter reads."""
import json
import os
import urllib.request

URL = "https://api.puntersedge.online/openapi.json"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "openapi-subset.json")


def main():
    with urllib.request.urlopen(URL, timeout=30) as fh:
        spec = json.load(fh)
    C = spec["components"]["schemas"]
    current = json.load(open(OUT))
    for path, entry in current["paths"].items():
        op = spec["paths"][path]["get"]
        entry["query"] = sorted(p["name"] for p in op.get("parameters", []) if p.get("in") == "query")
        sch = op["responses"]["200"]["content"]["application/json"].get("schema", {})
        ref = sch.get("$ref") or (sch.get("items") or {}).get("$ref")
        if ref:
            entry["fields"] = list(C[ref.split("/")[-1]]["properties"])
    json.dump(current, open(OUT, "w"), indent=1)
    print("refreshed", OUT)


if __name__ == "__main__":
    main()
