"""Build the labelers' blind copy of the golden-set cases.

Usage: python3 scripts/make_labeler_packet.py [corpus.jsonl] [golden.csv] [out.jsonl]

Keeps only `id` and `content` for each golden case (README "Golden set" step 1),
so labelers see only the meeting, the candidate action, and the evidence
snapshot. Generation metadata and review bookkeeping are dropped.
"""
import argparse
import csv
import json
import sys


def main(corpus, golden, out):
    with open(golden, newline="") as f:
        ids = [row["case_id"] for row in csv.DictReader(f)]
    cases = {}
    with open(corpus) as f:
        for line in f:
            if line.strip():
                c = json.loads(line)
                cases[c["id"]] = c
    missing = [i for i in ids if i not in cases]
    if missing:
        sys.exit(f"golden.csv IDs not in corpus: {missing}")
    no_content = [i for i in ids if "content" not in cases[i]]
    if no_content:
        sys.exit(f"golden cases with no content: {no_content}")
    with open(out, "w") as f:
        for i in ids:
            blind = {"id": i, "content": cases[i]["content"]}
            f.write(json.dumps(blind, ensure_ascii=False) + "\n")
    print(f"wrote {len(ids)} blind cases to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the labelers' blind packet of golden-set cases.")
    parser.add_argument("corpus", nargs="?", default="corpus.jsonl")
    parser.add_argument("golden", nargs="?", default="golden.csv")
    parser.add_argument("out", nargs="?", default="labeling_packet_for_labelers.jsonl")
    args = parser.parse_args()
    main(args.corpus, args.golden, args.out)
