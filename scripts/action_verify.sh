#!/usr/bin/env bash
# Composite-action entrypoint for the "Blast Radius verify" GitHub Action.
# Gate-verifies scenario drafts and optionally screens the PR diff, then writes a
# readable summary and step outputs. Reads its inputs from BR_SCENARIOS,
# BR_DIFF_BASE, BR_FAIL_ON (set by action.yml).
set -euo pipefail

scenarios="${BR_SCENARIOS:-}"
diff_base="${BR_DIFF_BASE:-}"
fail_on="${BR_FAIL_ON:-reject}"
here="${GITHUB_ACTION_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"

status=0

summary() {
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '%s\n' "$1" >>"${GITHUB_STEP_SUMMARY}"
  fi
}

if [ -n "${scenarios}" ]; then
  # Word-splitting is intended: the glob may expand to several files.
  # shellcheck disable=SC2086
  files=$(ls ${scenarios} 2>/dev/null || true)
  if [ -z "${files}" ]; then
    echo "No scenario files matched: ${scenarios}"
    summary "## Blast Radius scenarios"
    summary "- No files matched \`${scenarios}\`"
  else
    # shellcheck disable=SC2086
    if blastradius verify ${files}; then
      summary "## Blast Radius scenarios"
      summary "- ✅ Every draft passes the production gate"
    else
      status=1
      summary "## Blast Radius scenarios"
      summary "- ❌ A draft failed the production gate"
    fi
  fi
fi

if [ -n "${diff_base}" ]; then
  echo "Screening diff against ${diff_base}"
  # Capture the JSON report (stdout) while honoring the fail-on exit code, then
  # render a summary + outputs. The screen's exit status still governs the build.
  report="$(git diff "${diff_base}...HEAD" | blastradius check --kind diff - --json --fail-on "${fail_on}")" || status=1
  printf '%s' "${report}" | python3 "${here}/scripts/action_summary.py" || true
fi

exit "${status}"
