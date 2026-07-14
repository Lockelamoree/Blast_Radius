# Browser UI guidance

Keep the interface dependency-free: vanilla JavaScript and CSS served by FastAPI, with no
Node build step.

- Render untrusted scenario and model text with `textContent`, never `innerHTML`.
- Never request or display hidden ground truth before a decision is graded.
- Label the actual grading path from `grade.graded_by`; do not imply a model ran when it did
  not.
- Preserve keyboard navigation, visible focus, `aria-live` feedback, and mobile layouts.
- Keep the verified demo usable when OpenAI is unavailable or the daily budget is exhausted.
