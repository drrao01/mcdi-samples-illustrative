#!/usr/bin/env python3
"""Render index.html from samples/*/sample.json. The page is a VIEW of the JSON, never a source.

Usage: python3 render_page.py
"""
import json, glob, os, html, re

ROOT = os.path.dirname(os.path.abspath(__file__))
STYLE = open(os.path.join(ROOT, "assets", "style.css")).read()

ROLE_CLASS = {"developer": "t-dev", "user": "t-usr", "assistant": "t-asst",
              "tool_declaration": "t-decl", "tool_call": "t-call", "tool_response": "t-resp"}
ROLE_LABEL = {"developer": "DEVELOPER", "user": "USER", "assistant": "ASSISTANT",
              "tool_declaration": "TOOL DECLARATION", "tool_call": "TOOL CALL",
              "tool_response": "TOOL RESPONSE"}
REASON_BLURB = {
    "PROHIBITION": "developer bans it flat out", "PERMISSION": "developer defers to the user",
    "SILENCE": "developer never mentions it", "SPECIALIZATION": "user narrows the same rule",
    "ADVISORY": "tone, length or style only", "RECENCY": "later message, same tier",
}
e = html.escape


def code_blocks(text):
    """Render fenced code blocks; escape everything else."""
    out, i = [], 0
    for m in re.finditer(r"```[a-z]*\n(.*?)```", text, re.S):
        out.append(f"<div>{e(text[i:m.start()])}</div>")
        out.append(f'<pre class="codewrap"><code>{e(m.group(1))}</code></pre>')
        i = m.end()
    out.append(f"<div>{e(text[i:])}</div>")
    return "".join(out)


def render_message(m, turn):
    role = m["role"]
    cls = ROLE_CLASS[role]
    label = ROLE_LABEL[role]
    if m.get("thought"):
        cls, label = "t-thought", "ASSISTANT · THINKING"
    head = (f'<div class="mh"><span class="role">{label}</span>'
            f'<span class="tn">turn {turn}</span></div>')

    if role == "tool_declaration":
        d = m["tool_description"]
        body = (f'<div class="mk">{e(d["name"])}</div><div class="bd">{e(d["description"])}</div>'
                f'<pre class="codewrap"><code>{e(json.dumps(d["parameters"], indent=2))}</code></pre>')
    elif role == "tool_call":
        body = (f'<div class="mk">{e(m.get("tool_name") or "")}</div>'
                f'<pre class="codewrap"><code>'
                f'{e(json.dumps(m.get("arguments"), indent=2)[:1400])}</code></pre>')
    elif role == "tool_response":
        body = f'<pre class="codewrap"><code>{e((m.get("content") or "")[:1200])}</code></pre>'
    elif m.get("thought"):
        body = f'<details><summary>thinking</summary><div class="bd">{e(m.get("content") or "")}</div></details>'
    else:
        body = f'<div class="bd">{code_blocks(m.get("content") or "")}</div>'
    return f'<div class="msg {cls}">{head}{body}</div>'


def render_rubrics(rubrics):
    rows = []
    for r in rubrics:
        ov = r["expected_behavior"] == "BEHAVIOR_OVERRIDEN"
        badge = ('<span class="pill ov">OVERRIDDEN</span>' if ov
                 else '<span class="pill sa">SATISFIED</span>')
        by = ""
        if ov:
            reason = r.get("overriden_reason", "")
            by = (f'<div class="sub">by #{", #".join(str(x) for x in r["overriden_by"])} · '
                  f'<b>{e(reason)}</b> — {e(REASON_BLURB.get(reason, ""))}</div>')
        note = f'<div class="sub">{e(r["_authoring_note"])}</div>' if r.get("_authoring_note") else ""
        rows.append(
            f'<tr><td class="n">{r["id"]}</td>'
            f'<td><div class="rx">{e(r["text"])}</div>'
            f'<div class="chk"><b>check:</b> {e(r["check"])}</div>{by}{note}</td>'
            f'<td class="nt">{e(r["source"].replace("SOURCE_", ""))}</td>'
            f'<td class="nt">{r["num_turn"]}</td>'
            f'<td class="nt">{badge}</td></tr>')
    return ("<table class='rub'><thead><tr><th>#</th><th>instruction / check</th>"
            "<th>source</th><th>origin turn</th><th>expected</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def render_sample(d):
    md = d["metadata"]
    turns = md["turn_of_each_message"]
    msgs = []
    prev_turn = 0
    for m, t in zip(d["messages"], turns):
        if m["role"] == "developer" and t > 0 and t != prev_turn:
            msgs.append('<div class="ex">instructions change here</div>')
        msgs.append(render_message(m, t))
        prev_turn = t
    n_ov = sum(1 for r in d["rubrics"] if r["expected_behavior"] == "BEHAVIOR_OVERRIDEN")
    issues = "".join(f"<li>{e(i)}</li>" for i in md.get("known_issues", []))
    return f"""
<section>
  <p class="eyebrow">{e(d['domain'])} · {e(d['sample_id'])}</p>
  <h2>{e(d['name'])} <span class="badge unc">{e(d['sample_type'])}</span></h2>
  <div class="facts">
    <div><span class="n">{md['turn_count']}</span><span class="fl">turns</span></div>
    <div><span class="n">{md['mcdi_count']}</span><span class="fl">MCDI</span></div>
    <div><span class="n">{len(d['rubrics'])}</span><span class="fl">rubrics</span></div>
    <div><span class="n">{n_ov}</span><span class="fl">overridden</span></div>
    <div><span class="n">{md['graded_turn']}</span><span class="fl">graded turn</span></div>
  </div>
  <p class="blurb">Rubrics are graded on turn {md['graded_turn']} only. The sample ends at the final
  user message — the response under test is generated at evaluation time and is not shipped with the
  item. <code>origin turn</code> is where the instruction first appeared, not where it is checked.</p>
  <h3>Conversation</h3>
  {''.join(msgs)}
  <h3>Rubrics</h3>
  {render_rubrics(d['rubrics'])}
  <details class="ki"><summary>Known issues ({len(md.get('known_issues', []))})</summary>
  <ul>{issues}</ul></details>
</section>"""


def main():
    paths = sorted(glob.glob(os.path.join(ROOT, "samples", "*", "sample.json")))
    docs = [json.load(open(p)) for p in paths]
    body = "".join(render_sample(d) for d in docs)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">
<meta name="googlebot" content="noindex, nofollow, noarchive, nosnippet">
<meta name="referrer" content="no-referrer">
<meta name="description" content="Illustrative mid-conversation developer instruction samples.">
<title>MCDI Samples - Illustrative</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>{STYLE}</style></head>
<body><div class="wrap">
<header class="top">
  <p class="eyebrow">Mid-conversation developer instructions</p>
  <h1>MCDI Samples — Illustrative</h1>
  <p class="lede">Eval items in the delivery schema. Each is a multi-turn conversation whose
  developer instructions change partway through, captured from a live model run with thoughts and
  tool calls intact, followed by the rubrics that check whether the final response kept up.
  Generated from <code>samples/*/sample.json</code> — the JSON is the source of truth, this page is
  a view of it.</p>
</header>
{body}
</div></body></html>"""
    open(os.path.join(ROOT, "index.html"), "w").write(page)
    print(f"index.html: {len(docs)} samples, {len(page):,} bytes")


if __name__ == "__main__":
    main()
