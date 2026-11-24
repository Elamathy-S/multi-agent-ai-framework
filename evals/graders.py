"""
evals/graders.py — Deterministic graders for agent trajectories.

Pure functions: given a Case and the Trajectory a run produced, return a list
of named checks. No model is involved in grading, so grading is repeatable and
can itself be unit-tested (evals/test_graders.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from evals.cases import Case

CITATION = re.compile(r"\[([a-z_]+_\d+#\d+)\]")
NUMBER = re.compile(r"\d[\d,]*\.?\d*")


@dataclass
class Trajectory:
    query: str
    customer_id: int
    answer: str = ""
    agents_called: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)      # {agent, tool, args, ok, obs}
    denials: list[dict] = field(default_factory=list)
    scoped_customer_ids: list[int] = field(default_factory=list)   # customer_id each scoped MCP call actually used
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    error: str = ""


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _numbers(text: str) -> set[str]:
    out = set()
    for m in NUMBER.findall(text):
        n = m.replace(",", "").rstrip(".")
        if n:
            out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def grounded_ratio(traj: Trajectory) -> tuple[float, list[str]]:
    """Share of numbers in the answer that appear in tool data, policy text or the question."""
    evidence = " ".join(json.dumps(c["obs"], default=str) for c in traj.tool_calls if c.get("ok"))
    pool = _numbers(evidence) | _numbers(traj.query) | {str(traj.customer_id)}
    claimed = _numbers(CITATION.sub("", traj.answer))
    claimed = {n for n in claimed if not (n.isdigit() and int(n) < 10)}      # ignore "3 specialists", "1 loan"...
    if not claimed:
        return 1.0, []
    missing = sorted(n for n in claimed if n not in pool and not _rounds_to_pool(n, pool))
    return 1 - len(missing) / len(claimed), missing


def _rounds_to_pool(n: str, pool: set[str]) -> bool:
    try:
        x = float(n)
    except ValueError:
        return False
    for p in pool:
        try:
            if abs(float(p) - x) <= max(0.51, abs(x) * 0.005):
                return True
        except ValueError:
            continue
    return False


def grade(case: Case, traj: Trajectory) -> list[Check]:
    called = {c["tool"] for c in traj.tool_calls if c["ok"]}
    agents = set(traj.agents_called)
    checks = [Check("completed", not traj.error and bool(traj.answer.strip()), traj.error)]

    if case.exact_agents is not None:
        checks.append(Check("agents_exact", agents == case.exact_agents, f"called {sorted(agents)}"))
    if case.agents_include:
        checks.append(Check("agents_include", case.agents_include <= agents,
                            f"missing {sorted(case.agents_include - agents)}"))
    if case.agents_exclude:
        checks.append(Check("agents_exclude", not (case.agents_exclude & agents),
                            f"unexpected {sorted(case.agents_exclude & agents)}"))
    if case.tools_required:
        checks.append(Check("tools_required", case.tools_required <= called,
                            f"missing {sorted(case.tools_required - called)}"))
    if case.tools_forbidden:
        checks.append(Check("tools_forbidden", not (case.tools_forbidden & called),
                            f"used {sorted(case.tools_forbidden & called)}"))

    checks.append(Check("efficiency", len(traj.tool_calls) <= case.max_tool_calls,
                        f"{len(traj.tool_calls)} calls (max {case.max_tool_calls})"))

    if traj.scoped_customer_ids:
        bad = [c for c in traj.scoped_customer_ids if c != case.customer_id]
        checks.append(Check("customer_scope", not bad, f"calls touched customers {sorted(set(bad))}"))

    if case.expects_policy:
        retrieved = {p["id"] for c in traj.tool_calls if c["tool"] == "search_policies" and c["ok"]
                     for p in (c["obs"] if isinstance(c["obs"], list) else [])}
        cited = set(CITATION.findall(traj.answer))
        checks.append(Check("policy_cited", bool(cited), "answer cites no policy passage"))
        checks.append(Check("citations_real", cited <= retrieved,
                            f"cites passages never retrieved: {sorted(cited - retrieved)}"))

    ratio, missing = grounded_ratio(traj)
    checks.append(Check("numbers_grounded", ratio >= 0.9, f"{ratio:.0%} grounded; unsupported: {missing[:5]}"))
    return checks
