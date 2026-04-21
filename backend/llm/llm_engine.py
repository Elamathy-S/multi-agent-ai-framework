import json
import random


def safe_json_llm(system_prompt: str, user_prompt: str):
    """
    Mock LLM engine for MCP system (NO API REQUIRED)
    Returns structured financial reasoning like a real LLM.
    """

    text = (system_prompt + " " + user_prompt).lower()

    # ---------------------------
    # CREDIT SCORE SIMULATION
    # ---------------------------
    if "credit" in text or "loan" in text:
        base = random.randint(320, 820)

        return {
            "credit_score": base,
            "rating": (
                "Excellent" if base > 750 else
                "Good" if base > 650 else
                "Fair" if base > 550 else
                "Poor"
            ),
            "loan_approval_likelihood": (
                "HIGH" if base > 700 else
                "MEDIUM" if base > 550 else
                "LOW"
            ),
            "risk_factors": [
                "Mock analysis: limited data simulation",
                "No real-time banking feed"
            ],
            "positive_factors": [
                "Simulated stable behavior",
                "No fraud detected in mock system"
            ],
            "reason": "Mock LLM generated financial assessment based on simulated data"
        }

    # ---------------------------
    # RISK SCORING SIMULATION
    # ---------------------------
    if "risk" in text or "fraud" in text:
        score = random.randint(0, 100)

        return {
            "risk_score": score,
            "level": (
                "LOW" if score < 30 else
                "MEDIUM" if score < 70 else
                "HIGH"
            ),
            "fraud_flag": score > 80,
            "reason": "Mock risk model based on synthetic transaction behavior"
        }

    # ---------------------------
    # DEFAULT RESPONSE
    # ---------------------------
    return {
        "message": "Mock LLM could not classify request",
        "input": user_prompt
    }
