#!/usr/bin/env python3
"""
Run ONE question through the stage 7 agent in three modes and print a scoreboard.

    REPO=~/django uv run reference/compare.py
    REPO=~/django uv run reference/compare.py --question "..." --expect "1000,400"

Columns: steps taken, peak context of any single request, total tokens sent
(what you pay for), compactions, and whether the answer contains the expected facts.
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage7_large_codebase as s7  # noqa: E402

QUESTION = ("What is Django's default limit on the number of fields in a request, where is it defined, "
            "where is it enforced, and what HTTP status code does the client get when it is exceeded?")
EXPECT = "1000,400"


def arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def run(mode, question, expect, verbose):
    agent = s7.Agent(mode)
    out = io.StringIO()
    outcome = ""
    with contextlib.redirect_stdout(sys.stdout if verbose else out):
        try:
            answer = agent.ask(question)
            missing = [e for e in expect if e not in answer]
            outcome = "correct" if not missing else f"incomplete (missing {', '.join(missing)})"
        except s7.ContextOverflow:
            answer, outcome = "", "CONTEXT OVERFLOW"
    return agent.stats, outcome, answer


def main():
    if not s7.API_KEY or not s7.MODEL:
        raise SystemExit("Set OPENAI_API_KEY and MODEL (and OPENAI_BASE_URL if not using OpenAI).")
    question = arg("--question", QUESTION)
    expect = [e.strip() for e in arg("--expect", EXPECT).split(",") if e.strip()]
    verbose = "--verbose" in sys.argv
    s7.check_repo()
    files, tokens = s7.repo_stats()
    print(f"Repo: {s7.REPO}  ({files:,} files, ~{tokens:,} tokens; budget {s7.BUDGET:,})")
    print(f"Question: {question}\n")
    rows = []
    for mode in ("naive", "nav", "subagent"):
        print(f"running {mode} ...", flush=True)
        stats, outcome, answer = run(mode, question, expect, verbose)
        rows.append((mode, stats, outcome))
        if answer:
            print(f"  answer: {answer[:300]}{'...' if len(answer) > 300 else ''}\n")
    print(f"\n{'mode':<10}{'steps':>6}{'peak ctx':>11}{'tokens sent':>13}{'+sub-agent':>12}{'compact':>9}  outcome")
    for mode, s, outcome in rows:
        print(f"{mode:<10}{s['steps']:>6}{s['peak']:>11,}{s['sent']:>13,}{s['subagent_tokens']:>12,}"
              f"{s['compactions']:>9}  {outcome}")
    print("\npeak ctx = largest single request (must stay under the budget); "
          "tokens sent = what you pay for; +sub-agent = tokens the sub-agent used in its own context.")


if __name__ == "__main__":
    main()
