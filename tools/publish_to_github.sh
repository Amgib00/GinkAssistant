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

REPO="${GINK_REPO:-https://github.com/Amgib00/GinkAssistant.git}"
REPO_SLUG=$(echo "$REPO" | sed -E 's#^https://github.com/##; s#\.git$##')
BRANCH="${GINK_BRANCH:-main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLISH=(.github .gitignore .env.example README.md SECURITY.md INTEGRATION.md LICENSE CHANGELOG.md AGENTS.md openspec cli pyproject.toml
         requirements.txt requirements-test.txt render.yaml src tests deploy tools icons website webapp)
KEEP_FROM_REPO=(LICENSE .github/ISSUE_TEMPLATE)      # kept as they are on GitHub
SECRET_RE='hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(proj-)?[A-Za-z0-9]{32,}|sk_live_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY'

# No questions by default: the update commands are usually pasted all at once, and a question would
# swallow the NEXT pasted line as its answer ("Nothing pushed."). --ask brings the questions back.
ASK=0
for arg in "$@"; do [ "$arg" = "--ask" ] && ASK=1; done
ask() {                                   # ask "question" -> 0 for yes
  if [ "$ASK" != "1" ] || [ "${ASSUME_YES:-}" = "1" ]; then return 0; fi
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
MANIFEST="$ROOT/tools/MANIFEST.txt"
if [ -f "$MANIFEST" ]; then
  # Publish exactly the files of this version (unzipping an update never deletes old files,
  # so a project folder can hold stale ones -- those must not go back to GitHub).
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    [ -f "$ROOT/$f" ] || { echo "Missing $f -- unzip the full package again."; exit 1; }
    mkdir -p "./$(dirname "$f")"; cp "$ROOT/$f" "./$f"
  done < "$MANIFEST"
  # Not leftovers: files kept from GitHub (KEEP_FROM_REPO) and generated folders that are never published.
  STALE=$(cd "$ROOT" && for p in "${PUBLISH[@]}"; do [ -d "$p" ] && find "$p" -type f -not -path "*/__pycache__/*" \
          -not -path "website/_site/*" -not -path "tools/gink_dataset/out/*" -not -name ".DS_Store" -not -name "*.pyc" \
          -not -path "*.dist-info/*"; done | sort | comm -23 - <(sort "$MANIFEST") | while IFS= read -r f; do
            keep=0; for k in "${KEEP_FROM_REPO[@]}"; do case "$f" in "$k"|"$k"/*) keep=1;; esac; done
            if [ "$keep" = 0 ]; then echo "$f"; fi; done || true)
  if [ -n "$STALE" ]; then
    echo; echo "Not published -- these files in your folder aren't part of this version (old leftovers?):"
    echo "$STALE" | head -20 | sed 's/^/   - /'
    echo "   (they're left alone; delete them from your folder if they're old)"
  fi
else
  for p in "${PUBLISH[@]}"; do
    mkdir -p "./$(dirname "$p")"
    cp -R "$ROOT/$p" "./$(dirname "$p")/"
  done
fi
find . -path ./.git -prune -o \( -name "__pycache__" -o -name ".pytest_cache" -o -name "*.dist-info" \) -type d -print | xargs rm -rf
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
VERSION=$(grep -m1 '^version' "$ROOT/pyproject.toml" | sed -E 's/.*"(.*)".*/\1/')
if [ "$ADDED$CHANGED$REMOVED" = "000" ]; then echo "GitHub already has exactly this version ($VERSION)."; exit 0; fi
echo
ask "Push version $VERSION to $BRANCH on GitHub?" || { echo "Nothing pushed."; exit 1; }

git commit --quiet -m "Gink $VERSION" -m "$(awk '/^## /{n++} n==1' "$ROOT/CHANGELOG.md" | head -30)"
if ! git push --quiet origin "HEAD:$BRANCH"; then
  echo; echo "STOP: the push to GitHub failed (see the message above). Nothing was published, so don't run Release yet."
  exit 1
fi
# make sure GitHub really has it before anyone starts a release
git fetch --quiet origin "$BRANCH"
ON_GITHUB=$(git show "origin/$BRANCH:pyproject.toml" | grep -m1 '^version' | sed -E 's/.*"(.*)".*/\1/')
if [ "$ON_GITHUB" != "$VERSION" ]; then
  echo; echo "STOP: GitHub has version $ON_GITHUB, not $VERSION. Don't run Release yet."; exit 1
fi
echo
echo "================================================================"
echo "  GitHub now has version $VERSION."
echo "  Release it:  gh workflow run release.yml -R ${REPO_SLUG:-<owner>/<repo>} -f version=v$VERSION"
echo "================================================================"

# 5) old Dependabot branches (made from the old version)
OLD=$(git ls-remote --heads origin 'dependabot/*' | sed 's#.*refs/heads/##')
if [ -n "$OLD" ]; then
  echo; echo "Old Dependabot branches:"; echo "$OLD" | sed 's/^/   - /'
  if [ "$ASK" = "1" ] && ask "Delete these branches on GitHub?"; then
    for b in $OLD; do git push --quiet origin --delete "$b" && echo "   deleted $b"; done
  fi
fi

