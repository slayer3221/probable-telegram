#!/usr/bin/env python3
"""Preflight: confirm the Anthropic key, workspace binding and model are usable
with one minimal request. Fails fast so a misconfigured run stops before it
spends Regulations.gov calls.

Usage:
    python3 scripts/check_llm_access.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import LLM_MODEL, LLM_WORKSPACE_ID  # noqa: E402
from pipeline.llm import LLM  # noqa: E402


def main():
    try:
        reply = LLM(stage="preflight").preflight()
    except Exception as exc:  # noqa: BLE001
        print(f"LLM access check failed: {exc}")
        sys.exit(1)
    scope = f"workspace {LLM_WORKSPACE_ID}" if LLM_WORKSPACE_ID else "workspace-scoped key"
    print(f"LLM access OK: model {LLM_MODEL}, {scope}, reply={reply!r}")


if __name__ == "__main__":
    main()
