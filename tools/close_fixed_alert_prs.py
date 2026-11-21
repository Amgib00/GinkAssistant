#!/usr/bin/env python3
"""Close GitHub's "Potential fix for code scanning alert no. N" pull requests whose alert is already gone.

Copilot Autofix opened one pull request per code scanning alert. Many of those alerts were fixed since (on main)
or dismissed, so their pull requests only sit there with failing checks, based on old code. This closes those, with
a comment saying why, and lists the ones whose alert is still open -- with where it is -- so they can be fixed.

    python3 tools/close_fixed_alert_prs.py           # shows what it would do (changes nothing)
    python3 tools/close_fixed_alert_prs.py --close   # closes the pull requests of fixed or dismissed alerts

Uses your `gh` login (it needs to see the repository's code scanning alerts). It never merges anything, and never
closes a pull request whose alert is still open.
"""
import json
import os
import re
import subprocess
import sys

REPO = os.environ.get("GINK_GH_REPO", "Amgib00/GinkAssistant")
TITLE = re.compile(r"^Potential fix for code scanning alert no\. (\d+)", re.I)


def gh(*args, check=True) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def alert(number: int) -> dict:
    """{"state", "rule", "where"} of one code scanning alert ({"state": "unknown"} if GitHub won't say)."""
    out = gh("api", f"repos/{REPO}/code-scanning/alerts/{number}", check=False)
    try:
        a = json.loads(out)
    except ValueError:
        return {"state": "unknown", "rule": "", "where": ""}
    loc = ((a.get("most_recent_instance") or {}).get("location") or {})
    return {"state": a.get("state") or "unknown", "rule": (a.get("rule") or {}).get("description") or "",
            "where": f"{loc.get('path', '?')}:{loc.get('start_line', '?')}" if loc else ""}


def main(close: bool):
    prs = json.loads(gh("pr", "list", "-R", REPO, "--state", "open", "--limit", "200", "--json", "number,title"))
    mine = sorted(((p["number"], int(m.group(1)), p["title"]) for p in prs if (m := TITLE.match(p["title"]))), reverse=True)
    print(f"{len(mine)} open autofix pull requests in {REPO}{'' if close else '  (showing only: add --close to close them)'}\n")
    closing, still = 0, []
    for pr, number, title in mine:
        a = alert(number)
        if a["state"] in ("fixed", "dismissed"):
            closing += 1
            print(f"  #{pr:<4} alert {number} is {a['state']}: {'closing' if close else 'would close'}")
            if close:
                gh("pr", "close", str(pr), "-R", REPO, "--comment",
                   f"Code scanning alert {number} is {a['state']} on the main branch, so this suggested fix isn't "
                   "needed any more. Closed by tools/close_fixed_alert_prs.py.")
        else:
            still.append((pr, number, a))
            print(f"  #{pr:<4} alert {number} is {a['state']}: kept -- {a['rule']} ({a['where']})")
    print(f"\n{closing} pull request(s) {'closed' if close else 'would be closed'}; {len(still)} kept.")
    if still:
        print("Alerts still open (fix them, then run this again):")
        for pr, number, a in still:
            print(f"  alert {number}: {a['rule'] or '?'} at {a['where'] or '?'}  (pull request #{pr})")


if __name__ == "__main__":
    main("--close" in sys.argv[1:])
