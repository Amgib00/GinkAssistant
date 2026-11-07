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
# With pipefail, a reader that stops early (head, grep -m1) can kill the writer with SIGPIPE and the whole script
# silently exits 141 -- it happened right after a successful push. Pipes here read their input to the end (awk).

REPO="${GINK_REPO:-https://github.com/Amgib00/GinkAssistant.git}"
REPO_SLUG=$(echo "$REPO" | sed -E 's#^https://github.com/##; s#\.git$##')
BRANCH="${GINK_BRANCH:-main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLISH=(.github .gitignore .env.example README.md SECURITY.md INTEGRATION.md LICENSE CHANGELOG.md AGENTS.md openspec cli pyproject.toml
         requirements.txt requirements-test.txt render.yaml src tests deploy tools icons website webapp)
KEEP_FROM_REPO=(LICENSE .github/ISSUE_TEMPLATE)      # kept as they are on GitHub
OWNER_DATA=(tools/gink_dataset/paraphrases.csv tools/gink_dataset/translations.csv
            tools/gink_dataset/examples_general.csv tools/gink_dataset/languages)   # yours: from this folder
SECRET_RE='hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(proj-)?[A-Za-z0-9]{32,}|sk_live_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY'

# No questions by default: the update commands are usually pasted all at once, and a question would
# swallow the NEXT pasted line as its answer ("Nothing pushed."). --ask brings the questions back.
ASK=0
for arg in "$@"; do [ "$arg" = "--ask" ] && ASK=1; done
ask() {                                   # ask "question" -> 0 for yes
  if [ "$ASK" != "1" ] || [ "${ASSUME_YES:-}" = "1" ]; then return 0; fi
  read -r -p "$1 [y/N] " a; [ "$a" = "y" ] || [ "$a" = "Y" ]
}

# 4b) your project folder's own Git catches up (files untouched). Publishing works in a temporary clone, so
# before this the folder's Git stayed on an old version while GitHub moved on, and PyCharm saw ~500 files
# "changed here AND on GitHub" after every update: thousands of "Potential merge conflicts detected".
sync_project_git() {
  [ -d "$ROOT/.git" ] || return 0                                   # not a Git folder: nothing to do
  local url; url=$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)
  norm() { echo "$1" | sed -E 's#^git@github.com:#https://github.com/#; s#\.git$##; s#/$##' | tr 'A-Z' 'a-z'; }
  if [ -z "$url" ] || [ "$(norm "$url")" != "$(norm "$REPO")" ]; then
    echo "(Your project folder's Git points elsewhere -- left as it is.)"; return 0
  fi
  git -C "$ROOT" fetch --quiet origin "$BRANCH" || { echo "(Couldn't update your project folder's Git -- harmless.)"; return 0; }
  local here; here=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  if [ "$here" != "$BRANCH" ]; then
    echo "(Your project folder is on branch '$here', not $BRANCH -- left as it is.)"; return 0
  fi
  if [ -n "$(git -C "$ROOT" rev-list "origin/$BRANCH..HEAD" 2>/dev/null)" ]; then
    echo "(Your project folder has its own commits that aren't on GitHub -- left as it is.)"; return 0
  fi
  # --mixed: the branch and Git's index move to what was just published; the FILES stay exactly as they are
  git -C "$ROOT" reset --quiet --mixed "origin/$BRANCH" && \
    echo "Your project folder's Git is now on version $VERSION too (no more merge-conflict warnings in PyCharm)."
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
  sed -E 's/(hf_|gsk_|AKIA|ghp_|github_pat_|sk-|sk_live_|AIza)[A-Za-z0-9_-]{4,}/\1…/g' /tmp/gink_secret_hits | awk 'NR<=20'
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
  # The owner's own data, written on this computer (never in an update package, so unzipping an update
  # can't overwrite it): published exactly as it is here, if it exists.
  for d in "${OWNER_DATA[@]}"; do
    if [ -e "$ROOT/$d" ]; then mkdir -p "./$(dirname "$d")"; cp -R "$ROOT/$d" "./$(dirname "$d")/"; fi
  done
  # Not leftovers: files kept from GitHub (KEEP_FROM_REPO) and generated folders that are never published.
  STALE=$(cd "$ROOT" && for p in "${PUBLISH[@]}"; do [ -d "$p" ] && find "$p" -type f -not -path "*/__pycache__/*" \
          -not -path "website/_site/*" -not -path "tools/gink_dataset/out/*" -not -name ".DS_Store" -not -name "*.pyc" \
          -not -path "*.dist-info/*"; done | sort | comm -23 - <(sort "$MANIFEST") | while IFS= read -r f; do
            keep=0; for k in "${KEEP_FROM_REPO[@]}" "${OWNER_DATA[@]}"; do case "$f" in "$k"|"$k"/*) keep=1;; esac; done
            if [ "$keep" = 0 ]; then echo "$f"; fi; done || true)
  if [ -n "$STALE" ]; then
    echo; echo "Not published -- these files in your folder aren't part of this version (old leftovers?):"
    echo "$STALE" | awk 'NR<=20' | sed 's/^/   - /'
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
git diff --cached --name-only --diff-filter=D | awk 'NR<=25' | sed 's/^/   - /'
echo "Kept from GitHub: ${KEEP_FROM_REPO[*]}"
echo "Size of the new version: $(du -sh --exclude=.git . 2>/dev/null | cut -f1 || du -sh . | cut -f1)"
VERSION=$(grep -m1 '^version' "$ROOT/pyproject.toml" | sed -E 's/.*"(.*)".*/\1/')
if [ "$ADDED$CHANGED$REMOVED" = "000" ]; then echo "GitHub already has exactly this version ($VERSION)."; sync_project_git; exit 0; fi
echo
ask "Push version $VERSION to $BRANCH on GitHub?" || { echo "Nothing pushed."; exit 1; }

git commit --quiet -m "Gink $VERSION" -m "$(awk '/^## /{n++} n==1 && c++<30' "$ROOT/CHANGELOG.md")"
if ! git push --quiet origin "HEAD:$BRANCH"; then
  echo; echo "STOP: the push to GitHub failed (see the message above). Nothing was published, so don't run Release yet."
  exit 1
fi
# make sure GitHub really has it before anyone starts a release
git fetch --quiet origin "$BRANCH"
ON_GITHUB=$(git show "origin/$BRANCH:pyproject.toml" | awk '/^version/ && !v {v=$0} END {print v}' | sed -E 's/.*"(.*)".*/\1/')
if [ "$ON_GITHUB" != "$VERSION" ]; then
  echo; echo "STOP: GitHub has version $ON_GITHUB, not $VERSION. Don't run Release yet."; exit 1
fi
sync_project_git

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

