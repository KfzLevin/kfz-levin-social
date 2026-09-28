"""Laeuft in GitHub Actions: veroeffentlicht alle faelligen Posts aus queue/*.json.

Eintrag: {"zeit": "2026-09-29 19:00", "image_url": "...", "caption": "...", "ai": true}
"zeit" ist deutsche Ortszeit. Nach dem Posten wird die Datei nach queue/done/ verschoben.
"""

import glob
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

GRAPH_URL = "https://graph.instagram.com/v21.0"
ACCOUNT_ID = os.environ["INSTAGRAM_ACCOUNT_ID"]
TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
TZ = ZoneInfo("Europe/Berlin")


def post(entry: dict) -> str:
    data = {"image_url": entry["image_url"], "caption": entry["caption"], "access_token": TOKEN}
    if entry.get("ai"):
        data["is_ai_generated"] = "true"
    r = requests.post(f"{GRAPH_URL}/{ACCOUNT_ID}/media", data=data)
    r.raise_for_status()
    cid = r.json()["id"]
    for _ in range(30):
        s = requests.get(f"{GRAPH_URL}/{cid}", params={"fields": "status_code", "access_token": TOKEN})
        s.raise_for_status()
        status = s.json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"Container {cid} fehlgeschlagen")
        time.sleep(2)
    r = requests.post(f"{GRAPH_URL}/{ACCOUNT_ID}/media_publish", data={"creation_id": cid, "access_token": TOKEN})
    r.raise_for_status()
    return r.json()["id"]


def main() -> None:
    now = datetime.now(TZ)
    os.makedirs("queue/done", exist_ok=True)
    failed = False
    for path in sorted(glob.glob("queue/*.json")):
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
        due = datetime.strptime(entry["zeit"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        if due > now:
            print(f"{path}: geplant fuer {entry['zeit']}, noch nicht faellig")
            continue
        try:
            entry["media_id"] = post(entry)
            entry["veroeffentlicht"] = now.strftime("%Y-%m-%d %H:%M")
            print(f"{path}: veroeffentlicht, Media-ID {entry['media_id']}")
        except Exception as e:  # Datei bleibt liegen, naechster Lauf versucht es erneut
            print(f"{path}: FEHLER {e}", file=sys.stderr)
            failed = True
            continue
        with open(os.path.join("queue/done", os.path.basename(path)), "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        os.remove(path)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
