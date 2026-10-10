"""Print OCR findings and estimated cost for one lab case.

Usage: python lab_show.py <path-to-ocr-json>
Prices: Fireworks DeepSeek V4.1 Flash list rates, USD per 1M tokens.
"""
import json
import sys

PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.22, 0.007, 0.66

d = json.load(open(sys.argv[1], encoding="utf-8"))
s = d.get("summary", {})
inp, cached, out = s.get("input_tokens", 0), s.get("cache_read_tokens", 0), s.get("output_tokens", 0)
cost = ((inp - cached) * PRICE_IN + cached * PRICE_CACHED + out * PRICE_OUT) / 1e6
print(f"status: {d.get('status')} | {d.get('message')}")
print(f"files: {s.get('files_reviewed')} | tokens: {s.get('total_tokens'):,} | time: {s.get('elapsed')} | est. cost: ${cost:.3f}")
for c in d.get("comments", []):
    print(f"\n--- {c['path']}:{c.get('start_line')} [{c.get('severity')}/{c.get('category')}]")
    print(c["content"])
    if c.get("suggestion_code"):
        print("suggested fix:\n" + c["suggestion_code"])
