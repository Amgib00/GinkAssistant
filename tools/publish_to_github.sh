#!/usr/bin/env bash
# Replace the old version on GitHub (PyQt / old layout) with the current Gink.
#
#   bash tools/publish_to_github.sh
#
# Safe by design:
#  * works in a TEMPORARY clone -- your project folder and its git settings are untouched
#  * publishes ONLY the paths in PUBLISH below (no .env, models, build folders, old code)
#  * stops if anything looks like a secret key
#  * shows what changes and ASKS before pushing; normal push, never --force
#  * offers (and asks) to delete the old Dependabot branches
# Pushing needs your GitHub sign-in (macOS Keychain / GitHub Desktop / `gh auth login`,
# or a personal access token when git asks for a password).
set -euo pipefail

REPO="${GINK_REPO:-https://github.com/amgib00/ginkassistant.git}"
BRANCH="${GINK_BRANCH:-main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLISH=(.github .gitignore .env.example README.md SECURITY.md INTEGRATION.md pyproject.toml
         requirements.txt requirements-test.txt render.yaml src tests deploy tools icons)
KEEP_FROM_REPO=(LICENSE .github/ISSUE_TEMPLATE)      # kept as they are on GitHub
SECRET_RE='hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(proj-)?[A-Za-z0-9]{32,}|sk_live_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY'

ask() {                                   # ask "question" -> 0 for yes
  if [ "${ASSUME_YES:-}" = "1" ]; then return 0; fi
  read -r -p "$1 [y/N] " a; [ "$a" = "y" ] || [ "$a" = "Y" ]
}

echo "Project:    $ROOT"
echo "GitHub:     $REPO ($BRANCH)"
cd "$ROOT"
for p in "${PUBLISH[@]}"; do
  [ -e "$p" ] || { echo "Missing $p -- run this from the Gink project (unzip the latest package first)."; exit 1; }
done

# 1) secrets check (only what will be published)
if grep -rInE "$SECRET_RE" "${PUBLISH[@]}" --exclude-dir=__pycache__ --exclude=publish_to_github.sh >/tmp/gink_secret_hits 2>/dev/null; then
  echo; echo "STOP: these look like secret keys -- remove them (and revoke them) before publishing:"
  sed -E 's/(hf_|gsk_|AKIA|ghp_|github_pat_|sk-|sk_live_|AIza)[A-Za-z0-9_-]{4,}/\1…/g' /tmp/gink_secret_hits | head -20
  exit 1
fi
echo "Secrets:    none found in the files to publish"

# 2) temporary clone of what's on GitHub now
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$TMP/repo"
cd "$TMP/repo"
git config user.name  >/dev/null 2>&1 || git config user.name  "$(git -C "$ROOT" config user.name 2>/dev/null || echo Amgib00)"
git config user.email >/dev/null 2>&1 || git config user.email "$(git -C "$ROOT" config user.email 2>/dev/null || echo kargboi131ik667957@gmail.com)"

# 3) remove everything old (except LICENSE + issue templates), copy in the current Gink
git ls-files | while read -r f; do
  keep=0
  for k in "${KEEP_FROM_REPO[@]}"; do case "$f" in "$k"|"$k"/*) keep=1;; esac; done
  [ $keep = 0 ] && git rm -q --cached -- "$f" && rm -f -- "$f"
done
find . -mindepth 1 -type d -empty -not -path "./.git*" -delete 2>/dev/null || true
for p in "${PUBLISH[@]}"; do
  mkdir -p "./$(dirname "$p")"
  cp -R "$ROOT/$p" "./$(dirname "$p")/"
done
find . -path ./.git -prune -o \( -name "__pycache__" -o -name ".pytest_cache" \) -type d -print | xargs rm -rf
find . -path ./.git -prune -o -name ".DS_Store" -type f -print | xargs rm -f
git add -A

# 4) show what will change
ADDED=$(git diff --cached --name-only --diff-filter=A | wc -l | tr -d ' ')
CHANGED=$(git diff --cached --name-only --diff-filter=M | wc -l | tr -d ' ')
REMOVED=$(git diff --cached --name-only --diff-filter=D | wc -l | tr -d ' ')
echo; echo "Changes on GitHub: $ADDED added, $CHANGED updated, $REMOVED old files removed"
echo "Old files being removed (first 25):"
git diff --cached --name-only --diff-filter=D | head -25 | sed 's/^/   - /'
echo "Kept from GitHub: ${KEEP_FROM_REPO[*]}"
echo "Size of the new version: $(du -sh --exclude=.git . 2>/dev/null | cut -f1 || du -sh . | cut -f1)"
if [ "$ADDED$CHANGED$REMOVED" = "000" ]; then echo "GitHub already has exactly this version."; exit 0; fi
echo
ask "Push this to $BRANCH on GitHub?" || { echo "Nothing pushed."; exit 0; }

git commit --quiet -m "Replace the old PyQt version with Gink (Toga + Briefcase)

Current app: macOS, Windows, Linux, Android, iOS. Tests + Android/iOS builds on
GitHub Actions. Old code, compiled files and the old workflow removed."
git push --quiet origin "HEAD:$BRANCH"
echo "Pushed. GitHub -> Actions shows the tests running."

# 5) old Dependabot branches (made from the old version)
OLD=$(git ls-remote --heads origin 'dependabot/*' | sed 's#.*refs/heads/##')
if [ -n "$OLD" ]; then
  echo; echo "Old Dependabot branches:"; echo "$OLD" | sed 's/^/   - /'
  if ask "Delete these branches on GitHub?"; then
    for b in $OLD; do git push --quiet origin --delete "$b" && echo "   deleted $b"; done
  fi
fi

echo
echo "Still to do in your browser:"
echo " 1. Revoke the old Hugging Face token: huggingface.co -> Settings -> Access Tokens."
echo " 2. Close the old pull requests: $(echo "$REPO" | sed 's/\.git$//')/pulls"
