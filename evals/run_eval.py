"""Behaviour eval: does a model, given the group prompt, speak and stay silent in the right places?

Each case is a short group transcript ending in one new message. The script renders the turn exactly the
way the gateway does (sender tag, addressing hint, buffered context), asks the model through the
``claude`` CLI, and checks the reply against the expectation. Usage:

    python3 evals/run_eval.py [--model claude-sonnet-5-5] [--runs 3]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from read_the_room import GroupEtiquette, Roster  # noqa: E402

SILENCE = "NO_REPLY"
HERE = Path(__file__).parent
ROSTER = CASES = None


def render(case):
    g = GroupEtiquette(ROSTER)
    handles = {m.name: next(iter(m.handles)) for m in ROSTER.members}
    history = []
    for i, (who, text) in enumerate(case["history"]):
        if who == ROSTER.me.name:
            history.append({"role": "assistant", "content": text})
            continue
        g.decide("c", handles[who], text, now_ms=i)
        history.append({"role": "user", "content": f"[{who}] {text}"})
    who, text = case["message"]
    dec = g.decide("c", handles[who], text, now_ms=len(case["history"]))
    turn = f"[{who}] {text}\n(addressing hint: {dec.hint})"
    return dec, history, turn


def ask(model, system, history, turn):
    convo = "\n".join(h["content"] if h["role"] == "user" else f"[{ROSTER.me.name} (you)] {h['content']}"
                      for h in history)
    prompt = (f"Conversation so far:\n{convo}\n\nNew message:\n{turn}\n\n"
              f"Write exactly what you would send to the group, or {SILENCE} to send nothing.")
    out = subprocess.run(["claude", "-p", "--model", model, "--system-prompt", system, "--tools", "",
                          "--strict-mcp-config", prompt], capture_output=True, text=True, timeout=180)
    return out.stdout.strip()


def judge(case, reply):
    silent = reply.strip().upper().strip(".") == SILENCE
    if case["expect"] == "silent":
        return silent, "should stay silent"
    if silent:
        return False, "should answer"
    low = reply.lower()
    bad = [w for w in case.get("forbid", []) if w in low]
    if bad:
        return False, f"used {bad}"
    if "\n\n" in reply.strip():
        return False, "more than one bubble"
    return True, "answered"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--only")
    ap.add_argument("--json", action="store_true", help="print each full reply as JSON")
    ap.add_argument("--roster", default=str(HERE / "roster.json"))
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    ap.add_argument("--persona", help="file prepended to the system prompt (the agent's own persona)")
    args = ap.parse_args()
    global ROSTER, CASES
    ROSTER = Roster.from_config(json.loads(Path(args.roster).read_text()))
    CASES = json.loads(Path(args.cases).read_text())
    system = GroupEtiquette(ROSTER).system_prompt() + f"\n\nThe silence marker is {SILENCE}."
    if args.persona:
        system = Path(args.persona).read_text() + "\n\n" + system
    passed = total = 0
    for case in CASES:
        if args.only and case["id"] != args.only:
            continue
        dec, history, turn = render(case)
        for _ in range(args.runs):
            reply = ask(args.model, system, history, turn)
            ok, why = judge(case, reply)
            passed += ok
            total += 1
            if args.json:
                print(json.dumps({"case": case["id"], "ok": ok, "why": why, "reply": reply}))
            else:
                print(f"{case['id']:<30}{case['expect']:<9}{'ok' if ok else 'FAIL ' + why}")
    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
