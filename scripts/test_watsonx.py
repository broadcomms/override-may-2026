"""scripts/test_watsonx.py — smoke test for watsonx.ai connectivity.

Loads credentials from .env, never echoes the API key, and runs a tiny
generation against each configured Granite model. Used to close gate G-1
under the watsonx-based runtime (replacing the previous Ollama path).

Usage:
    .venv/bin/python scripts/test_watsonx.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from ibm_watsonx_ai import APIClient, Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def get_required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"missing required env var: {name}")
    return value


def main() -> int:
    api_key = get_required("WATSONX_API_KEY")
    url = get_required("WATSONX_URL")
    project_id = get_required("WATSONX_PROJECT_ID")

    instruct_id = os.environ.get("GRANITE_INSTRUCT", "ibm/granite-4-h-small")
    guardian_id = os.environ.get("GRANITE_GUARDIAN", "ibm/granite-guardian-3-8b")

    creds = Credentials(api_key=api_key, url=url)

    print(f"  url:        {url}")
    print(f"  project_id: {project_id[:4]}…{project_id[-4:]}")
    print(f"  instruct:   {instruct_id}")
    print(f"  guardian:   {guardian_id}")
    print()

    print("→ verifying credentials …")
    try:
        client = APIClient(credentials=creds, project_id=project_id)
        client.set.default_project(project_id)
    except Exception as e:  # pragma: no cover
        print(f"  FAIL: APIClient init failed: {type(e).__name__}: {e}")
        return 1
    print("  OK\n")

    print(f"→ generating with {instruct_id} …")
    try:
        m = ModelInference(model_id=instruct_id, credentials=creds, project_id=project_id)
        out = m.generate_text(
            prompt="Reply with exactly: pong",
            params={"max_new_tokens": 8, "temperature": 0.0, "decoding_method": "greedy"},
        )
        print(f"  OK → {out!r}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return 1
    print()

    print(f"→ generating with {guardian_id} …")
    try:
        m = ModelInference(model_id=guardian_id, credentials=creds, project_id=project_id)
        out = m.generate_text(
            prompt="Is the sky blue? Yes or No.",
            params={"max_new_tokens": 4, "temperature": 0.0, "decoding_method": "greedy"},
        )
        print(f"  OK → {out!r}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        if "ibm/ibm/" in guardian_id:
            print("  HINT: GRANITE_GUARDIAN has a doubled 'ibm/' prefix in .env.")
        return 1
    print()

    print("✓ watsonx.ai smoke test passed for all configured models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
