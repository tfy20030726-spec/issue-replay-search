"""Fetch a new title snapshot from public GitHub REST endpoints (no account needed)."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
REPO = "microsoft/vscode"
WINDOWS = [
    ("2026-06-01", "2026-08-31"),
    ("2026-09-01", "2026-09-30"),
    ("2026-10-01", "2026-10-31"),
    ("2026-11-01", "2026-11-17"),
]
KEYWORDS = ["terminal", "editor", "explorer"]
PER_STRATUM = 35
SKIP = re.compile(
    r"\b(cve|xss|exploit|security|vulnerability|injection|malware|password|credentials?|"
    r"tokens?|secrets?|attack|attackers?|copilot|(?:sub-?)?agents?|ssh|wsl|chat|mcp|"
    r"sandbox\w*|bypass\w*|trust|code execution|destructive|permissions?|"
    r"auto[- ]?approv\w*|approvals?|automation\w*|harness|auth(?:orization|entication)?)\b"
    r"|[\w.+-]+@[\w.-]+\.[a-z]{2,}|[/\\]users[/\\]|https?://",
    re.I,
)


def get_json(path):
    headers = {"User-Agent": "issue-replay-search", "Accept": "application/vnd.github+json"}
    req = Request(API + path, headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"GitHub returned HTTP {exc.code} for {path}; retry later.") from exc


def select_fields(item):
    return {key: item[key] for key in ("number", "title", "created_at")}


def fetch_snapshot(labels):
    docs = {}
    for begin, end in WINDOWS:
        for term in KEYWORDS:
            query = f"repo:{REPO} is:issue in:title {term} created:{begin}..{end}"
            params = dict(q=query, sort="created", order="asc", per_page=PER_STRATUM)
            result = get_json("/search/issues?" + urlencode(params))
            if result["incomplete_results"]:
                raise RuntimeError(f"Incomplete search response for {query}. Retry later.")
            for item in result["items"]:
                if not SKIP.search(item["title"]):
                    docs[item["number"]] = select_fields(item)
            print(f"{begin}..{end} {term} -> {len(docs)} unique titles", flush=True)
            time.sleep(7)  # Unauthenticated GitHub issue search has its own rate limit.
    pinned = {row[key] for row in labels for key in ("query", "canonical")}
    for number in sorted(pinned - docs.keys()):
        item = get_json(f"/repos/{REPO}/issues/{number}")
        if "pull_request" in item or SKIP.search(item["title"]):
            raise ValueError(f"Pinned issue #{number} needs manual review.")
        docs[number] = select_fields(item)
        time.sleep(1)
    return sorted(docs.values(), key=lambda row: (row["created_at"], row["number"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="write a new JSON file")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new file and review the differences")
    pairs = json.loads((ROOT / "data" / "duplicates.json").read_text(encoding="utf-8"))
    docs = fetch_snapshot(pairs)
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(docs, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(docs)} issues retrieved at {datetime.now(timezone.utc).isoformat()} UTC")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        sys.exit(str(error))
