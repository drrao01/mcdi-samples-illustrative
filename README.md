# MCDI Samples — Illustrative

Four mid-conversation developer instruction (MCDI) samples. In each one the developer
instructions change partway through the conversation, and the rubrics check whether the model
kept up.

- **Coding — payments service.** The team switches HTTP library partway through. Two turns later
  the model is still importing the old one, and reports it back as compliant.
- **Finance — quarterly board reporting.** Percentages must be whole numbers. Asked to show its
  working, the model rounds first and then subtracts, and the gap it reports is wrong.
- **Customer support — billing dispute.** The customer asks two questions in one message: one the
  agent can answer, one it cannot. It answers both.
- **Shopping — Wickfield & Co.** Two declared tools. Stock holds are suspended and a delivery
  charge is introduced in one instruction, just as the customer asks for a hold.

The first three are generated: the assistant text is real model output from a live run, and each
one fails at least one rubric. The shopping sample is **authored** — it exists to cover the tool
layer, which cannot currently be generated in our environment.

## Contents

| Path | What it is |
| --- | --- |
| `samples/<sample_id>/sample.json` | The eval item. Source of truth. |
| `samples/<sample_id>/files/` | Input files the task needs. Empty for these two. |
| `samples/<sample_id>/trajectories/` | Captured context turns, and the observed final-turn response. |
| `schema/mcdi_sample.schema.json` | JSON Schema for a sample. |
| `validate_mcdi.py` | Schema + semantic validation. AutoQC layer 0. |
| `build_samples.py` | Builds a sample from a Studio live chain + a rubric table. |
| `rubrics_coding.py`, `rubrics_finance.py` | The hand-authored rubric tables. |
| `render_page.py`, `index.html` | The rendered page. A **view** of the JSON, never a source. |

Regenerate everything with `python3 build_samples.py && python3 validate_mcdi.py && python3 render_page.py`.

## Sample format

```json
{
  "sample_id": "mcdi_coding_payments_001",
  "domain": "coding",
  "sample_type": "uncertified",
  "messages": [
    { "role": "developer | user | assistant | tool_declaration | tool_call | tool_response",
      "content": "...", "thought": true }
  ],
  "rubrics": [
    { "id": 1, "text": "...", "check": "...", "source": "SOURCE_DEVELOPER",
      "num_turn": 0, "expected_behavior": "BEHAVIOR_OVERRIDEN",
      "overriden_by": [6], "overriden_reason": "RECENCY" }
  ]
}
```

### The four things worth knowing

**It is an eval item, so it ends at the final user message.** The response under test is generated
at evaluation time and is not shipped inside the item. The response the model actually gave lives
in `trajectories/observed_final_turn.json` as evidence, not as an answer key.

**`text` and `check` do different jobs.** `text` is the instruction as written — it is the client's
field, and it carries provenance and supersession. `check` is the graded binary assertion, phrased
so that PASS always means correct behaviour. For an overridden rubric the check is the negation of
the instruction. Collapsing the two into one field makes `expected_behavior` incoherent: a check
already phrased as a negation, plus a flag saying "should not comply", reads as a double negative.

**`num_turn` is where the instruction originated, not where it is graded.** Every rubric here is
graded on the final turn. Earlier-turn rubrics are optional and none are included.

**Only `RECENCY` requires the overriding rule to come later.** Recency means "same tier, later
message wins". Every other reason is tier-based, so a developer rule from turn 0 legitimately
overrides a user request made at turn 3. The validator enforces this distinction.

## Certification

`sample_type` is assigned from measurement, never from intent. Samples stay `uncertified` until
they are run against **gemini-3.7-flash** — 5 runs; ≥3 rubric-set failures marks the sample
`loss_triggering`, 1–2 marks it `flaky`, 0 marks it `representative`. The historical grades stored
alongside each sample come from a single earlier run on a different model and are not a
certification.

## Rubric fields

Each rubric carries `id`, `text`, `source`, `num_turn`, `expected_behavior`, and where something
supersedes it, `overriden_by` and `overriden_reason`.

`expected_behavior` is `BEHAVIOR_SATISFIED` for a rule the model should follow, and
`BEHAVIOR_OVERRIDEN` for one a later instruction replaced — a correct run **fails** an overridden
rubric, because complying with a superseded rule is itself the error. `num_turn` records the turn
that introduced the instruction, not where it is checked; every rubric is graded on the final turn.
