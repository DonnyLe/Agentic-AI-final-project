# FP2 submission checklist

Checked against the current files and the assignment instructions on 2026-11-08.

## Completed in the current files

- [x] Corpus contains 122 cases, including 88 violating cases (72.1%), all four tiers, 15 ambiguous cases, and 8 injection cases.
- [x] Every corpus case has `reviewed_by` filled in and `review_status: "reviewed"`.
- [x] Golden set contains 39 cases, including every ambiguous and injection case.
- [x] Both labeler columns and final labels are filled for all 39 golden cases.
- [x] Blind labeling packet contains only `id` and `content` fields.
- [x] Policy contains 14 rules across four tiers and is version 1.3.
- [x] Internal checker supports the current corpus schema and space-separated labels.
- [x] `scripts/make_labeler_packet.py` supports argparse and `--help`.
- [x] `python3 scripts/check_corpus.py` returns PASS.
- [x] `python3 scripts/check_file.py` reports that all corpus minimums are met and no cases lack a reviewer.

These checks verify recorded completion and file structure. The team must confirm that the required human review and independent labeling actually happened.

## 1. Finish the architecture report

- [ ] Update policy references from v1.2 to v1.3, including Appendix A, and describe the R2.1 clarification about evidence for expected behavior.
- [ ] Clarify that the Supervisor alone adjudicates policy while specialists receive relevant clauses. Remove the conflicting claim that it is the only agent that reads policy.
- [ ] Add corpus counts and agreement results wherever the assignment requests them: 33/39 exact-label agreement (84.6%) and Cohen's kappa 0.826. Recompute if labels change.
- [ ] Remove assignment prompts, placeholders, and editing notes from the final report.

## 2. Validate and submit

- [ ] Create `Group3_FP2_corpus.zip` containing these required files at its root:
  - `policy.md`
  - `corpus.jsonl`
  - `golden.csv`
  - `README.md`
- [ ] Recommended: also include `prompts/generate_cases.txt`, since the README describes it as the generation prompt.
- [ ] Inspect the ZIP contents. Do not include `.git/`, old labels, `working/`, templates, or unrelated repository files.
- [ ] Submit the architecture PDF and corpus ZIP through the course's submission interface.
