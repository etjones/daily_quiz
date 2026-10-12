# Task: turn a progress-report data structure into a short note for a parent

You receive the report as JSON (fixed questions, each with computed answers). Write at most 120 words,
plain and warm, addressed to the parent.

Rules
- Use ONLY facts in the JSON. Do not invent numbers, skills or causes.
- Lead with what is going well. Name at most two things to watch.
- If `load_reductions` > 0 or `tears_days` > 0, say the habit matters more than the content and the
  load is already adjusting.
- Do not give medical, psychological or diagnostic opinions.
- End with one concrete suggestion for the next three days, taken from `recommendations` in the JSON.

Output plain text only.
