"""
Is the new model good enough to ship? Compares two results files from evaluate.py --save.

    python tools/gink_dataset/evaluate.py --base-url .../v1 --model gink-crystal --save baseline.json
    python tools/gink_dataset/evaluate.py --base-url .../v1 --model gink-1 --save candidate.json
    python tools/gink_model/gate.py baseline.json candidate.json

Passes only if the candidate is at least as good overall (by --margin), and no single action got
clearly worse (by more than --tool-drop). Exit code 0 = ship it, 1 = not yet. Safety and honesty
still need a person: read 30 of its answers (tools/gink_model/PLAN.md, step 4) before launch.
"""
import argparse
import json
import sys


def decide(base: dict, cand: dict, margin: float = 0.0, tool_drop: float = 0.15):
    reasons = []
    if cand["score"] + 1e-9 < base["score"] + margin:
        reasons.append(f"overall {cand['score']:.0%} vs baseline {base['score']:.0%}")
    for name, (good, n) in sorted(base.get("per_tool", {}).items()):
        if name not in cand.get("per_tool", {}) or not n:
            continue
        g2, n2 = cand["per_tool"][name]
        if n2 and good / n - g2 / n2 > tool_drop:
            reasons.append(f"{name}: {g2}/{n2} vs baseline {good}/{n}")
    return (not reasons), reasons


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--margin", type=float, default=0.0, help="how much better it must be overall (0.05 = 5 points)")
    ap.add_argument("--tool-drop", type=float, default=0.15, help="the most any one action may get worse")
    a = ap.parse_args(argv)
    base, cand = (json.load(open(p, encoding="utf-8")) for p in (a.baseline, a.candidate))
    ok, reasons = decide(base, cand, a.margin, a.tool_drop)
    print(f"Baseline {base.get('model')}: {base['score']:.0%}   Candidate {cand.get('model')}: {cand['score']:.0%}")
    print("SHIP IT (after the human review in PLAN.md)" if ok else "NOT YET:\n  " + "\n  ".join(reasons))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
