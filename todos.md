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

## 1. Finish human review documentation

- [ ] Confirm that every case was reviewed by hand and every golden case was labeled independently by two team members using only the policy and blind case content, without seeded labels or each other's labels.
- [ ] Replace the generic reconciliation notes for K-051, K-063, K-110, K-115, K-116, and K-125 in `golden.csv` with the team's actual reasons. Each note should identify the decisive evidence and policy interpretation; "Reconciled to none" records an outcome but not a reason.
- [ ] If those discussions require a policy change, update its version and change log, then revisit affected cases and labels.

## 2. Finish policy history

- [ ] Replace the `[TEAM TO COMPLETE]` placeholders in the version 1.0 and 1.1 change log rows in `policy.md` with real dates and changes from the team's records.
- [ ] Check that the report's description of changes since FP1 matches the completed change log.

## 3. Finish the architecture report

- [ ] Update policy references from v1.2 to v1.3, including Appendix A, and describe the R2.1 clarification about evidence for expected behavior.
- [ ] Include the actual architecture diagram in the PDF, not just its caption or an editable-diagram link. Show agents, MCP/tools, external sources, precedent retrieval, persistence, the reviewer interface, approval boundaries, and enforcement actions.
- [ ] Explicitly state that no third-party MCP services are planned for the core prototype, if that remains the plan.
- [ ] Clarify that the Supervisor alone adjudicates policy while specialists receive relevant clauses. Remove the conflicting claim that it is the only agent that reads policy.
- [ ] Replace the claim that hidden instructions have "no way" to reach the Action Agent with a narrower explanation: restricted inputs, tool permissions, and backend approval checks reduce the risk, but upstream proposals can still be influenced by untrusted content.
- [ ] Check the full assignment template for section 9 or any other reporting fields missing from the pasted report, which ends at section 6 before the appendix.
- [ ] Add corpus counts and agreement results wherever the assignment requests them: 33/39 exact-label agreement (84.6%) and Cohen's kappa 0.826. Recompute if labels change.
- [ ] Remove assignment prompts, placeholders, and editing notes from the final report.

The pasted instructions require an architecture design, policy, corpus, and golden set, not a completed agent implementation. The separate precedent history is part of the proposed architecture; those instructions do not explicitly require submitting it as an extra file.

## 4. Finish the README

- [ ] Add exact-label agreement (33/39, 84.6%) and Cohen's kappa (0.826) to the Validation section, updating them if labels change.
- [ ] Keep generation, review, discard counts, policy version, and labeling claims consistent with what the team actually did.
- [ ] Make the Files table match the ZIP contents, or clearly distinguish submission files from repository-only helpers. Include the generation prompt if retaining its reference as a supplied file.

## 5. Validate and submit

- [ ] Rerun `python3 scripts/check_corpus.py` and `python3 scripts/check_file.py` after the final edits.
- [ ] The supplied `README_Corpus.md` contains one checking snippet, reproduced in `scripts/check_file.py`; the assignment mentions two. Check whether the course provides a separate agreement checker elsewhere. The internal checker already computes agreement, but is not an official course checker.
- [ ] Export the architecture report as a well-formatted PDF. Suggested filename: `Group3_FP2_Architecture.pdf`.
- [ ] Inspect the exported PDF for diagram readability, table wrapping, page breaks, and leftover prompts or placeholders.
- [ ] Create `Group3_FP2_corpus.zip` containing these required files at its root:
  - `policy.md`
  - `corpus.jsonl`
  - `golden.csv`
  - `README.md`
- [ ] Recommended: also include `prompts/generate_cases.txt`, since the README describes it as the generation prompt.
- [ ] Inspect the ZIP contents. Do not include `.git/`, old labels, `working/`, templates, or unrelated repository files.
- [ ] Submit the architecture PDF and corpus ZIP through the course's submission interface.
