#!/usr/bin/env python3
"""Build canonical MCDI eval samples from a Studio live chain + a hand-authored rubric table.

  live chain (real Gemini output, thoughts, tool calls)
      -> samples/<sample_id>/sample.json          the eval item: ends at the final USER turn
      -> samples/<sample_id>/trajectories/        captured context turns + the observed final turn
      -> samples/<sample_id>/files/               input files (none for these two)

Roles are the client's: developer / user / assistant / tool_declaration / tool_call / tool_response.
Studio has no native `developer` role (role:"developer" -> HTTP 422), so system-role messages in a
Studio task carry the DEVELOPER tier and are mapped to `developer` here, at export.

Usage:  python3 build_samples.py            (uses the cached trajectory dumps)
"""
import json, os, ast, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("MCDI_TRAJ_CACHE", "/private/tmp/claude-501/-Users-dhairyarao/"
                       "d167991c-3402-429d-9b9b-d2a17e4b04ea/scratchpad")
HARNESS_PREFIX = "You are an AI agent that will be given a specific task"

# Tools that were genuinely available in the environment and used by the model.
# `finish` is harness scaffolding - its `reason` argument IS the assistant's answer - so it is
# unwrapped into the assistant message rather than shipped as a tool call.
TOOL_DECLS = [
    {"name": "filesystem_list_files",
     "description": "List the files available in the task workspace.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "filesystem_search_files",
     "description": "Search the task workspace for files matching a glob pattern.",
     "parameters": {"type": "object",
                    "properties": {"pattern": {"type": "string",
                        "description": "Glob pattern to match against file paths."}},
                    "required": ["pattern"]}},
    {"name": "code_execution_code_exec",
     "description": "Execute a shell command or code snippet in a sandboxed environment and "
                    "return its stdout, stderr and exit status. Has no network access.",
     "parameters": {"type": "object",
                    "properties": {"request": {"type": "object",
                        "description": "The execution request.",
                        "properties": {"code": {"type": "string",
                            "description": "The code or shell command to execute."}},
                        "required": ["code"]}},
                    "required": ["request"]}},
]


def unwrap(content):
    """Studio tool payloads arrive either as a real [{'text': ..., 'type': 'text'}] list or as a
    repr of one. Both flatten to plain text; the schema requires tool_response.content to be a string."""
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    if content is None:
        return None
    if not isinstance(content, str):
        return json.dumps(content, ensure_ascii=False)
    s = content.strip()
    if s.startswith("[{"):
        for loader in (json.loads, ast.literal_eval):
            try:
                parts = loader(s)
                return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)) or s
            except Exception:
                continue
    return content


def to_messages(traj_messages):
    """Flatten a Studio trajectory into the client's message vocabulary."""
    out, skip_next_tool = [], False
    for m in traj_messages:
        role, content = m.get("role"), m.get("content")
        if role == "system":
            if isinstance(content, str) and content.startswith(HARNESS_PREFIX):
                continue                                   # orchestrator scaffolding, not data
            out.append({"role": "developer", "content": content})
        elif role == "user":
            out.append({"role": "user", "content": content})
        elif role == "assistant":
            rc = m.get("reasoning_content")
            if rc:
                out.append({"role": "assistant", "thought": True, "content": rc})
            for call in (m.get("tool_calls") or []):
                fn = call.get("function") or {}
                name, raw = fn.get("name"), fn.get("arguments")
                try:
                    args = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except Exception:
                    args = {"_raw": raw}
                if name == "finish":
                    out.append({"role": "assistant", "content": args.get("reason", "")})
                    skip_next_tool = True                  # the echo carries no new information
                else:
                    out.append({"role": "tool_call", "tool_name": name,
                                "tool_call_id": call.get("id"), "arguments": args})
        elif role == "tool":
            if skip_next_tool:
                skip_next_tool = False
                continue
            out.append({"role": "tool_response", "tool_call_id": m.get("tool_call_id"),
                        "content": unwrap(content)})
    return out


def split_at_final_user(msgs):
    """An eval item stops at the last user turn; the graded response is produced at eval time.
    Everything after it is the OBSERVED response, kept for certification, not for delivery."""
    last_user = max(i for i, m in enumerate(msgs) if m["role"] == "user")
    return msgs[:last_user + 1], msgs[last_user + 1:]


def turn_map(msgs):
    out, t, seen_user = [], 0, False
    for m in msgs:
        if m["role"] in ("developer", "user") and seen_user:
            t += 1
            seen_user = False
        if m["role"] == "user":
            seen_user = True
        out.append(t)
    return out


