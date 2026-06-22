#!/usr/bin/env python3
"""Create and label seed issues on the Superset fork.

Usage:
    python seed/create_issues.py

Requires environment variables:
    GITHUB_TOKEN    - Personal access token with repo scope
    GITHUB_OWNER    - Your GitHub org or username
    GITHUB_REPO     - Repository name (default: superset)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
import yaml

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env from the repo root if present
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        for line in _env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

OWNER = os.environ.get("GITHUB_OWNER", "")
REPO = os.environ.get("GITHUB_REPO", "superset")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SEED_FILE = Path(__file__).parent / "seed_issues.yaml"


async def ensure_label(client: httpx.AsyncClient, label: str) -> None:
    """Create the auto-remediate label if it doesn't exist."""
    resp = await client.get(f"/repos/{OWNER}/{REPO}/labels/{label}")
    if resp.status_code == 200:
        return
    await client.post(
        f"/repos/{OWNER}/{REPO}/labels",
        json={"name": label, "color": "7057ff", "description": "Auto-remediated by Devin"},
    )
    print(f"  Created label: {label}")


async def create_issue(
    client: httpx.AsyncClient,
    title: str,
    body: str,
    label: str,
) -> dict:
    resp = await client.post(
        f"/repos/{OWNER}/{REPO}/issues",
        json={"title": title, "body": body, "labels": [label]},
    )
    resp.raise_for_status()
    return resp.json()


async def main() -> None:
    if not TOKEN or not OWNER:
        print("ERROR: Set GITHUB_TOKEN and GITHUB_OWNER environment variables.")
        sys.exit(1)

    data = yaml.safe_load(SEED_FILE.read_text())
    default_label: str = data["label"]
    issues: list[dict] = data["issues"]

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=15.0,
    ) as client:
        print(f"Target repo: {OWNER}/{REPO}")
        print(f"Ensuring label '{default_label}' exists…")
        await ensure_label(client, default_label)

        for i, issue in enumerate(issues, 1):
            print(f"\n[{i}/{len(issues)}] Creating: {issue['title'][:70]}…")
            result = await create_issue(
                client,
                title=issue["title"],
                body=issue["body"],
                label=default_label,
            )
            url = result.get("html_url", "")
            number = result.get("number", "?")
            print(f"  → #{number}: {url}")

    print(f"\n✅ Created {len(issues)} seed issues on {OWNER}/{REPO}.")
    print(f"   Each issue is labeled '{default_label}' and ready to trigger the orchestrator.")


if __name__ == "__main__":
    asyncio.run(main())
