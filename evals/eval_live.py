"""
evals/eval_live.py — Live AI decision quality evals.

Unlike the offline evals (eval_dataset.py) which test deterministic code,
these run actual queries through the full agent pipeline with real LLM
calls and real MCP tool execution.

These will NOT all pass at 100% — that's the point. They measure how
well the AI reasons, and the score depends on the model (phi3 vs llama3),
prompt engineering, and RAG quality. Tracking this score over time is
how you measure improvement.

Requires: MCP server running, Ollama running, database seeded.

Usage:
    PYTHONPATH=. python evals/eval_live.py
"""

import asyncio
import json
import sys
import time
from datetime import datetime

from client.mcp.client import MCPClient, MCPConnectionError


# ---------------------------------------------------------------------------
# Live eval cases — each tests a real AI decision
# ---------------------------------------------------------------------------
LIVE_EVALS = [
    # ── ReAct reasoning: does the agent stop when it has enough? ──────
    {
        "id": "live_01",
        "category": "ReAct Efficiency",
        "query": "who is customer 1",
        "customer_id": 1,
        "agent": "customer",
        "description": "Simple profile query should need only 1 tool call",
        "check": lambda r: (
            len(r.get("steps", [])) <= 2,
            f"Used {len(r.get('steps', []))} steps, expected ≤2"
        ),
    },
    {
        "id": "live_02",
        "category": "ReAct Efficiency",
        "query": "check risk level",
        "customer_id": 1,
        "agent": "risk",
        "description": "Risk query should call get_risk_score",
        "check": lambda r: (
            any(s.get("action") == "get_risk_score" for s in r.get("steps", [])),
            f"Tools called: {[s.get('action') for s in r.get('steps', [])]}"
        ),
    },
    {
        "id": "live_03",
        "category": "ReAct Efficiency",
        "query": "what is the credit score for this customer",
        "customer_id": 1,
        "agent": "loan",
        "description": "Credit-only query should call get_credit_score (not both loan tools)",
        "check": lambda r: (
            any(s.get("action") == "get_credit_score" for s in r.get("steps", [])),
            f"Tools called: {[s.get('action') for s in r.get('steps', [])]}"
        ),
    },

    # ── Data quality: does the answer contain the right information? ──
    {
        "id": "live_04",
        "category": "Answer Quality",
        "query": "who is customer 1",
        "customer_id": 1,
        "agent": "customer",
        "description": "Answer should contain the customer's actual name",
        "check": lambda r: (
            bool(r.get("answer")) and r["answer"] not in ("Data retrieved.", ""),
            f"Answer: '{r.get('answer', '')[:80]}'"
        ),
    },
    {
        "id": "live_05",
        "category": "Answer Quality",
        "query": "check risk and fraud",
        "customer_id": 1,
        "agent": "risk",
        "description": "Risk answer should mention a score or level",
        "check": lambda r: (
            any(kw in r.get("answer", "").lower() for kw in ["risk", "score", "low", "medium", "high"]),
            f"Answer: '{r.get('answer', '')[:80]}'"
        ),
    },
    {
        "id": "live_06",
        "category": "Answer Quality",
        "query": "show portfolio and profit loss",
        "customer_id": 1,
        "agent": "trading",
        "description": "Trading answer should mention holdings or PnL",
        "check": lambda r: (
            any(kw in r.get("answer", "").lower() for kw in ["portfolio", "pnl", "profit", "loss", "holding", "position"]),
            f"Answer: '{r.get('answer', '')[:80]}'"
        ),
    },

    # ── Reasoning mode: did the agent use ReAct or fall back? ─────────
    {
        "id": "live_07",
        "category": "ReAct vs Fallback",
        "query": "who is customer 1",
        "customer_id": 1,
        "agent": "customer",
        "description": "Simple query should ideally use ReAct (not fallback)",
        "check": lambda r: (
            r.get("reasoning_mode") == "react",
            f"Mode: {r.get('reasoning_mode', 'unknown')}"
        ),
    },
    {
        "id": "live_08",
        "category": "ReAct vs Fallback",
        "query": "check risk level for customer 1",
        "customer_id": 1,
        "agent": "risk",
        "description": "Risk query should ideally use ReAct",
        "check": lambda r: (
            r.get("reasoning_mode") == "react",
            f"Mode: {r.get('reasoning_mode', 'unknown')}"
        ),
    },
    {
        "id": "live_09",
        "category": "ReAct vs Fallback",
        "query": "full loan review for customer 1",
        "customer_id": 1,
        "agent": "loan",
        "description": "Loan review should ideally use ReAct",
        "check": lambda r: (
            r.get("reasoning_mode") == "react",
            f"Mode: {r.get('reasoning_mode', 'unknown')}"
        ),
    },

    # ── Permission enforcement: are denials actually happening? ───────
    {
        "id": "live_10",
        "category": "Security",
        "query": "who is customer 1",
        "customer_id": 1,
        "agent": "customer",
        "description": "Customer agent should have zero permission denials",
        "check": lambda r: (
            len(r.get("denials", [])) == 0,
            f"Denials: {r.get('denials', [])}"
        ),
    },

    # ── Observation completeness: did tools return real data? ─────────
    {
        "id": "live_11",
        "category": "Data Completeness",
        "query": "check risk for customer 1",
        "customer_id": 1,
        "agent": "risk",
        "description": "Risk observations should contain score data (not errors)",
        "check": lambda r: (
            any(
                isinstance(s.get("obs"), dict) and "risk_score" in s.get("obs", {})
                for s in r.get("steps", [])
            ),
            f"Observations: {[s.get('action') + ':' + ('ok' if 'error' not in str(s.get('obs','')) else 'err') for s in r.get('steps',[])]}"
        ),
    },
    {
        "id": "live_12",
        "category": "Data Completeness",
        "query": "show portfolio",
        "customer_id": 1,
        "agent": "trading",
        "description": "Portfolio observation should be a non-empty list",
        "check": lambda r: (
            any(
                isinstance(s.get("obs"), list) and len(s.get("obs", [])) > 0
                for s in r.get("steps", [])
            ),
            f"Observations: {[type(s.get('obs')).__name__ for s in r.get('steps',[])]}"
        ),
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
async def run_live_evals():
    # Check MCP server
    try:
        async with MCPClient() as mcp:
            tools = await mcp.list_tools()
            print(f"\n  MCP server connected — {len(tools)} tools available")
    except MCPConnectionError:
        print("\n  ❌ MCP server not running. Start it first:")
        print("     PYTHONPATH=. python3 -m server.mcp_server --http --port 8001")
        return None

    agent_fns = {
        "customer": ("client.agents.customer_agent", "customer_agent"),
        "loan":     ("client.agents.loan_agent", "loan_agent"),
        "risk":     ("client.agents.risk_agent", "risk_agent"),
        "trading":  ("client.agents.trading_agent", "trading_agent"),
    }

    print()
    print("=" * 60)
    print(f"  LIVE EVAL REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Running {len(LIVE_EVALS)} evals with real LLM + MCP calls")
    print("=" * 60)

    results_by_category = {}
    all_results = []

    current_category = None
    for case in LIVE_EVALS:
        cat = case["category"]
        if cat != current_category:
            current_category = cat
            print(f"\n  {cat}")
            print(f"  {'─' * 50}")

        # Run the agent
        module_name, fn_name = agent_fns[case["agent"]]
        module = __import__(module_name, fromlist=[fn_name])
        agent_fn = getattr(module, fn_name)

        start = time.time()
        try:
            async with MCPClient() as mcp:
                result = await agent_fn(mcp, case["query"], case["customer_id"])
            latency = (time.time() - start) * 1000

            passed, detail = case["check"](result)
        except Exception as e:
            latency = (time.time() - start) * 1000
            passed = False
            detail = f"Exception: {e}"
            result = {}

        status = "✅" if passed else "❌"
        print(f"    {status} {case['id']}: {case['description']} ({latency:.0f}ms)")
        if not passed:
            print(f"       → {detail}")

        entry = {
            "id": case["id"],
            "category": cat,
            "passed": passed,
            "detail": detail,
            "latency_ms": round(latency),
            "reasoning_mode": result.get("reasoning_mode", "unknown"),
        }
        all_results.append(entry)

        if cat not in results_by_category:
            results_by_category[cat] = {"passed": 0, "total": 0}
        results_by_category[cat]["total"] += 1
        if passed:
            results_by_category[cat]["passed"] += 1

    # Summary table
    total_passed = sum(c["passed"] for c in results_by_category.values())
    total_cases = sum(c["total"] for c in results_by_category.values())
    overall_pct = (total_passed / total_cases * 100) if total_cases else 0

    print()
    print("┌──────────────────────┬────────┬────────┬─────────┐")
    print("│ Category             │ Passed │ Total  │ Score   │")
    print("├──────────────────────┼────────┼────────┼─────────┤")

    for cat, data in results_by_category.items():
        pct = (data["passed"] / data["total"] * 100) if data["total"] else 0
        name = cat[:20].ljust(20)
        p = str(data["passed"]).center(6)
        t = str(data["total"]).center(6)
        s = f"{pct:.0f}%".rjust(7)
        print(f"│ {name} │ {p} │ {t} │ {s} │")

    print("├──────────────────────┼────────┼────────┼─────────┤")
    p = str(total_passed).center(6)
    t = str(total_cases).center(6)
    s = f"{overall_pct:.0f}%".rjust(7)
    print(f"│ {'OVERALL'.ljust(20)} │ {p} │ {t} │ {s} │")
    print("└──────────────────────┴────────┴────────┴─────────┘")

    # Reasoning mode breakdown
    modes = {}
    for r in all_results:
        m = r["reasoning_mode"]
        modes[m] = modes.get(m, 0) + 1

    print(f"\n  Reasoning modes: {modes}")
    print(f"  Avg latency: {sum(r['latency_ms'] for r in all_results) / len(all_results):.0f}ms")

    # Save
    report = {
        "timestamp": datetime.now().isoformat(),
        "type": "live",
        "overall_score": round(overall_pct, 1),
        "total_passed": total_passed,
        "total_cases": total_cases,
        "categories": {
            cat: {**data, "score": round((data["passed"] / data["total"] * 100) if data["total"] else 0, 1)}
            for cat, data in results_by_category.items()
        },
        "reasoning_modes": modes,
        "results": all_results,
    }

    with open("evals/eval_live_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to evals/eval_live_report.json\n")

    return report


if __name__ == "__main__":
    result = asyncio.run(run_live_evals())
    if result:
        sys.exit(0 if result["overall_score"] >= 70 else 1)
    else:
        sys.exit(1)