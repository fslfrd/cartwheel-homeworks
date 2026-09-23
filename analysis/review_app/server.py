"""Backend for the Homework 4 review interface.

A standard-library HTTP server, like the reference interface under
``analysis/server.py``, keeping the same file-backed API so the watcher and
the supplied helpers work unchanged. Three things differ, each for a reason
recorded in ``analysis/report/interface_comparison.md``:

* **Sessions are the unit.** Cartwheel writes one trace per user turn, so the
  store is keyed by ``cartwheel.session_id`` and a whole conversation is one
  record.
* **The sample manifest is the sample.** ``state/sample_manifest.json`` is
  both the committed deliverable and what ``GET /api/samples`` serves, so the
  batch composition can never drift from what was reviewed. Trace content is
  served separately by ``GET /api/session``, which keeps the committed file
  small and the sidebar instant.
* **Labels fan out.** A judgment is recorded once against a session and
  written to Langfuse as a score on *every* member trace, so no turn of a
  multi-turn conversation appears unscored.

Run it:

    uv run python -m analysis.review_app.server
    uv run python -m analysis.review_app.server --port 8021 --source langfuse
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from analysis.review_app import loader

HERE = Path(__file__).resolve().parent
STATE_DIR = HERE.parent / "state"
UI_DIR = HERE / "ui"
LABELS_DIR = STATE_DIR / "labels"

API_FILES: dict[str, Path] = {
    "/api/samples": STATE_DIR / "sample_manifest.json",
    "/api/annotations": STATE_DIR / "annotations.json",
    "/api/patterns": STATE_DIR / "patterns.json",
    "/api/suggestions": STATE_DIR / "suggestions.json",
}

API_DEFAULTS: dict[str, Any] = {
    "/api/samples": {"sessions": [], "batches": []},
    "/api/annotations": {"annotations": []},
    "/api/patterns": {"modes": []},
    "/api/suggestions": [],
}

# session_id -> full record, populated at startup.
STORE: dict[str, dict[str, Any]] = {}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _annotation_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = data.get("annotations", [])
    return [a for a in data if isinstance(a, dict)] if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def _label_path(mode: str) -> Path:
    safe = "".join(c for c in mode if c.isalnum() or c in "_-")
    return LABELS_DIR / f"{safe}.jsonl"


def _write_label(record: dict[str, Any]) -> dict[str, Any]:
    """Persist one session/mode judgment locally, then mirror it to Langfuse.

    The local file is keyed by session so the review history stays readable.
    The Langfuse score is written to every member trace, because a score
    attaches to a trace identifier and a reviewer opening turn three of a
    conversation should see the same judgment as one opening turn one.
    """
    mode = str(record["mode"])
    session_id = str(record["session_id"])
    label = int(record["label"])

    path = _label_path(mode)
    rows = [
        row
        for row in _read_jsonl(path)
        if row.get("session_id") != session_id  # last judgment wins
    ]
    rows.append(
        {
            "session_id": session_id,
            "mode": mode,
            "label": label,
            "note": record.get("note") or "",
            "trace_ids": record.get("trace_ids") or [],
            "source": record.get("source") or "human",
            "ts": record.get("ts"),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    written = 0
    error = None
    try:
        from analysis.helpers import langfuse_io

        if langfuse_io.is_configured():
            client = langfuse_io._client()
            for trace_id in record.get("trace_ids") or []:
                langfuse_io.write_label_score(
                    trace_id=str(trace_id),
                    mode=mode,
                    label=label,
                    comment=record.get("note"),
                    client=client,
                )
                written += 1
    except Exception as exc:  # pragma: no cover - network-only path
        error = str(exc)

    return {"ok": True, "langfuse_scores_written": written, "langfuse_error": error}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _all_labels() -> dict[str, dict[str, int]]:
    """Return ``{mode: {session_id: label}}`` across every label file."""
    out: dict[str, dict[str, int]] = {}
    if not LABELS_DIR.exists():
        return out
    for path in sorted(LABELS_DIR.glob("*.jsonl")):
        mode = path.stem
        out[mode] = {
            row["session_id"]: int(row["label"])
            for row in _read_jsonl(path)
            if row.get("session_id") is not None
        }
    return out


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


def _progress() -> dict[str, Any]:
    """Coverage of the review set: what is read, and what is still unjudged.

    Part A asks the interface to show reviewed traces *and* incomplete
    judgments. Those are different questions: a session can be open-coded but
    carry no structured label, or carry three of five labels once the
    taxonomy grows.
    """
    manifest = _read_json(API_FILES["/api/samples"], API_DEFAULTS["/api/samples"])
    sessions = manifest.get("sessions", [])
    if not sessions:
        # Before Part B draws the batches, report against everything loaded so
        # the interface is coherent rather than showing 0 of 0.
        sessions = [{"session_id": sid, "batch": "unassigned"} for sid in STORE]
    ids = [s["session_id"] for s in sessions]

    annotations = _annotation_list(
        _read_json(API_FILES["/api/annotations"], API_DEFAULTS["/api/annotations"])
    )
    noted: dict[str, int] = {}
    clean: set[str] = set()
    flagged: set[str] = set()
    for ann in annotations:
        sid = ann.get("session_id")
        if not sid:
            continue
        if ann.get("kind") == "no_failure":
            clean.add(sid)
        elif ann.get("kind") == "flag":
            flagged.add(sid)
        else:
            noted[sid] = noted.get(sid, 0) + 1

    patterns = _read_json(API_FILES["/api/patterns"], API_DEFAULTS["/api/patterns"])
    modes = [m["name"] for m in patterns.get("modes", []) if m.get("name")]
    labels = _all_labels()

    per_batch: dict[str, dict[str, int]] = {}
    for session in sessions:
        batch = session.get("batch") or "unassigned"
        row = per_batch.setdefault(batch, {"total": 0, "reviewed": 0})
        row["total"] += 1
        sid = session["session_id"]
        if sid in noted or sid in clean:
            row["reviewed"] += 1

    incomplete = []
    if modes:
        for sid in ids:
            missing = [m for m in modes if sid not in labels.get(m, {})]
            if missing:
                incomplete.append({"session_id": sid, "missing": missing})

    return {
        "total": len(ids),
        "reviewed": len([s for s in ids if s in noted or s in clean]),
        "annotated": len([s for s in ids if s in noted]),
        "no_failure": len([s for s in ids if s in clean]),
        "flagged": sorted(flagged),
        "annotation_count": len([a for a in annotations if a.get("note")]),
        "batches": per_batch,
        "modes": modes,
        # Only our own modes: analysis/state/labels also holds the instructor's
        # supplied demo file, which is not part of this taxonomy.
        "label_counts": {
            mode: {
                "fail": sum(1 for v in rows.values() if v == 1),
                "pass": sum(1 for v in rows.values() if v == 0),
            }
            for mode, rows in labels.items()
            if mode in modes
        },
        "incomplete": incomplete[:200],
        "incomplete_total": len(incomplete),
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class ReviewHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"error": f"not found: {path.name}"}, status=404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return None

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({}, status=204)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_file(UI_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path == "/api/session":
            session_id = (query.get("id") or [""])[0]
            record = STORE.get(session_id)
            if not record:
                self._send_json({"error": f"unknown session: {session_id}"}, status=404)
                return
            self._send_json(record)
            return

        if path == "/api/store":
            # Lightweight index of everything loaded, for sampling and search.
            self._send_json(
                [
                    {
                        k: v
                        for k, v in record.items()
                        if k not in ("trace", "expected", "features")
                    }
                    for record in STORE.values()
                ]
            )
            return

        if path == "/api/progress":
            self._send_json(_progress())
            return

        if path == "/api/labels":
            self._send_json(_all_labels())
            return

        if path in API_FILES:
            self._send_json(_read_json(API_FILES[path], API_DEFAULTS[path]))
            return

        self._send_json({"error": f"unknown path: {path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        data = self._body()
        if data is None:
            self._send_json({"error": "expected a JSON body"}, status=400)
            return

        if path == "/api/labels":
            records = data if isinstance(data, list) else [data]
            written = 0
            errors = []
            for record in records:
                try:
                    result = _write_label(record)
                    written += result["langfuse_scores_written"]
                    if result["langfuse_error"]:
                        errors.append(result["langfuse_error"])
                except Exception as exc:
                    errors.append(str(exc))
            self._send_json(
                {
                    "ok": not errors,
                    "count": len(records),
                    "langfuse_scores_written": written,
                    "errors": errors[:3],
                }
            )
            return

        if path not in API_FILES:
            self._send_json({"error": f"cannot POST to {path}"}, status=404)
            return

        _write_json(API_FILES[path], data)
        count = len(data) if isinstance(data, list) else len(data or {})
        self._send_json({"ok": True, "count": count})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--source",
        default="export",
        choices=("export", "langfuse"),
        help="where to read traces from (default: the committed export)",
    )
    args = parser.parse_args()

    records = loader.load(args.source)
    STORE.clear()
    STORE.update({r["session_id"]: r for r in records})

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    print(f"loaded {len(STORE)} sessions from {args.source}")
    print(f"review interface on http://{args.host}:{args.port}/")
    print(f"state in {STATE_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
