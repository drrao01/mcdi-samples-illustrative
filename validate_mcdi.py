#!/usr/bin/env python3
"""Validate MCDI eval samples against the schema plus the semantic rules the schema can't express.

Usage:  python3 validate_mcdi.py samples/*/sample.json
Exit 0 = all clean. Exit 1 = at least one ERROR. WARNs never fail the run.

This is AutoQC layer 0: every check here is deterministic and runs before a sample is
eligible for the model run that certifies it representative vs loss-triggering.
"""
import json, sys, glob, os

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema", "mcdi_sample.schema.json")
NEG = ("not ", "no ", "never", "does not", "refus", "decline", "without", "avoid", "n't")


def schema_check(doc, errs):
    try:
        import jsonschema
    except ImportError:
        errs.append(("WARN", "jsonschema not installed - structural check skipped (pip install jsonschema)"))
        return
    v = jsonschema.Draft202012Validator(json.load(open(SCHEMA)))
    for e in sorted(v.iter_errors(doc), key=lambda z: list(z.path)):
        errs.append(("ERROR", f"schema: {'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"))


def turn_map(msgs):
    """0-based turn per message. A turn opens at the developer/user block and closes after
    the assistant answer, matching the client's // Turn N comments."""
    out, t, seen_user = [], 0, False
    for m in msgs:
        if m["role"] in ("developer", "user") and seen_user:
            t += 1
            seen_user = False
        if m["role"] == "user":
            seen_user = True
        out.append(t)
    return out


