import json
import os
import uuid
from datetime import datetime

_DATA_DIR       = os.path.join(os.path.expanduser("~"), ".torrentbot")
_HISTORY_FILE   = os.path.join(_DATA_DIR, "history.json")
_WISHLIST_FILE  = os.path.join(_DATA_DIR, "wishlist.json")
_DL_HIST_FILE   = os.path.join(_DATA_DIR, "dl_history.json")


def _ensure():
    os.makedirs(_DATA_DIR, exist_ok=True)


# ── Search history ─────────────────────────────────────────────────────────────

def load_history():
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(history):
    _ensure()
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def add_to_history(query):
    query = query.strip()
    if not query:
        return
    history = load_history()
    history = [h for h in history if h.lower() != query.lower()]
    history.insert(0, query)
    save_history(history[:50])


# ── Wishlist ───────────────────────────────────────────────────────────────────

def load_wishlist():
    try:
        with open(_WISHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_wishlist(wishlist):
    _ensure()
    with open(_WISHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wishlist, f, ensure_ascii=False, indent=2)


def add_to_wishlist(title):
    title = title.strip()
    if not title:
        return None
    wishlist = load_wishlist()
    for item in wishlist:
        if item["title"].lower() == title.lower():
            return None
    item = {
        "id":          str(uuid.uuid4()),
        "title":       title,
        "added":       datetime.now().strftime("%Y-%m-%d"),
        "status":      "pending",
        "found_link":  None,
        "found_title": None,
        "found_hash":  None,
    }
    wishlist.append(item)
    save_wishlist(wishlist)
    return item


def remove_from_wishlist(item_id):
    wishlist = load_wishlist()
    save_wishlist([w for w in wishlist if w["id"] != item_id])


def update_wishlist_item(item_id, **kwargs):
    wishlist = load_wishlist()
    for item in wishlist:
        if item["id"] == item_id:
            item.update(kwargs)
            break
    save_wishlist(wishlist)


# ── Download history ───────────────────────────────────────────────────────────

def load_dl_history():
    try:
        with open(_DL_HIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_to_dl_history(title, found_title="", quality=""):
    _ensure()
    history = load_dl_history()
    history.insert(0, {
        "title":       title,
        "found_title": found_title,
        "quality":     quality,
        "date":        datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    with open(_DL_HIST_FILE, "w", encoding="utf-8") as f:
        json.dump(history[:200], f, ensure_ascii=False, indent=2)


def clear_dl_history():
    _ensure()
    with open(_DL_HIST_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
