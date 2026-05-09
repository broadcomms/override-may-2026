"""scripts/find_watsonx_region.py — locate which watsonx.ai region hosts the project.

Tries each public watsonx region and reports which one accepts the
WATSONX_PROJECT_ID from .env. Run when the configured WATSONX_URL fails with
"project not found".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from ibm_watsonx_ai import APIClient, Credentials

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

REGIONS = [
    ("us-south",  "https://us-south.ml.cloud.ibm.com"),
    ("eu-de",     "https://eu-de.ml.cloud.ibm.com"),
    ("eu-gb",     "https://eu-gb.ml.cloud.ibm.com"),
    ("jp-tok",    "https://jp-tok.ml.cloud.ibm.com"),
    ("au-syd",    "https://au-syd.ml.cloud.ibm.com"),
    ("ca-tor",    "https://ca-tor.ml.cloud.ibm.com"),
]


def main() -> int:
    api_key = os.environ.get("WATSONX_API_KEY")
    project_id = os.environ.get("WATSONX_PROJECT_ID")
    if not api_key or not project_id:
        sys.exit("missing WATSONX_API_KEY or WATSONX_PROJECT_ID in .env")

    print(f"probing for project {project_id[:4]}…{project_id[-4:]}\n")

    found = None
    for name, url in REGIONS:
        try:
            client = APIClient(credentials=Credentials(api_key=api_key, url=url),
                               project_id=project_id)
            client.set.default_project(project_id)
            print(f"  ✓ {name:8s} {url}")
            found = (name, url)
        except Exception as e:
            msg = str(e)
            if "not_found" in msg or "404" in msg:
                print(f"  ✗ {name:8s} project not in this region")
            elif "Unauthorized" in msg or "401" in msg or "BXNIM" in msg:
                print(f"  ! {name:8s} auth rejected — API key invalid for this region")
            else:
                short = msg.split("\n")[0][:80]
                print(f"  ? {name:8s} {short}")

    if found:
        print(f"\n→ update .env: WATSONX_URL={found[1]}")
        return 0
    print("\nProject not found in any public region. Check WATSONX_PROJECT_ID and that the API key has access.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
