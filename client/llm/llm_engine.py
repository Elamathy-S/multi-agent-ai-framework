"""
server/llm/llm_engine.py — LLM engine using Ollama with phi3.
"""

import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL      = os.getenv("OLLAMA_MODEL", "phi3")


def safe_json_llm(system_prompt: str, user_prompt: str) -> dict:
    """
    Send prompts to Ollama and return a parsed JSON dict.
    Does NOT use format:json mode — phi3 leaks prompts with that setting.
    Instead we extract JSON manually from the raw response.
    """
    # Keep system prompt very short for phi3
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 300,   # cap output length to prevent rambling
        },
    }

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=300,
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"].strip()

    except requests.ConnectionError:
        return {"error": "Ollama is not running. Start with: ollama serve"}
    except requests.Timeout:
        return {"error": "Ollama timed out — model may still be loading, try again"}
    except Exception as exc:
        return {"error": f"Ollama request failed: {exc}"}

    return _extract_json(raw)


def _extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from a string.
    Handles prompt leakage, markdown fences, and extra text around the JSON.
    """
    # Strip markdown fences
    text = re.sub(r"```[a-z]*", "", text).strip()

    # Find the first { and last } to isolate JSON
    start = text.find("{")
    end   = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return {"error": "No JSON found in response", "raw_response": text[:200]}

    candidate = text[start:end + 1]

    # Remove any endoftext or special tokens inside the JSON
    candidate = re.sub(r"<[^>]+>", "", candidate)          # <|endoftext|> etc
    candidate = re.sub(r"<[|][^|]+[|]>", "", candidate)  # strip <|endoftext|> etc

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Try to fix common phi3 issues — trailing commas, single quotes
        candidate = re.sub(r",\s*}", "}", candidate)
        candidate = re.sub(r",\s*]", "]", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return {"error": "Could not parse JSON", "raw_response": candidate[:200]}