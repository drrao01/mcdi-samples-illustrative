#!/usr/bin/env python3
"""Export a Studio MCDI task + its live chain into the client's delivery envelope.

  messages[]  role: system | user | assistant   (system == the DEVELOPER tier)
  rubrics[]   id, text, source, num_turn, expected_behavior, overriden_by, overriden_reason

Turn numbering is 0-BASED, matching the client's own example (// Turn 0, // Turn 1).
Usage:  python3 export_mcdi.py <task_id> <final_trajectory_id> [out.json]
"""
import json, subprocess, os, re, sys

S = os.path.expanduser("~/.config/rls-studio/studio.sh")
def get(p):
    return json.loads(subprocess.run([S,"GET",p],capture_output=True,text=True).stdout)

HARNESS_PREFIX = "You are an AI agent that will be given a specific task"

def build_messages(final_traj):
    """Flatten the chain's final trajectory into the delivery message list.
    A live chain's final trajectory carries the whole conversation, so one read is enough."""
    msgs=[]
    for m in get(f"/trajectories/{final_traj}")["trajectory_messages"]:
        role, c = m.get("role"), m.get("content")
        if not isinstance(c,str) or not c.strip(): continue
        if role=="system":
            if c.startswith(HARNESS_PREFIX):     continue     # orchestrator scaffolding, not data
            msgs.append({"role":"system","content":c})        # DEVELOPER tier
        elif role=="user":
            msgs.append({"role":"user","content":c})
        elif role=="tool" and len(c)>40 and not c.strip().startswith('[{"text"'):
            msgs.append({"role":"assistant","content":c})     # the finish-tool payload is the reply
    return msgs

def turn_index(msgs):
    """0-based turn number for each message. A turn opens at a developer/user block and
    closes after the assistant reply, matching the client's // Turn N comments."""
    idx=[]; t=0; seen_user=False
    for m in msgs:
        if m["role"]in("system","user") and seen_user:
            t+=1; seen_user=False
        if m["role"]=="user": seen_user=True
        idx.append(t)
    return idx

META_KEYS=["source","num_turn","rule","expected_behavior","overriden_by","overriden_reason","note"]
def parse_meta(expl):
    out={}
    for part in re.split(r"\|", expl or ""):
        m=re.match(r"\s*([a-z_]+)\s*=\s*(.*)$", part.strip())
        if m and m.group(1) in META_KEYS: out[m.group(1)]=m.group(2).strip()
    return out

def build_rubrics(task_id):
    vs=get(f"/verifiers/task/{task_id}")["verifiers"]
    rubrics=[]; by_rule={}
    for v in sorted(vs,key=lambda z:z["verifier_index"]):
        meta=parse_meta(v["verifier_values"].get("criteria_explanation",""))
        rid=v["verifier_index"]
        if meta.get("rule"): by_rule.setdefault(meta["rule"],rid)
        rubrics.append({"id":rid,
            "text":v["verifier_values"].get("criteria","").strip(),
            "source":meta.get("source","SOURCE_DEVELOPER"),
            "num_turn":int(meta["num_turn"]) if meta.get("num_turn","").isdigit() else 0,
            "expected_behavior":meta.get("expected_behavior","BEHAVIOR_SATISFIED"),
            "_rule":meta.get("rule"), "_overriden_by_rule":meta.get("overriden_by"),
            "overriden_reason":meta.get("overriden_reason"), "_note":meta.get("note")})
    # resolve overriden_by from rule name -> rubric id, per the spec's list-of-rubrics shape
    for r in rubrics:
        ob=r.pop("_overriden_by_rule"); r.pop("_rule",None); note=r.pop("_note",None)
        r["overriden_by"]=[by_rule[ob]] if ob and ob in by_rule else []
        if not r["overriden_by"]: r.pop("overriden_reason",None) if r.get("overriden_reason") is None else None
        if r.get("overriden_reason") is None: r.pop("overriden_reason",None)
        if note: r["_authoring_note"]=note
    return rubrics

def export(task_id, final_traj):
    t=get(f"/tasks/{task_id}")
    msgs=build_messages(final_traj)
    turns=turn_index(msgs)
    for m,ti in zip(msgs,turns): m["_turn"]=ti
    mcdi=[i for i,m in enumerate(msgs) if m["role"]=="system" and turns[i]>0]
    return {
      "sample_id": task_id,
      "name": t["task_name"],
      "messages": [{"role":m["role"],"content":m["content"]} for m in msgs],
      "rubrics": build_rubrics(task_id),
      "metadata": {
        "turn_count": max(turns)+1,
        "mcdi_count": len(mcdi),
        "mcdi_message_indices": mcdi,
        "turn_of_each_message": turns,
        "tier_mapping": {"system_role_in_this_file":"DEVELOPER tier",
                         "user_role_in_this_file":"USER tier",
                         "google_internal_system_instruction":"SYSTEM tier - not authored here"},
        "turn_indexing":"0-based, matching the client's // Turn 0 / // Turn 1 example",
        "generation":"live chain, one API call per turn; assistant text is generated, not authored",
        "source_world":"world_983e6879ef494edf912f9c9042cc112a",
      }}

if __name__=="__main__":
    if len(sys.argv)<3: sys.exit(__doc__)
    d=export(sys.argv[1],sys.argv[2])
    out=sys.argv[3] if len(sys.argv)>3 else f"{sys.argv[1][:16]}.json"
    json.dump(d,open(out,"w"),indent=2,ensure_ascii=False)
    print(f"wrote {out}: {len(d['messages'])} messages, {len(d['rubrics'])} rubrics, "
          f"{d['metadata']['turn_count']} turns, {d['metadata']['mcdi_count']} MCDI")
