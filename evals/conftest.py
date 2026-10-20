"""
evals/conftest.py — Eval configuration.

Adds --run-integration flag for evals that need live servers.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration evals that need MCP server + Ollama",
    )