# MCDI Samples — Illustrative

Two illustrative examples of mid-conversation developer instruction (MCDI) samples.

Each example is a four-turn conversation in which the developer instructions change partway
through, followed by the rubrics that check whether the model kept up. They show the shape of a
sample; they are not a report of results.

- **Coding — payments service.** The HTTP library changes at turn 1 and credential handling moves
  to a vault at turn 2. The vault rule does not matter until turn 3, when a secret first comes up.
  That same turn asks for two things the team rules do not allow, plus one they do.
- **Finance — quarterly board reporting.** The number format changes at turn 1 and source tagging
  is added at turn 2. The user then asks for a figure nobody supplied and tells the model to guess.
  Turn 3 asks for all of it inside a word limit.

## Contents

| Path | What it is |
| --- | --- |
| `index.html` | The rendered page. Open it directly or via Pages. |
| `samples/sample_coding.json` | Coding sample in the delivery envelope. |
| `samples/sample_finance.json` | Finance sample in the delivery envelope. |
| `export_mcdi.py` | Builds the delivery envelope from a source task and its conversation. |

## Sample format

```json
{
  "messages": [ { "role": "system | user | assistant", "content": "..." } ],
  "rubrics":  [ { "id": 0, "text": "...", "source": "...", "num_turn": 1 } ]
}
```

`system` carries the developer instructions, including the ones added mid-conversation. Turn
numbering is zero-based.

**Rubrics are graded on the final turn.** Each one checks the last response — both that it is
correct on its own terms and that it still honours developer instructions set earlier in the
conversation. `num_turn` records which turn introduced the instruction a rubric enforces, not where
it is checked. Rubrics that grade an intermediate turn are optional and none are included here.

Every rubric is written so that a model doing the right thing passes it. Where a rubric can stop
applying — because a later instruction replaced it, or because the turn being graded does not touch
it — the rubric says so explicitly, so correct behaviour is never scored as a failure.
