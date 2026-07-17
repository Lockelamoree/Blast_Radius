#!/usr/bin/env bash
# Composite-action entrypoint for the "Blast Radius verify" GitHub Action.
# Gate-verifies scenario drafts and optionally screens the PR diff. Reads its
# inputs from BR_SCENARIOS, BR_DIFF_BASE, BR_FAIL_ON (set by action.yml).
set -euo pipefail

scenarios="${BR_SCENARIOS:-}"
diff_base="${BR_DIFF_BASE:-}"
fail_on="${BR_FAIL_ON:-reject}"

status=0

if [ -n "${scenarios}" ]; then
  # Word-splitting is intended: the glob may expand to several files.
  # shellcheck disable=SC2086
  files=$(ls ${scenarios} 2>/dev/null || true)
  if [ -z "${files}" ]; then
    echo "No scenario files matched: ${scenarios}"
  else
    # shellcheck disable=SC2086
    blastradius verify ${files} || status=1
  fi
fi

if [ -n "${diff_base}" ]; then
  echo "Screening diff against ${diff_base}"
  git diff "${diff_base}...HEAD" | blastradius check --kind diff - --fail-on "${fail_on}" || status=1
fi

exit "${status}"
