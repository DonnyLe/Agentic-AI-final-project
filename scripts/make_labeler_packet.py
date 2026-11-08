"""Build the labelers' blind copy of the golden-set cases.

Usage: python3 scripts/make_labeler_packet.py [corpus.jsonl] [golden.csv] [out.jsonl]

Removes every generation-metadata field listed in README "Golden set" step 1,
plus review bookkeeping, so labelers see only the meeting, the candidate
action, and the evidence snapshot.
"""
import csv
import json
import sys

HIDDEN = {
    "seeded_tier", "seeded_rules", "target_tier", "ambiguous", "ambiguity_type",
    "injection", "scenario_family", "generation_note",
    "reviewed_by", "review_status",
}


def main(corpus="corpus.jsonl", golden="golden.csv", out="labeling_packet_for_labelers.jsonl"):
    with open(golden, newline="") as f:
        ids = [row["case_id"] for row in csv.DictReader(f)]
    cases = {}
    with open(corpus) as f:
        for line in f:
            if line.strip():
                c = json.loads(line)
                cases[c["case_id"]] = c
    missing = [i for i in ids if i not in cases]
    if missing:
        sys.exit(f"golden.csv IDs not in corpus: {missing}")
    with open(out, "w") as f:
        for i in ids:
            blind = {k: v for k, v in cases[i].items() if k not in HIDDEN}
            f.write(json.dumps(blind, ensure_ascii=False) + "\n")
    print(f"wrote {len(ids)} blind cases to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
