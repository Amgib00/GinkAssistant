#!/usr/bin/env bash
# Close the pull requests that add security-scanner workflows needing paid accounts and tokens (they can only
# fail here), and delete their branches. .github/workflows/security.yml replaces them with free checks.
#
#   bash tools/close_scanner_prs.sh            # shows what it would close
#   bash tools/close_scanner_prs.sh --close    # closes them
set -euo pipefail
REPO="${GINK_REPO_SLUG:-Amgib00/GinkAssistant}"
DO=0; [ "${1:-}" = "--close" ] && DO=1
NOTE="Closing: this scanner needs a paid account and a secret token, so it can only fail here. Gink's free checks \
(.github/workflows/security.yml: Hadolint for the Dockerfile, pip-audit for packages) and CodeQL's default setup \
(Settings -> Code security) cover this instead."
found=0
while IFS=$'\t' read -r num branch title; do
  [ -n "$num" ] || continue
  case "$title" in
    *Checkmarx*|*"Black Duck"*|*APIsec*|*Sysdig*|*[Ss]nyk*|*Codacy*|*Fortify*|*PSScriptAnalyzer*|*codeql.yml*|*CodeQL*|*Hadolint*)
      found=$((found + 1))
      if [ "$DO" = 1 ]; then
        gh pr close "$num" -R "$REPO" --delete-branch --comment "$NOTE" && echo "closed #$num  $title"
      else
        echo "would close #$num  $title   (branch $branch)"
      fi ;;
  esac
done < <(gh pr list -R "$REPO" --state open --limit 200 --json number,headRefName,title \
           --jq '.[] | [.number, .headRefName, .title] | @tsv')
[ "$found" = 0 ] && echo "No open scanner pull requests."
[ "$DO" = 0 ] && [ "$found" != 0 ] && echo "Run again with --close to close them."
exit 0
