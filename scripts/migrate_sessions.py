#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_source(path: Path) -> dict[str, list[dict[str, object]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("source must be a JSON object")
    normalized: dict[str, list[dict[str, object]]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, list):
            normalized[key] = [item for item in value if isinstance(item, dict)]
    return normalized


def write_target(path: Path, payload: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def migrate(source: Path, target: Path) -> tuple[int, int]:
    sessions = read_source(source)
    rows: list[dict[str, object]] = []
    message_count = 0
    for session_key, messages in sessions.items():
        rows.append({"type": "session", "sessionId": session_key, "title": f"Migrated {session_key}"})
        for message in messages:
            role = str(message.get("role", "assistant"))
            text = ""
            content = message.get("content")
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                        texts.append(item["text"])
                text = "\n".join(texts)
            if not text and isinstance(message.get("text"), str):
                text = message["text"]
            rows.append({"type": "message", "sessionId": session_key, "role": role, "text": text})
            message_count += 1
    write_target(target, rows)
    return len(sessions), message_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy session JSON into v1 import format")
    parser.add_argument("--source", required=True, help="Legacy JSON export path")
    parser.add_argument("--target", required=True, help="Target transformed JSON path")
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)
    sessions, messages = migrate(source, target)
    print(f"Migrated {sessions} sessions and {messages} messages into {target}")


if __name__ == "__main__":
    main()
