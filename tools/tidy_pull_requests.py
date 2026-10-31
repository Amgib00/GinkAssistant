#!/usr/bin/env python3
"""Tidy every pull request on GitHub (open AND closed) with the same rules as
.github/workflows/pull-requests.yml: labels from the changed files (.github/labeler.yml), the owner as
assignee when there's none, and open ones in the "Next release" milestone.

    python3 tools/tidy_pull_requests.py            # shows what it would do (changes nothing)
    python3 tools/tidy_pull_requests.py --apply    # does it

Uses your `gh` login. It never closes, merges or reopens anything.
"""
import json
import os
import re
import subprocess
import sys

REPO = os.environ.get("GINK_GH_REPO", "Amgib00/GinkAssistant")
OWNER = REPO.split("/")[0]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LABELS = {  # the same names, colours and descriptions as the workflow
    "app": ("1f6feb", "The Gink apps (desktop and phone)"), "server": ("8250df", "The Gink server"),
    "web": ("0e8a16", "The web app"), "genie": ("a8f03c", "Gink Genie"), "tests": ("fbca04", "Tests"),
    "docs": ("c5def5", "Documentation and specs"), "ci": ("5319e7", "Builds, releases and tools"),
    "website": ("bfdadc", "The website"), "dependencies": ("0366d6", "Package updates"),
}
MILESTONE = "Next release"


def gh(*args, check=True) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def edit(number: int, add_labels: list, assign: bool, milestone):
    """Through the REST API: `gh pr edit` also asks about classic Projects, which GitHub retired -> it fails
    ("Projects (classic) is being deprecated ... projectCards")."""
    issue = f"repos/{REPO}/issues/{number}"           # a pull request is an issue for labels/assignees/milestone
    if add_labels:
        gh("api", "-X", "POST", f"{issue}/labels", *sum((["-f", f"labels[]={x}"] for x in add_labels), []))
    if assign:
        gh("api", "-X", "POST", f"{issue}/assignees", "-f", f"assignees[]={OWNER}")
    if milestone:
        gh("api", "-X", "PATCH", issue, "-F", f"milestone={milestone}")


def glob_to_regex(pattern: str) -> str:
    """labeler's globs: ** (any folders), * and ? (within a name), !(a|b) (anything but)."""
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pattern.startswith("**", i):
            out += ".*"; i += 2
        elif pattern.startswith("!(", i):
            j = pattern.index(")", i)
            out += "(?!(?:%s)(?:[^/]*$))[^/]*" % "|".join(re.escape(x) for x in pattern[i + 2:j].split("|"))
            i = j + 1
        elif c == "*":
            out += "[^/]*"; i += 1
        elif c == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(c); i += 1
    return "^" + out + "$"


def load_rules() -> dict:
    """{label: [regex, ...]} from .github/labeler.yml (no YAML library needed: the file is simple)."""
    rules, label = {}, None
    for line in open(os.path.join(ROOT, ".github", "labeler.yml"), encoding="utf-8"):
        if re.match(r"^[a-z][\w-]*:\s*$", line):
            label = line.strip()[:-1]; rules[label] = []
        m = re.search(r"any-glob-to-any-file:\s*\[(.*)\]", line)
        if m and label:
            rules[label] += [glob_to_regex(g.strip().strip("'\"")) for g in m.group(1).split(",") if g.strip()]
    return rules


def labels_for(files: list, rules: dict) -> set:
    return {lab for lab, regs in rules.items() if any(re.match(r, f) for r in regs for f in files)}


def main(apply: bool):
    rules = load_rules()
    prs = json.loads(gh("pr", "list", "-R", REPO, "--state", "all", "--limit", "500",
                        "--json", "number,title,state,labels,assignees,milestone"))
    print(f"{len(prs)} pull requests in {REPO}{'' if apply else '  (showing only: add --apply to do it)'}\n")
    milestone_no = None
    if apply:
        for name, (color, text) in LABELS.items():
            gh("label", "create", name, "-R", REPO, "--color", color, "--description", text, "--force")
        if any(p["state"] == "OPEN" and not p["milestone"] for p in prs):
            found = gh("api", f"repos/{REPO}/milestones?state=open", "--jq", f'.[] | select(.title=="{MILESTONE}") | .number').strip()
            milestone_no = found or gh("api", f"repos/{REPO}/milestones", "-f", f"title={MILESTONE}", "-f",
                                       "description=Changes going into the next Gink release", "--jq", ".number").strip()
    changed = 0
    for p in sorted(prs, key=lambda p: p["number"]):
        files = [f["path"] for f in json.loads(gh("pr", "view", str(p["number"]), "-R", REPO, "--json", "files"))["files"]]
        have = {l["name"] for l in p["labels"]}
        add = sorted(labels_for(files, rules) - have)
        assign = not p["assignees"]
        wants_milestone = p["state"] == "OPEN" and not p["milestone"]
        what = ", ".join(x for x in (f"labels {', '.join(add)}" if add else "", "assign you" if assign else "",
                                     "milestone 'Next release'" if wants_milestone else "") if x) or "nothing to do"
        print(f"  #{p['number']:<4} {p['state'].lower():<6} {p['title'][:55]:<55}  {what}")
        if add or assign or wants_milestone:
            changed += 1
            if apply:
                edit(p["number"], add, assign, milestone_no if wants_milestone else None)
    print(f"\n{changed} pull request(s) {'updated' if apply else 'would be updated'}.")


if __name__ == "__main__":
    main("--apply" in sys.argv[1:])
