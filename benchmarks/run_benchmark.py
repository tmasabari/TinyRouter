import argparse
import csv
import json
import statistics
import time
import urllib.request
from pathlib import Path

EXPECTED = {"simple": "l1", "medium": "l1", "complex": "l2", "obvious_coding": "l2", "long_context": "l2"}


def prompt_for(item):
    if "repeat" not in item:
        return item["prompt"]
    block = " Context detail: The application uses HTTP services, a relational database, structured logging, retries, caching, authentication, configuration, and background processing. Evaluate these details as part of the stated task."
    return item["prompt"] + block * item["repeat"]


def chat(url, model, prompt, timeout, temperature=0, max_tokens=256):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": max_tokens}).encode()
    started = time.perf_counter()
    try:
        request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
            usage = payload.get("usage", {})
            return {"ok": True, "latency_ms": (time.perf_counter() - started) * 1000,
                    "model": payload.get("model", ""), "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0), "route": response.headers.get("X-TinyRouter-Route", ""),
                    "source": response.headers.get("X-TinyRouter-Source", ""),
                    "hops": int(response.headers.get("X-TinyRouter-Hops", 0)),
                    "escalation": response.headers.get("X-TinyRouter-Escalation", "false") == "true"}
    except Exception as error:
        return {"ok": False, "latency_ms": (time.perf_counter() - started) * 1000, "error": str(error)}


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["category"], []).append(row)
    summary = []
    for category, items in groups.items():
        router = [x for x in items if x["router_ok"]]
        baseline = [x for x in items if x["baseline_ok"]]
        l2_calls = sum(x["router_route"] == "l2" for x in router)
        expected = EXPECTED[category]
        summary.append({
            "category": category, "count": len(items), "expected_route": expected,
            "route_accuracy": sum(x["router_route"] == expected for x in router) / len(router) if router else 0,
            "baseline_avg_ms": statistics.mean(x["baseline_ms"] for x in baseline) if baseline else 0,
            "router_avg_ms": statistics.mean(x["router_ms"] for x in router) if router else 0,
            "l1_handled": sum(x["router_route"] == "l1" for x in router),
            "l1_escalated": sum(x["router_escalation"] for x in router),
            "l2_calls": l2_calls,
            "l2_calls_avoided": len(baseline) - l2_calls,
        })
    return summary


def main():
    parser = argparse.ArgumentParser(description="Benchmark L2 baseline versus TinyRouter")
    parser.add_argument("--dataset", default="benchmarks/test_set.json")
    parser.add_argument("--router", default="http://127.0.0.1:8090/v1/chat/completions")
    parser.add_argument("--l2", default="http://127.0.0.1:8082/v1/chat/completions")
    parser.add_argument("--l2-model", default="lfm2.5-8b-a1b")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out", default="benchmark-results")
    args = parser.parse_args()
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if len(dataset) != 50:
        raise ValueError(f"expected exactly 50 benchmark prompts, found {len(dataset)}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print("Warming up L2 and TinyRouter...")
    chat(args.l2, args.l2_model, "Reply with OK.", args.timeout, temperature=0.2, max_tokens=32)
    chat(args.router, "router", "Reply with OK.", args.timeout)
    rows = []
    for repeat in range(args.repeats):
        for index, item in enumerate(dataset, 1):
            prompt = prompt_for(item)
            print(f"[{repeat + 1}/{args.repeats}] {index:02d}/50 {item['category']:<16} {item['id']}")
            baseline = chat(args.l2, args.l2_model, prompt, args.timeout, temperature=0.2, max_tokens=2048)
            routed = chat(args.router, "router", prompt, args.timeout)
            rows.append({"id": item["id"], "category": item["category"], "repeat": repeat + 1, "prompt_chars": len(prompt),
                         "baseline_ok": baseline["ok"], "baseline_ms": baseline["latency_ms"],
                         "baseline_input_tokens": baseline.get("input_tokens", 0), "baseline_output_tokens": baseline.get("output_tokens", 0),
                         "router_ok": routed["ok"], "router_ms": routed["latency_ms"], "router_route": routed.get("route", ""),
                         "router_source": routed.get("source", ""), "router_hops": routed.get("hops", 0),
                         "router_escalation": routed.get("escalation", False), "router_input_tokens": routed.get("input_tokens", 0),
                         "router_output_tokens": routed.get("output_tokens", 0), "router_error": routed.get("error", "")})
    fields = list(rows[0])
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    summary = summarize(rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    routed_ok = [x for x in rows if x["router_ok"]]
    baseline_ok = [x for x in rows if x["baseline_ok"]]
    l2_calls = sum(x["router_route"] == "l2" for x in routed_ok)
    avoided = len(baseline_ok) - l2_calls
    print("\n=== TinyRouter benchmark ===")
    print(f"Requests:          {len(rows)}")
    print(f"L1 handled:        {sum(x['router_route'] == 'l1' for x in routed_ok)}")
    print(f"L1 escalated:      {sum(x['router_escalation'] for x in routed_ok)}")
    print(f"L2 calls:          {l2_calls}")
    print(f"L2 calls avoided:  {avoided} ({avoided / len(baseline_ok) * 100:.1f}%)" if baseline_ok else "L2 calls avoided:  n/a")
    print(f"Baseline avg ms:   {statistics.mean(x['baseline_ms'] for x in baseline_ok):.1f}" if baseline_ok else "Baseline avg ms:   n/a")
    print(f"Router avg ms:     {statistics.mean(x['router_ms'] for x in routed_ok):.1f}" if routed_ok else "Router avg ms:     n/a")
    print(f"Results:           {out / 'results.csv'}")
    print(f"Summary:           {out / 'summary.json'}")


if __name__ == "__main__":
    main()
