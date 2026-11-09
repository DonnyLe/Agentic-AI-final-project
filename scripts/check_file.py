import json
from collections import Counter

cases = []
with open("corpus.jsonl") as f:
    for n, line in enumerate(f, 1):
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"line {n} is not valid JSON: {e}")
            raise SystemExit

seeded = [c for c in cases if c["seeded_tier"] != "none"]
print("cases:          ", len(cases), "(minimum 100)")
print("with violation: ", len(seeded), f"({len(seeded) / len(cases):.0%}, minimum 15%)")
print("by tier:        ", dict(Counter(c["seeded_tier"] for c in cases)))
print("ambiguous:      ", sum(c["ambiguous"] for c in cases), "(minimum 5)")
print("injection:      ", sum(c["injection"] for c in cases), "(minimum 2)")
print("not reviewed:   ", sum(not c["reviewed_by"] for c in cases), "(must be 0)")