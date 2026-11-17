"""Build an offline replay from the rankers' saved output."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    issues = json.loads((ROOT / "data/issues.json").read_text(encoding="utf-8-sig"))
    report = json.loads((ROOT / "reports/replay.json").read_text(encoding="utf-8-sig"))
    rows = report["rows"]
    if not rows:
        raise ValueError("Replay contains no confirmed pairs")
    referenced = {row[key] for row in rows for key in ("query", "canonical")}
    for row in rows:
        for ranked in row["results"].values():
            referenced.update(ranked)
    titles = {item["number"]: [item["title"], item["created_at"]] for item in issues
              if item["number"] in referenced}
    if referenced.difference(titles):
        raise ValueError("At least one replay candidate is missing from the snapshot")
    payload = {"issues": titles, "rows": rows, "size": len(issues)}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", r"\u003c")
    template = Path(__file__).with_name("replay.html").read_text(encoding="utf-8-sig")
    (ROOT / "index.html").write_text(template.replace("__REPLAY_DATA__", data), encoding="utf-8")


if __name__ == "__main__":
    build()
