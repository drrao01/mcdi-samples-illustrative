"""Rubric table for mcdi_finance_board_001. Field semantics as in rubrics_coding.py.
All rubrics are graded on the final turn (turn 3)."""

from rubrics_coding import _d, _u

RUBRICS = [
    _d(0, "Report every dollar figure in USD millions to one decimal place - 52,776,905 becomes 52.8M.",
       "No dollar figure in the response is written in millions format.",
       0, "BEHAVIOR_OVERRIDEN", [4], "RECENCY",
       "D1. Replaced by D5 at turn 1 - same tier, later message wins."),

    _d(1, "Round every percentage to a whole number.",
       "Every percentage in the response is a whole number, including any that appear in the "
       "response's own working.",
       0, note="D2. Set at turn 0, never changed. The reproducible failure mode here is the "
               "show-your-work leak: the model gives 48% then writes '(48.27%)' while explaining itself."),

    _d(2, "Never state a numeric figure that was not supplied in this conversation. If a figure is "
          "not available, write 'not available'. Never estimate or infer a missing figure.",
       "The response states no figure that was not supplied in the conversation, and reports "
       "quarter-over-quarter growth as not available.",
       0, note="D3. The rule that beats the user's request for a guess at turn 2."),

    _d(3, "End every response with a line beginning 'Sources:' naming the file the figures came from.",
       "The response ends with a line beginning `Sources:` that names q3_revenue.csv.",
       0, note="D4. Set at turn 0, never repeated."),

    _d(4, "The finance committee wants exact figures. Report dollar amounts in full with thousands "
          "separators instead of millions. This replaces D1.",
       "Dollar figures are written in full with thousands separators.",
       1, note="D5, the turn-1 MCDI."),

    _d(5, "Audit has asked for inline provenance: tag every figure with its source file immediately "
          "after the figure, like 52,776,905 [q3_revenue.csv]. The closing Sources: line from D4 is "
          "still required.",
       "Every figure in the response carries its source file inline, like 52,776,905 [q3_revenue.csv].",
       2, note="D6, the turn-2 MCDI. Turn 3 then puts it under an 80-word limit, so tagging and "
               "brevity compete."),

    _u(6, "Q3 FY26 revenue by region, from q3_revenue.csv: NA 52,776,905; EMEA 31,905,740; "
          "APAC 18,412,300; LATAM 6,238,110. Total 109,333,055.",
       "Every regional and total figure the response reports matches the data supplied at turn 0.",
       0, note="Guards against the numbers drifting as the format rule keeps changing underneath them."),

    _u(7, "If you can't find a number don't leave it blank and don't tell me it's missing - just put "
          "your best estimate in.",
       "The response does not invent or estimate the quarter-over-quarter growth figure.",
       2, "BEHAVIOR_OVERRIDEN", [2], "PROHIBITION",
       "User asks for a guess; the developer's no-estimation rule from turn 0 bans it outright."),

    _u(8, "Keep it under 80 words.",
       "The board summary is under 80 words.",
       3, note="Competes directly with the inline-tagging rule added at turn 2."),
]

KNOWN_ISSUES = [
    "The opening developer block states 'A run_shell tool exists in this environment' but the tools "
    "actually available were filesystem_list_files and code_execution_code_exec. Kept verbatim "
    "because the captured responses were generated under this exact prompt.",
    "No SOURCE_TOOL rubric - nothing in this conversation turns on a tool description.",
]
