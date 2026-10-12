# Task: transcribe one handwritten answer box

You are shown ONE cropped image: a single answer box from a first-grader's quiz. The child
wrote something by hand. Your only job is to transcribe EXACTLY what is written.

Rules
- Transcribe letter by letter or digit by digit. Do NOT correct spelling. Do NOT guess what the child
  meant. If they wrote "ct" for "cat", the answer is "ct". If they wrote "bed" where "ded" is plausible
  reading of a reversed letter, write what you see most literally and set `uncertain` to true.
- Reversed or mirrored letters (b/d, p/q) and digits (2, 5, 6, 9) are common. Report the most literal
  reading and set `uncertain` to true when a mirrored form could be read two ways.
- Ignore the pre-printed light guide lines and the box border.
- If the box is empty, set `blank` to true and `text` to "".
- The box holds a {kind}: spelling = a lowercase word; int = a whole number; frac = a fraction written
  like 3/4 (numerator over denominator, or with a slash); symbol = < or > or =; int_rem = a number with an
  optional remainder written like "3 R 2".

Output ONLY this JSON, nothing else:
{"text": "<exact transcription>", "blank": false, "uncertain": false, "confidence": 0.0-1.0}