def check_sample(path):
    errs = []
    doc = json.load(open(path))
    schema_check(doc, errs)

    msgs = doc.get("messages", [])
    rubs = doc.get("rubrics", [])
    turns = turn_map(msgs)
    last_turn = max(turns) if turns else 0

    # --- eval-set shape -------------------------------------------------
    if msgs and msgs[-1]["role"] != "user":
        errs.append(("ERROR", f"eval item must end at the final user message, ends at '{msgs[-1]['role']}'. "
                              "The graded response is generated at eval time and must not be shipped."))

    # --- at least one MCDI (hard requirement 1) -------------------------
    mcdi_idx = [i for i, m in enumerate(msgs) if m["role"] == "developer" and turns[i] > 0]
    if not mcdi_idx:
        errs.append(("ERROR", "no MCDI: sample needs at least one developer message after turn 0"))

    # --- order-diagnostic attestation (hard requirement 2) --------------
    adjacent = [i for i in mcdi_idx if i + 1 < len(msgs) and msgs[i + 1]["role"] == "user"]
    if adjacent and not doc.get("metadata", {}).get("order_diagnostic_reviewed"):
        errs.append(("ERROR", f"MCDI at message index {adjacent} immediately precedes a user message; "
                              "set metadata.order_diagnostic_reviewed=true once a human has confirmed "
                              "the pair is order-diagnostic"))

    # --- rubric ids -----------------------------------------------------
    ids = [r["id"] for r in rubs]
    if len(set(ids)) != len(ids):
        errs.append(("ERROR", f"duplicate rubric ids: {sorted({i for i in ids if ids.count(i) > 1})}"))
    if ids and sorted(ids) != list(range(len(ids))):
        errs.append(("WARN", f"rubric ids are not contiguous 0..{len(ids)-1}: {sorted(ids)}"))
    known = set(ids)

    for r in rubs:
        rid, ob = r["id"], r.get("overriden_by") or []
        beh, reason = r["expected_behavior"], r.get("overriden_reason")

        # supersession coherence - the whole point of the spec
        if beh == "BEHAVIOR_OVERRIDEN":
            if not ob:
                errs.append(("ERROR", f"rubric {rid}: BEHAVIOR_OVERRIDEN with empty overriden_by"))
            if not reason:
                errs.append(("ERROR", f"rubric {rid}: BEHAVIOR_OVERRIDEN requires overriden_reason"))
        else:
            if ob:
                errs.append(("ERROR", f"rubric {rid}: BEHAVIOR_SATISFIED must not set overriden_by {ob}"))
            if reason:
                errs.append(("ERROR", f"rubric {rid}: BEHAVIOR_SATISFIED must not set overriden_reason"))

        for o in ob:
            if o not in known:
                errs.append(("ERROR", f"rubric {rid}: overriden_by references unknown rubric {o}"))
            elif o == rid:
                errs.append(("ERROR", f"rubric {rid}: overriden_by references itself"))
            else:
                other = next(x for x in rubs if x["id"] == o)
                # Recency is the only reason that REQUIRES the overrider to come later: it means
                # "same tier, later message wins". Every other reason is tier-based, so a developer
                # rule from turn 0 may legitimately override a user request made at turn 3.
                if reason == "RECENCY" and other["num_turn"] < r["num_turn"]:
                    errs.append(("ERROR", f"rubric {rid} (turn {r['num_turn']}) claims RECENCY override by "
                                          f"rubric {o} from the EARLIER turn {other['num_turn']}"))
                if reason == "RECENCY" and other["source"] != r["source"]:
                    errs.append(("ERROR", f"rubric {rid}: RECENCY requires same tier, but {r['source']} "
                                          f"is overridden by {o} ({other['source']}) - pick a tier-based reason"))
                if rid in (other.get("overriden_by") or []):
                    errs.append(("ERROR", f"rubrics {rid} and {o} override each other"))

        if r["num_turn"] > last_turn:
            errs.append(("ERROR", f"rubric {rid}: num_turn {r['num_turn']} exceeds last turn {last_turn}"))

        # check phrasing - PASS must always mean correct behaviour
        if beh == "BEHAVIOR_OVERRIDEN" and not any(n in r["check"].lower() for n in NEG):
            errs.append(("WARN", f"rubric {rid}: overridden rubric whose check reads as an affirmative "
                                 f"assertion - confirm PASS still means correct: {r['check'][:70]!r}"))

    # --- tools ----------------------------------------------------------
    declared = {m["tool_description"]["name"] for m in msgs
                if m["role"] == "tool_declaration" and m.get("tool_description", {}).get("name")}
    called = [m.get("tool_name") for m in msgs if m["role"] == "tool_call"]
    for c in set(called):
        if c not in declared:
            errs.append(("ERROR", f"tool_call to undeclared tool '{c}'"))
    open_calls = [m.get("tool_call_id") for m in msgs if m["role"] == "tool_call"]
    responded = {m.get("tool_call_id") for m in msgs if m["role"] == "tool_response"}
    for cid in open_calls:
        if cid not in responded:
            errs.append(("WARN", f"tool_call {cid} has no matching tool_response"))
    if declared and not any(r["source"] == "SOURCE_TOOL" for r in rubs):
        errs.append(("WARN", "tools are declared but no rubric has source SOURCE_TOOL"))

    # --- corpus-shape signals (never fatal) -----------------------------
    if not any(r["expected_behavior"] == "BEHAVIOR_OVERRIDEN" for r in rubs):
        errs.append(("WARN", "no rubric is BEHAVIOR_OVERRIDEN - sample exercises no supersession"))
    if doc.get("sample_type") == "uncertified":
        errs.append(("WARN", "sample_type is 'uncertified' - not yet eligible for delivery"))
    return errs


def main(paths):
    total_err = 0
    for p in paths:
        errs = check_sample(p)
        ne = sum(1 for lvl, _ in errs if lvl == "ERROR")
        total_err += ne
        status = "FAIL" if ne else "ok"
        print(f"[{status}] {p}")
        for lvl, msg in errs:
            print(f"    {lvl}: {msg}")
    print(f"\n{len(paths)} sample(s), {total_err} error(s)")
    return 1 if total_err else 0


if __name__ == "__main__":
    args = sys.argv[1:] or sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "samples", "*", "sample.json")))
    if not args:
        sys.exit("no samples found")
    sys.exit(main(args))