def build(sample_id, name, domain, traj_file, rubrics, known_issues, grades_key=None):
    traj = json.load(open(os.path.join(CACHE, traj_file)))
    msgs = to_messages(traj["trajectory_messages"])

    # declare the tools immediately after the opening developer block
    first_user = next(i for i, m in enumerate(msgs) if m["role"] == "user")
    decls = [{"role": "tool_declaration", "tool_description": d} for d in TOOL_DECLS]
    msgs = msgs[:first_user] + decls + msgs[first_user:]

    eval_msgs, observed = split_at_final_user(msgs)
    turns = turn_map(eval_msgs)
    mcdi = [i for i, m in enumerate(eval_msgs) if m["role"] == "developer" and turns[i] > 0]

    doc = {
        "sample_id": sample_id,
        "name": name,
        "domain": domain,
        "sample_type": "uncertified",
        "messages": eval_msgs,
        "rubrics": rubrics,
        "metadata": {
            "turn_count": max(turns) + 1,
            "mcdi_count": len(mcdi),
            "mcdi_message_indices": mcdi,
            "turn_of_each_message": turns,
            "turn_indexing": "0-based, matching the client's // Turn 0 / // Turn 1 example",
            "graded_turn": max(turns),
            "grading_scope": "final turn only; earlier-turn rubrics are optional and none are included",
            "tier_mapping": {
                "developer_role_in_this_file": "DEVELOPER tier",
                "user_role_in_this_file": "USER tier",
                "google_internal_system_instruction": "SYSTEM tier - not authored here, not expected to change",
            },
            "generation": "live chain on Gemini, one API call per turn; assistant text, thoughts and "
                          "tool calls are generated, not authored",
            "thoughts_captured": True,
            "order_diagnostic_reviewed": True,
            "certification": {
                "status": "pending",
                "model": "gemini-3.7-flash",
                "protocol": "5 runs; >=3 rubric-set failures => loss_triggering, 1-2 => flaky, 0 => representative",
                "note": "sample_type stays 'uncertified' until this runs. The observed response in "
                        "trajectories/observed_final_turn.json is a single historical run on an "
                        "earlier model and is NOT a certification.",
            },
            "known_issues": known_issues,
            "source_world": "world_983e6879ef494edf912f9c9042cc112a",
        },
    }

    out_dir = os.path.join(ROOT, "samples", sample_id)
    os.makedirs(os.path.join(out_dir, "trajectories"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "files"), exist_ok=True)
    open(os.path.join(out_dir, "files", ".gitkeep"), "w").close()

    json.dump(doc, open(os.path.join(out_dir, "sample.json"), "w"), indent=2, ensure_ascii=False)
    json.dump({"messages": observed,
               "note": "The response the model actually produced to the final user turn. Excluded "
                       "from the eval item by design; retained as evidence for certification.",
               "historical_grades": (json.load(open(os.path.join(CACHE, "final_grades.json")))
                                     .get(grades_key) if grades_key and
                                     os.path.exists(os.path.join(CACHE, "final_grades.json")) else None)},
              open(os.path.join(out_dir, "trajectories", "observed_final_turn.json"), "w"),
              indent=2, ensure_ascii=False)
    json.dump({"messages": eval_msgs, "note": "Context turns as generated by the live chain, "
               "including thoughts and tool calls."},
              open(os.path.join(out_dir, "trajectories", "context_turns.json"), "w"),
              indent=2, ensure_ascii=False)

    print(f"{sample_id}: {len(eval_msgs)} messages ({max(turns)+1} turns, {len(mcdi)} MCDI), "
          f"{len(rubrics)} rubrics, {sum(1 for r in rubrics if r['expected_behavior']=='BEHAVIOR_OVERRIDEN')} overridden")
    return doc


if __name__ == "__main__":
    from rubrics_coding import RUBRICS as CODING, KNOWN_ISSUES as CI
    from rubrics_finance import RUBRICS as FINANCE, KNOWN_ISSUES as FI
    sys.path.insert(0, ROOT)
    build("mcdi_coding_payments_001", "Coding - payments service", "coding",
          "traj_coding.json", CODING, CI, grades_key="coding")
    build("mcdi_finance_board_001", "Finance - quarterly board reporting", "finance",
          "traj_finance.json", FINANCE, FI, grades_key="finance")
