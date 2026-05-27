"""scripts/test_watsonx_embedding.py — smoke test for watsonx.ai embeddings.

Reads GRANITE_EMBEDDING from .env, embeds two short strings, and reports the
output dimensionality. Used to lock the embedding contract for P2.5
regulation chunk retrieval.

Usage:
    .venv/bin/python scripts/test_watsonx_embedding.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import Embeddings

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
    model_id = os.environ.get(
        "GRANITE_EMBEDDING", "ibm/granite-embedding-278m-multilingual"
    )

    creds = Credentials(api_key=api_key, url=url)

    print(f"  url:        {url}")
    print(f"  project_id: {project_id[:4]}…{project_id[-4:]}")
    print(f"  embedding:  {model_id}")
    print()

    print(f"→ embedding two strings with {model_id} …")
    try:
        e = Embeddings(model_id=model_id, credentials=creds, project_id=project_id)
        vecs = e.embed_documents(
            texts=[
                "Energy released from the ES into the MGU-K shall not exceed the per-lap cap.",
                "Sporting Regulations govern Overtake Mode availability.",
            ]
        )
    except Exception as ex:
        print(f"  FAIL: {type(ex).__name__}: {ex}")
        return 1

    if not vecs or not isinstance(vecs, list) or len(vecs) != 2:
        print(f"  FAIL: expected 2 vectors, got {type(vecs).__name__}")
        return 1

    dim_a, dim_b = len(vecs[0]), len(vecs[1])
    print(f"  OK → 2 vectors returned")
    print(f"     vector 0: dim={dim_a}, head={vecs[0][:3]}")
    print(f"     vector 1: dim={dim_b}, head={vecs[1][:3]}")

    if dim_a != dim_b:
        print(f"  FAIL: vector dimensions differ ({dim_a} vs {dim_b})")
        return 1

    print()
    print(f"✓ watsonx.ai embedding smoke test passed (dim={dim_a})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
