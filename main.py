"""
WhatsApp Cloud API — Friends‑Only Chip Accounting Bot (Iteration 1)
Bilingual (English/Hebrew) commands. Flask + MongoDB (pymongo).

⚙️ ENV VARS required:
- WHATSAPP_TOKEN:      Meta permanent access token
- PHONE_NUMBER_ID:     WhatsApp Business phone number ID
- VERIFY_TOKEN:        Webhook verify token (choose any string)
- MONGO_URL:           MongoDB connection string (Atlas or local)
- BASE_URL:            Public base URL of this service (for building join links)

📝 Notes
- No chip tracking during the game.
- Players can request full cash-out (host confirms + enters amount when applicable).
- Host ends game and inputs final chip counts; bot computes minimal transfers,
  prioritizing cash-to-cash where possible. Host must confirm payouts.

📦 Run locally
  export FLASK_APP=app:app FLASK_ENV=development
  flask run -p 5000
  (or) python app.py

🚇 Webhook
  GET /webhook  -> verification (hub.challenge)
  POST /webhook -> incoming messages

"""
import os
import re
import json
from datetime import datetime
from typing import List, Dict, Tuple

from flask import Flask, request
from pymongo import MongoClient
import requests

# -------------------------- Setup --------------------------
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
ACCESS_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "verify_me")
BASE_URL = os.environ.get("BASE_URL", "https://example.com")

client = MongoClient(MONGO_URL)
db = client["chipbot"]

app = Flask(__name__)

# -------------------------- Utilities --------------------------
HEB_CHARS = re.compile(r"[\u0590-\u05FF]")

def is_hebrew(text: str) -> bool:
    return bool(HEB_CHARS.search(text or ""))

CMD_ALIASES = {
    "newgame": ["/newgame", "/משחקחדש"],
    "join": ["/join", "/הצטרף"],
    "buyin_cash": ["/buyin cash", "/קניה מזומן"],
    "buyin_register": ["/buyin register", "/קניה רישום"],
    "cashout": ["/cashout", "/פדיון"],
    "endgame": ["/endgame", "/סיום"],
    "chips": ["/chips", "/ציפים"],
    "settle": ["/settle", "/חישוב"],
    "status": ["/status", "/סטטוס"],
    "quit": ["/quit", "/יציאה"],
    "help": ["/help", "/עזרה"],
}
ALIAS_LOOKUP = {a: key for key, arr in CMD_ALIASES.items() for a in arr}

def parse_command(text: str) -> Tuple[str, List[str]]:
    if not text:
        return "", []
    text = text.strip()
    for alias in sorted(ALIAS_LOOKUP.keys(), key=len, reverse=True):
        if text.lower().startswith(alias):
            key = ALIAS_LOOKUP[alias]
            rest = text[len(alias):].strip()
            args = rest.split() if rest else []
            return key, args
    return "", []

# WhatsApp API
def wa_send_text(to_phone: str, body: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": body},
    }
    requests.post(url, headers=headers, json=payload, timeout=20)

# -------------------------- DB Helpers --------------------------

def create_game(host_phone: str, title: str = "Friends Game") -> dict:
    g = {
        "host_phone": host_phone,
        "status": "active",
        "title": title,
        "chip_value": 1,
        "created_at": datetime.utcnow(),
    }
    res = db.games.insert_one(g)
    g["_id"] = res.inserted_id
    return g


def join_game(game_id, phone: str, name: str = None) -> dict:
    p = db.players.find_one({"game_id": game_id, "phone": phone})
    if not p:
        p = {
            "game_id": game_id,
            "phone": phone,
            "name": name or phone,
            "joined": True,
            "quit": False,
            "total_buyin": 0,
            "cash_buyin": 0,
            "register_buyin": 0,
            "final_chips": None,
        }
        db.players.insert_one(p)
    return p


def record_transaction(game_id, phone, tx_type: str, amount: int = 0) -> dict:
    tx = {
        "game_id": game_id,
        "phone": phone,
        "type": tx_type,
        "amount": amount,
        "confirmed": False,
        "at": datetime.utcnow(),
    }
    res = db.transactions.insert_one(tx)
    tx["_id"] = res.inserted_id
    return tx

# -------------------------- HTTP Endpoints --------------------------
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "Bad token", 403

@app.route("/webhook", methods=["POST"])
def incoming():
    data = request.get_json(force=True)
    try:
        changes = data["entry"][0]["changes"][0]["value"]
        messages = changes.get("messages", [])
        for m in messages:
            from_phone = m.get("from")
            profile = changes.get("contacts", [{}])[0].get("profile", {})
            name = profile.get("name", from_phone)
            text = m.get("text", {}).get("body", "")
            handle_command(from_phone, name, text)
    except Exception:
        pass
    return "ok", 200

# -------------------------- Command Handlers (partial demo) --------------------------

def handle_command(from_phone: str, name: str, text: str):
    lang_he = is_hebrew(text)
    key, args = parse_command(text)

    def reply(msg_en: str, msg_he: str):
        wa_send_text(from_phone, msg_he if lang_he else msg_en)

    if key == "help" or key == "":
        reply("Commands: /newgame, /join <game_id>, /buyin cash <amt>, /buyin register <amt>",
              "פקודות: /משחקחדש, /הצטרף <מזהה>, /קניה מזומן <סכום>, /קניה רישום <סכום>")

    elif key == "newgame":
        g = create_game(from_phone, title=f"Game by {name}")
        join_link = f"{BASE_URL}/join/{g['_id']}"
        wa_send_text(from_phone, f"Game created. Share join link: {join_link}")
        wa_send_text(from_phone, f"נוצר משחק. קישור הצטרפות: {join_link}")

    elif key == "join":
        if not args:
            reply("Usage: /join <game_id>", "שימוש: /הצטרף <מזהה>")
            return
        gid = args[0]
        p = join_game(gid, from_phone, name)
        reply(f"Joined game {gid}", f"הצטרפת למשחק {gid}")

    elif key in ("buyin_cash", "buyin_register"):
        if not args:
            reply("Usage: /buyin cash <amount>", "שימוש: /קניה מזומן <סכום>")
            return
        amount = int(args[0])
        gid = args[1] if len(args) > 1 else None
        if not gid:
            reply("Provide game id", "יש לציין מזהה משחק")
            return
        join_game(gid, from_phone, name)
        tx = record_transaction(gid, from_phone, key, amount)
        reply("Buy-in recorded (waiting host confirm)", "הקניה נרשמה (ממתין לאישור המארח)")

    else:
        reply("Unknown command. Try /help", "פקודה לא מוכרת. נסה /עזרה")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
