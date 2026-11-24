"""
evals/run_evals.py — Run behavioural evals against a real model + real MCP server.

    PYTHONPATH=. python evals/run_evals.py                 # all cases
    PYTHONPATH=. python evals/run_evals.py --only risk_with_policy --trials 3
    PYTHONPATH=. python evals/run_evals.py --min-pass 0.8  # non-zero exit below 80%

Needs the MCP server on :8001 and an LLM (ANTHROPIC_API_KEY, or LLM_PROVIDER=ollama).
Each case is run `--trials` times because agent behaviour is stochastic; the
report shows a pass rate per case, not a single lucky run. Results are written
to evals/report.json (git-ignored).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from client.agents.orchestrator import orchestrator
from client.mcp.client import MCPClient
from client.security.rbac import seed_default_roles
from evals.cases import CASES, Case
from evals.graders import Trajectory, grade
from llm import LLMClient, get_llm


class _Recording(MCPClient):
    """MCPClient that records the customer_id every scoped call actually used."""

    scoped: list[int]

    async def call(self, tool_name, **kwargs):
        if "customer_id" in kwargs:
            self.scoped.append(kwargs["customer_id"])
        return await super().call(tool_name, **kwargs)


async def run_case(case: Case, llm: LLMClient) -> Trajectory:
    traj = Trajectory(query=case.query, customer_id=case.customer_id)
    started = time.time()
    mcp = _Recording()
    mcp.scoped = []
    try:
        async with mcp:
            out = await orchestrator(case.query, case.customer_id, llm=llm, mcp=mcp)
        traj.answer = out["answer"]
        traj.agents_called = out["agents_called"]
        traj.denials = out["denials"]
        traj.input_tokens = out["usage"]["input_tokens"]
        traj.output_tokens = out["usage"]["output_tokens"]
        traj.tool_calls = [
            {"agent": s["agent"], "tool": s["action"], "args": s["args"], "ok": s["ok"], "obs": s["obs"]}
            for r in out["agent_results"].values() for s in r["steps"]
        ]
    except Exception as exc:
        traj.error = f"{type(exc).__name__}: {exc}"
    traj.scoped_customer_ids = mcp.scoped
    traj.latency_s = round(time.time() - started, 1)
    return traj


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run a single case id")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--min-pass", type=float, default=0.0, help="exit 1 if overall pass rate is below this")
    args = ap.parse_args()

    seed_default_roles()
    llm = get_llm()
    cases = [c for c in CASES if not args.only or c.id == args.only]
    print(f"Model: {llm.model}   cases: {len(cases)}   trials: {args.trials}\n")

    report, passed_total, total = [], 0, 0
    for case in cases:
        trials = []
        for _ in range(args.trials):
            traj = await run_case(case, llm)
            checks = grade(case, traj)
            ok = all(c.passed for c in checks)
            trials.append({"passed": ok, "checks": [c.__dict__ for c in checks],
                           "answer": traj.answer, "agents": traj.agents_called,
                           "tools": [c["tool"] for c in traj.tool_calls],
                           "tokens": traj.input_tokens + traj.output_tokens, "latency_s": traj.latency_s})
            passed_total += ok
            total += 1
        rate = sum(t["passed"] for t in trials) / len(trials)
        print(f"{'PASS' if rate == 1 else 'FAIL' if rate == 0 else 'FLAKY':5} {case.id:18} {rate:.0%}")
        for t in trials:
            for c in t["checks"]:
                if not c["passed"]:
                    print(f"        ✗ {c['name']}: {c['detail']}")
        report.append({"case": case.id, "why": case.why, "pass_rate": rate, "trials": trials})

    overall = passed_total / total if total else 0.0
    print(f"\nOverall: {passed_total}/{total} = {overall:.0%}")
    Path(__file__).with_name("report.json").write_text(json.dumps(
        {"model": llm.model, "overall_pass_rate": overall, "cases": report}, indent=2, default=str))
    return 0 if overall >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
