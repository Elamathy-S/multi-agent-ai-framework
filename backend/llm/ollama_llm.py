import requests
import json
import re

OLLAMA_URL = "http://localhost:11434/api/generate"


def ollama_tool_call(query: str, tools_schema: list):

    prompt = f"""
You are a strict JSON API.

Available tools:
{json.dumps(tools_schema, indent=2)}

User query: "{query}"

Rules:
- Output ONLY valid JSON
- Do NOT include explanation
- Do NOT include text outside JSON

Format:
{{
  "tool": "tool_name",
  "arguments": {{
    "customer_id": 1
  }}
}}
"""


    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "phi3",
            "prompt": prompt,
            "stream": False
        },
        timeout=50
    )

    data = response.json()

    # HANDLE ERRORS
    if "response" not in data:
        return {"tool": None, "error": data}

    output = data["response"]

    # CLEAN JSON FROM LLM
    match = re.search(r"\{.*\}", output, re.DOTALL)

    if match:
        try:
            return json.loads(match.group())
        except:
            return {"tool": None}

    return {"tool": None}
