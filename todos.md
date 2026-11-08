# FP2 To-Do

Checked against the current files on 2026-11-08.

## 1. Fix the scripts

### `scripts/check_corpus.py`: crashes on the current corpus
- [ ] It still expects the old field names. Running it gives `KeyError: 'case_id'` (line 85) because the corpus now uses the course template (`id` + `content`).
  - Read `id` instead of `case_id`.
  - `meeting_id`, `segments`, `candidate_action` and `evidence` are now inside `content`, so look them up there.
  - Update `REQUIRED` to match the template: `id, seeded_tier, seeded_rules, ambiguous, injection, generated_by, reviewed_by, content`, plus our extra metadata (`target_tier, ambiguity_type, scenario_family, generation_note, review_status`).
- [ ] Fix the label format. `LABEL_RE` accepts comma-separated rules (`T4 R4.1, R4.3`), but the course README and our README use spaces (`T4 R4.1 R4.3`). Change it to `^(none|T[1-4]( R\d\.\d)+)$`, and change the error message on line 67 to match.
- [ ] Add `generated_by`, `reviewed_by` and `review_status` to its `HIDDEN` set so the packet leak check matches `make_labeler_packet.py`, which now strips them.
- [ ] Check that `content` contains none of the hidden metadata (this is what keeps labels out of the agent's prompt).
- [ ] Optional: compute labeler A/B percent agreement and Cohen's kappa from `golden.csv` once both columns are filled (the README needs these numbers).
- [ ] Run it, fix any real errors, and paste the output into the README "Validation" section, which currently says `[TEAM TO COMPLETE]`.

### `scripts/make_labeler_packet.py`
- [ ] Rerun it once the corpus is final (after review corrections) so `labeling_packet_for_labelers.jsonl` matches `corpus.jsonl`. Check that each packet line holds only `id` and `content`.
- [ ] Small fix: it treats `--help` as a file path. Add a usage message or argparse.

### Course check script
- [ ] Rerun the snippet from `README_Corpus.md` (in `templates/*.zip`) after review. `not reviewed` must be 0.

## 2. Review all 122 cases (required before submission)
- [ ] Split the 122 cases among team members and review each one in `working/review_sheet.csv`. Fill in `reviewer`, `decision(keep/correct/discard)`, `corrected_label` and `review_notes`.
- [ ] Look closely at rows that have `audit_flags` set (doubts the generator reported).
- [ ] Apply the decisions to `corpus.jsonl`:
  - Fill in `reviewed_by` and set `review_status` to reviewed on every kept case.
  - Correct `seeded_tier`/`seeded_rules` where the reviewer changed the label.
  - Remove discarded cases.
- [ ] Make sure the corpus still meets the minimums after discards: ≥100 cases, ≥15% violating, all four tiers, ≥5 ambiguous, ≥2 injection. If not, generate replacement cases with `prompts/generate_cases.txt` and add their settings to `prompts/case_settings.jsonl`.
- [ ] If a discarded case is in the golden set, replace it in `golden.csv` (it still has to contain every ambiguous and injection case).
- [ ] README "Review" section: fill in the discarded cases, rejection rate and reviewers, and change Status from **pending**.

## 3. Label the golden set (39 cases)
- [ ] Labeler A labels the regenerated cases from `labeling_packet_for_labelers.jsonl` → `labeler_a` column. Format: `none` or `T<n> R<x.y>[ R<x.y>]`.
- [ ] Labeler B labels the same packet independently → `labeler_b`. **Do not open `working/labeler_a_v1_old_cases.csv`, `prompts/case_settings.jsonl`, `corpus.jsonl` or the review sheet first.**
- [ ] Settle disagreements by discussion: write the agreed label in `final` and the reason in `notes`.
- [ ] If a disagreement shows a rule is unclear, reword it in `policy.md`, bump the version (→ 1.3) and add a change log row.
- [ ] Compute percent agreement and Cohen's kappa and add them to the README "Validation" section.
- [ ] Where `final` differs from the seeded label, note it. The golden label is what the evaluation uses, per the course README.

## 4. Update `policy.md` with the changes since FP1
- [ ] Fill in the change log rows for 1.0 and 1.1 (dates, and what changed from 1.0 to 1.1). Both still say `[TEAM TO COMPLETE]`. Get these from the FP1 submission or its feedback.
- [ ] Check that every change since FP1 is listed. Possible ones: rules reworded after FP1 feedback, the multi-finding rule ("Several findings in one case"), global constraints moved into "How the rules are applied".
- [ ] Check `policy.md` against `FP2_policy_template.md` (in `templates/*.zip`) for missing sections.
- [ ] If the policy changes after the cases were generated, check whether any cases or labels depend on the changed wording.

## 5. Finish the README
- [ ] Replace every `[TEAM TO COMPLETE]` (Review, Validation, kappa).
- [ ] Update the validation counts if review changes the corpus.
- [ ] Update "Cases: 122 generated, 122 in `corpus.jsonl`" and the unused-ID list after discards.
- [ ] Mention `working/labeler_a_v1_old_cases.csv` and `prompts/case_settings.jsonl` in the Files table, or move them out of the submission.

## 6. Before submitting
- [ ] Decide which `working/` files to submit. `golden_ai_review_SEALED.md` and `golden_reveal_AFTER_LABELING.csv` are deleted in the working tree but still in git history. Make sure nothing AI-labeled gets submitted, since the README says no LLM supplies any label.
- [ ] Commit the current regeneration work. Commit `6da9b1c` is just "tmp", and many files have uncommitted changes.
- [ ] Final run of both checkers with no errors.
