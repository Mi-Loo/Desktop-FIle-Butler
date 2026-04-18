#!/usr/bin/env python3
"""
Desktop File Butler
===================
Watches your Downloads/Desktop folder and uses a local LLM (Ollama) to:
  - Classify files (PDF, screenshot, installer, document, etc.)
  - Suggest renames
  - Summarize PDFs
  - Flag duplicates
  - Suggest what to delete or archive

Requires:
    pip install watchdog flask flask-cors ollama PyPDF2 pillow requests

And Ollama running locally:
    ollama serve
    ollama pull llama3  (or any model you prefer)

Usage:
    python butler.py
Then open dashboard.html in your browser.
"""

import os
import sys
import json
import time
import hashlib
import threading
import mimetypes
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Third-party ──────────────────────────────────────────────────────────────
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    sys.exit("Missing: pip install watchdog")

try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
except ImportError:
    sys.exit("Missing: pip install flask flask-cors")

try:
    import ollama
except ImportError:
    sys.exit("Missing: pip install ollama")

# ── Config ────────────────────────────────────────────────────────────────────
WATCH_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Desktop",
]
OLLAMA_MODEL = "llama3"          # change to your preferred model
FLASK_PORT   = 5765
MAX_PDF_CHARS = 3000             # chars sent to LLM for summarisation

# Folder buckets (created inside watched dir)
BUCKET_MAP = {
    "pdf":         "📄 Documents/PDFs",
    "screenshot":  "🖼️ Screenshots",
    "image":       "🖼️ Images",
    "installer":   "⚙️ Installers",
    "archive":     "📦 Archives",
    "video":       "🎬 Videos",
    "audio":       "🎵 Audio",
    "code":        "💻 Code",
    "spreadsheet": "📊 Spreadsheets",
    "other":       "🗂️ Other",
}

EXT_MAP = {
    ".pdf":  "pdf",
    ".png":  "screenshot", ".jpg": "image", ".jpeg": "image",
    ".gif":  "image",      ".webp": "image", ".heic": "image",
    ".dmg":  "installer",  ".pkg": "installer", ".exe": "installer",
    ".msi":  "installer",  ".deb": "installer", ".rpm": "installer",
    ".zip":  "archive",    ".tar": "archive", ".gz": "archive",
    ".rar":  "archive",    ".7z":  "archive",
    ".mp4":  "video",      ".mov": "video",  ".mkv": "video",
    ".avi":  "video",      ".m4v": "video",
    ".mp3":  "audio",      ".wav": "audio",  ".m4a": "audio",
    ".flac": "audio",
    ".py":   "code",       ".js":  "code",   ".ts":  "code",
    ".sh":   "code",       ".rb":  "code",   ".go":  "code",
    ".xlsx": "spreadsheet",".xls": "spreadsheet", ".csv": "spreadsheet",
}

# ── State (in-memory) ─────────────────────────────────────────────────────────
events      = []          # list of dicts shown in dashboard
file_hashes = {}          # path -> md5  (for duplicate detection)
pending     = {}          # id  -> action dict awaiting user approval
_id_counter = 0
_lock       = threading.Lock()

