"""Search a frozen set of public VS Code issue titles and replay confirmed duplicate links."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
METHODS = ("overlap", "bm25")
STOP = set("a an and are as at be by for from in is it of on or that the to when with".split())


def read_data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def utc_cutoff(value):
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value += "T00:00:00Z"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("A timestamp must include an offset or Z.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def tokens(title):
    return [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOP]


def rank(issues, title, before):
    """Rank titles sharing a token, using statistics from the eligible corpus only."""
    cutoff = datetime.fromisoformat(before.replace("Z", "+00:00"))
    documents = [
        d for d in issues
        if datetime.fromisoformat(d["created_at"].replace("Z", "+00:00")) < cutoff
    ]
    terms = set(tokens(title))
    results = {method: [] for method in METHODS}
    if not terms or not documents:
        return len(documents), results

    words = {d["number"]: tokens(d["title"]) for d in documents}
    overlap = {number: len(terms.intersection(row)) for number, row in words.items()}
    results["overlap"] = sorted(
        (number for number, score in overlap.items() if score),
        key=lambda number: (-overlap[number], number),
    )

    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE titles USING fts5(words)")
        con.executemany("INSERT INTO titles(rowid, words) VALUES (?, ?)",
                        [(number, " ".join(row)) for number, row in words.items()])
        # Tokenization only emits ASCII letters and numbers. Quotes keep FTS keywords literal.
        expression = " OR ".join(f'"{term}"' for term in sorted(terms))
        rows = con.execute(
            "SELECT rowid FROM titles WHERE titles MATCH ? ORDER BY bm25(titles), rowid",
            (expression,),
        )
        results["bm25"] = [number for (number,) in rows]
    finally:
        con.close()
    return len(documents), results


def replay_rows(issues, duplicates):
    by_id = {item["number"]: item for item in issues}
    if len(by_id) != len(issues):
        raise ValueError("Snapshot contains duplicate issue numbers.")
    if len({pair["query"] for pair in duplicates}) != len(duplicates):
        raise ValueError("Snapshot contains duplicate query labels.")
    rows = []
    for pair in duplicates:
        query, canonical = by_id[pair["query"]], by_id[pair["canonical"]]
        if not canonical["created_at"] < query["created_at"] <= pair["confirmed_at"]:
            raise ValueError(f"Invalid timestamps for #{query['number']}.")
        count, rankings = rank(issues, query["title"], query["created_at"])
        ranks = {
            method: (ids.index(canonical["number"]) + 1 if canonical["number"] in ids else None)
            for method, ids in rankings.items()
        }
        rows.append({
            **pair,
            "candidate_count": count,
            "results": {method: ids[:5] for method, ids in rankings.items()},
            "ranks": ranks,
        })
    return rows


def metrics(rows):
    if not rows:
        raise ValueError("An evaluation needs at least one labeled query.")
    result = {}
    for method in METHODS:
        positions = [row["ranks"][method] for row in rows]
        top = [pos for pos in positions if pos is not None and pos <= 5]
        result[method] = {
            "queries": len(rows),
            "hits_at_1": sum(pos == 1 for pos in positions),
            "hits_at_5": len(top),
            "mrr_at_5": round(sum(1 / pos for pos in top) / len(rows), 4),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="search titles available before a UTC instant")
    search.add_argument("title")
    search.add_argument("--before", required=True, help="YYYY-MM-DD or timestamp with UTC offset")
    search.add_argument("--method", choices=METHODS, default="bm25")
    replay = commands.add_parser("replay", help="replay every labeled duplicate")
    replay.add_argument("--output", type=Path, help="save complete replay as JSON")
    args = parser.parse_args()
    docs = read_data("issues.json")
    if args.command == "search":
        cutoff = utc_cutoff(args.before)
        count, rankings = rank(docs, args.title, cutoff)
        by_id = {doc["number"]: doc for doc in docs}
        print(f"{args.method} | before {cutoff} | {count} candidate titles")
        hits = rankings[args.method][:5]
        if not hits:
            print("No matching titles.")
        for i, number in enumerate(hits, 1):
            print(f"{i}. #{number} {by_id[number]['title']}")
            print(f"   https://github.com/microsoft/vscode/issues/{number}")
        return
    rows = replay_rows(docs, read_data("duplicates.json"))
    summary = metrics(rows)
    for method, score in summary.items():
        print(f"{method:7}  Top 1 {score['hits_at_1']}/{score['queries']}  "
              f"Top 5 {score['hits_at_5']}/{score['queries']}  MRR@5 {score['mrr_at_5']:.4f}")
    for row in rows:
        def position(method):
            return row["ranks"][method] or "-"
        print(f"#{row['query']} -> #{row['canonical']}  ({row['candidate_count']} candidates)  "
              f"overlap {position('overlap')} | bm25 {position('bm25')}")
    if args.output:
        payload = json.dumps({"rows": rows, "metrics": summary}, ensure_ascii=False, indent=2)
        args.output.write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.OperationalError, KeyError) as error:
        sys.exit(str(error))
