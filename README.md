# Group 3 — Kangaroo: FP2 Corpus

## Files

| File | Contents |
|------|----------|
| `policy.md` | Meeting-to-Action Policy v1.1 (14 rules, 4 tiers) |
| `corpus.jsonl` | Generated cases, one JSON object per line |
| `golden.csv` | Golden-set case IDs with columns `labeler_a`, `labeler_b`, `final`, `notes` |
| `labeling_packet_for_labelers.jsonl` | Blind copy of the 39 golden cases with all generation metadata and review fields removed (built by `scripts/make_labeler_packet.py`) |
| `scripts/check_corpus.py` | Internal consistency checker for the FP2 requirements stated in our F2 (not the course's official checking scripts) |

## How the cases were generated

Cases were produced by a script from hand-written scenario templates (one family per rule or situation). This differs from the FP1/F2 plan: no generation model rendered the transcripts or added disfluencies, so each case is a short 2–4 segment exchange focused on a single candidate action, not an excerpt from an 8–25 minute meeting. Each case is its own meeting (`meeting_id` M-001 to M-127, matching the case number). Each template is varied across a fixed set of 12 defect scenarios, a 12-person roster, and four components (checkout, search, auth, jobs). Every case embeds its own evidence snapshot (roster entries, ticket records, calendar availability, repository/test results, and package-registry lookups), so a label can be decided from the case alone.

- **Generation tool / model family:** Claude Opus 5.5 (Anthropic, Claude family) wrote the scenario templates, the generator script and the resulting cases. Per FP1 this must differ from the agent's model family.
- **Cases:** see counts below. [TEAM TO CONFIRM after review]
- **Case fields:** `seeded_tier`, `seeded_rules`, `ambiguous`, `ambiguity_type`, `injection`, `scenario_family`, and `generation_note` are generation metadata. They must never enter the agent's prompt or the retrieval index.
- **A case counts as a violation** when carrying out the candidate action exactly as requested in the transcript would break one or more rules. Clean cases are genuinely compliant. `seeded_rules: []` means no violation. `target_tier` is the action class, stored separately from the violation label.

## Review

Every case must be reviewed by a team member, who then corrects or discards it.

- Before human review, an AI assistant (Claude) corrected generator data bugs in 33 cases without changing any label, flag, family or candidate action. It added missing speakers to `evidence.roster` (K-024, K-045–053, K-067–071, K-095–100), replaced a duplicated attendee name and added that person's availability (K-062, K-064, K-066), changed a duplicated component to a real second one (K-091), corrected GMT to BST for spring/summer London times (K-021–025 notes, K-072, K-074, K-076), moved a Friday meeting so "tomorrow" is a weekday (K-073), and filled in the roster matches for a group reference (K-071). Human reviewers still decide every label.
- `reviewed_by` is empty and `review_status` is `pending_human_review` on every case. Reviewers fill these in after reading each case.
- An AI first pass (Claude Opus 5.5) of the 88 non-golden cases is in `working/review_sheet.csv`, columns `ai_first_pass`, `ai_suggested_label` and `ai_notes`: 46 keep, 31 keep with a minor fix, 11 correct. These are suggestions only. The human columns (`reviewer`, `decision`, `corrected_label`, `review_notes`) stay blank until a team member reviews each case. The 39 golden cases are covered by `working/golden_ai_review_SEALED.md` instead, so labelers stay blind.
- Cases discarded: [TEAM TO COMPLETE]. Rejection rate: [TEAM TO COMPLETE].
- Reviewers: [TEAM TO COMPLETE]

## Golden set

The golden set contains every ambiguous case and every injection case, plus two sampled cases for each tier and violation status (clean/violating) combination. It is selected by `case_id` in `golden.csv`.

1. Remove `seeded_tier`, `seeded_rules`, `target_tier`, `ambiguous`, `ambiguity_type`, `injection`, `scenario_family`, and `generation_note` from the labelers' copy.
2. Two team members label each case independently using only the policy and the case, and enter labels as `none` or `T<n> R<x.y>[, R<x.y>]` in `labeler_a` and `labeler_b`.
3. Reconcile disagreements by discussion, record the reason in `notes`, and enter the agreed label in `final`.
4. If a disagreement shows a rule is unclear, reword it and bump the policy version.

No LLM supplies any label. `golden.csv` is intentionally unlabeled until the team completes.

## Splits and leakage

`scenario_family` names the generating template (25 families, e.g. `t2-r22`, `amb`, `inj`). Variants within a family are near-identical, so the seed-precedent history and the evaluation set must be split by family, never by case. Evaluation cases and labels stay out of the precedent index.

## Validation

[TEAM TO COMPLETE: paste the output of both checking scripts from `FP2_corpus_template_README
.md`, and the agreement statistics.]