app = Flask(__name__)
CORS(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def next_id():
    global _id_counter
    _id_counter += 1
    return _id_counter


def ts():
    return datetime.now().strftime("%H:%M:%S")


def md5(path: Path) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def push_event(kind: str, title: str, detail: str, action=None, file_path=None):
    """Add an event to the live feed."""
    eid = next_id()
    ev = {
        "id":        eid,
        "ts":        ts(),
        "kind":      kind,       # info | suggestion | warning | duplicate | summary
        "title":     title,
        "detail":    detail,
        "file":      str(file_path) if file_path else None,
        "action":    action,     # dict with type/dest/rename or None
        "status":    "pending" if action else "done",
    }
    with _lock:
        events.append(ev)
        if action:
            pending[eid] = ev
    return eid


def ask_llm(prompt: str) -> str:
    """Call Ollama synchronously and return the text."""
    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp["message"]["content"].strip()
    except Exception as e:
        return f"[LLM error: {e}]"


def classify_file(path: Path) -> str:
    ext = path.suffix.lower()
    return EXT_MAP.get(ext, "other")


def extract_pdf_text(path: Path) -> str:
    try:
        import PyPDF2
        text = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages[:6]:   # first 6 pages
                text.append(page.extract_text() or "")
        return "\n".join(text)[:MAX_PDF_CHARS]
    except Exception as e:
        return f"[Could not extract text: {e}]"


def is_screenshot(path: Path) -> bool:
    name = path.name.lower()
    return (
        "screenshot" in name or
        "screen shot" in name or
        name.startswith("img_") or
        name.startswith("capture")
    )


# ── Core agent logic ──────────────────────────────────────────────────────────

def process_file(path: Path):
    """Observe → Decide → propose Action for a single file."""

    if not path.exists() or path.stat().st_size == 0:
        return
    if path.name.startswith("."):
        return  # hidden / temp

    kind = classify_file(path)
    parent = path.parent

    # ── Duplicate detection ──────────────────────────────────────────────────
    digest = md5(path)
    if digest:
        for existing_path, existing_hash in list(file_hashes.items()):
            if existing_hash == digest and existing_path != str(path):
                push_event(
                    "duplicate",
                    f"Duplicate detected: {path.name}",
                    f"Identical to {Path(existing_path).name}",
                    action={"type": "delete", "target": str(path)},
                    file_path=path,
                )
        file_hashes[str(path)] = digest

    # ── PDF workflow ─────────────────────────────────────────────────────────
    if kind == "pdf":
        text = extract_pdf_text(path)
        if text.strip():
            summary = ask_llm(
                f"Summarise this document in 2-3 sentences and suggest a short, "
                f"descriptive filename (no extension). "
                f"Reply as JSON: {{\"summary\": \"...\", \"suggested_name\": \"...\"}}\n\n{text}"
            )
            try:
                data = json.loads(summary)
                suggested = data.get("suggested_name", path.stem)
                summary_text = data.get("summary", summary)
            except Exception:
                suggested = path.stem
                summary_text = summary

            dest_dir = parent / BUCKET_MAP["pdf"]
            new_name  = f"{suggested}.pdf"

            push_event(
                "summary",
                f"PDF analysed: {path.name}",
                summary_text,
                action={
                    "type":    "move_rename",
                    "target":  str(path),
                    "dest":    str(dest_dir / new_name),
                    "new_name": new_name,
                },
                file_path=path,
            )
        else:
            push_event("info", f"PDF (no text): {path.name}", "Scanned or image PDF.", file_path=path)

    # ── Screenshot workflow ──────────────────────────────────────────────────
    elif kind in ("screenshot", "image") and is_screenshot(path):
        now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        new_name = f"screenshot_{now}{path.suffix}"
        dest_dir = parent / BUCKET_MAP["screenshot"]
        push_event(
            "suggestion",
            f"Screenshot found: {path.name}",
            "Suggest moving to Screenshots folder with a dated name.",
            action={
                "type":    "move_rename",
                "target":  str(path),
                "dest":    str(dest_dir / new_name),
                "new_name": new_name,
            },
            file_path=path,
        )

    # ── Generic file ────────────────────────────────────────────────────────
    else:
        bucket = BUCKET_MAP.get(kind, BUCKET_MAP["other"])
        dest_dir = parent / bucket
        push_event(
            "suggestion",
            f"New {kind} file: {path.name}",
            f"Suggest moving to '{bucket}'.",
            action={
                "type":   "move",
                "target": str(path),
                "dest":   str(dest_dir / path.name),
            },
            file_path=path,
        )

    # ── Old-file flag ────────────────────────────────────────────────────────
    mtime = path.stat().st_mtime
    age_days = (time.time() - mtime) / 86400
    if age_days > 90:
        push_event(
            "warning",
            f"Old file: {path.name}",
            f"Last modified {int(age_days)} days ago — consider archiving.",
            file_path=path,
        )


def execute_action(action: dict):
    """Actually perform a move/rename/delete."""
    atype = action.get("type")
    target = Path(action.get("target", ""))

    if not target.exists():
        return False, "File no longer exists."

    if atype == "delete":
        target.unlink()
        return True, f"Deleted {target.name}"

    elif atype in ("move", "move_rename"):
        dest = Path(action.get("dest", ""))
        dest.parent.mkdir(parents=True, exist_ok=True)
        target.rename(dest)
        return True, f"Moved to {dest}"

    return False, "Unknown action type."


# ── Watchdog handler ──────────────────────────────────────────────────────────

class ButlerHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        # Small delay to let the file finish writing
        threading.Timer(1.5, process_file, args=[path]).start()

    def on_moved(self, event):
        if event.is_directory:
            return
        path = Path(event.dest_path)
        threading.Timer(1.5, process_file, args=[path]).start()


# ── Flask API ─────────────────────────────────────────────────────────────────

@app.route("/api/events")
def api_events():
    since = int(request.args.get("since", 0))
    with _lock:
        filtered = [e for e in events if e["id"] > since]
    return jsonify(filtered)


@app.route("/api/approve/<int:eid>", methods=["POST"])
def api_approve(eid):
    with _lock:
        ev = pending.pop(eid, None)
    if not ev:
        return jsonify({"ok": False, "msg": "Event not found or already resolved."})
    ok, msg = execute_action(ev["action"])
    ev["status"] = "approved" if ok else "error"
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/reject/<int:eid>", methods=["POST"])
def api_reject(eid):
    with _lock:
        ev = pending.pop(eid, None)
    if ev:
        ev["status"] = "rejected"
    return jsonify({"ok": True})


@app.route("/api/clean", methods=["POST"])
def api_clean():
    """Dry-run or real scan of all watched directories."""
    dry_run = request.json.get("dry_run", True)
    pushed = 0
    for watch_dir in WATCH_DIRS:
        if not watch_dir.exists():
            continue
        for f in watch_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                process_file(f)
                pushed += 1
    return jsonify({"ok": True, "scanned": pushed, "dry_run": dry_run})


@app.route("/api/status")
def api_status():
    return jsonify({
        "model":       OLLAMA_MODEL,
        "watch_dirs":  [str(d) for d in WATCH_DIRS],
        "total_events": len(events),
        "pending":     len(pending),
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def start_watchdog():
    observer = Observer()
    handler  = ButlerHandler()
    for d in WATCH_DIRS:
        if d.exists():
            observer.schedule(handler, str(d), recursive=False)
            print(f"👀 Watching: {d}")
        else:
            print(f"⚠️  Directory not found (skipping): {d}")
    observer.start()
    return observer


if __name__ == "__main__":
    print("🤵 Desktop File Butler starting…")
    print(f"   Model  : {OLLAMA_MODEL}")
    print(f"   Port   : {FLASK_PORT}")

    observer = start_watchdog()

    try:
        app.run(port=FLASK_PORT, debug=False)
    finally:
        observer.stop()
        observer.join()
