#!/usr/bin/env python3
"""Serve a *local-only* Quest review UI. Not a public or multi-user service.

Needs clean exact pinned ClassicUA + Spoken checkouts. Source dialogue stays in
RAM and same-origin localhost responses; never in generated JSON/CSV/log files.
Only reject/defer writes are implemented, not identity/content approvals.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.classicua.source import audit_checkout
from adapters.classicua.evidence import from_audit
from adapters.mapping import load_reviews
from adapters.review_ui import LocalReviewState, guarded_decisions_path
from adapters.spoken import PublicSource, build_index
from adapters.spoken.text_index import index_verified_originals

STATIC = ROOT / "tools/review_ui/static"
MAX_REQUEST_BYTES = 2048


def build_state(classicua_path, spoken_path, decisions_path, reviews_path=None):
    """Load exact audited checkouts with no network traffic."""
    lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "tests/stage3_sources.json").read_text(encoding="utf-8"))
    if manifest["revision"] != lock["spoken"]["revision"]:
        raise ValueError("pinned_spoken_manifest_mismatch")
    reader = PublicSource(spoken_path, manifest)
    inventory = build_index(reader)
    original_index = index_verified_originals(reader, inventory)
    dataset, audit = audit_checkout(classicua_path, lock["classicua"]["files"])
    source = from_audit(dataset, audit)
    if source.revision != lock["classicua"]["revision"]:
        raise ValueError("pinned_classicua_revision_mismatch")
    reviews = (
        load_reviews(json.loads(Path(reviews_path).read_text(encoding="utf-8")),
                     source_inventories={source.revision: source})
        if reviews_path else ()
    )
    return LocalReviewState(dataset, source, inventory, original_index,
                            decisions_path, ROOT / "build", tuple(reviews))


def create_handler(state, token, port):
    """Return request handler with strict host/origin and anti-CSRF policy."""
    allowed_host = f"127.0.0.1:{port}"
    allowed_origin = f"http://{allowed_host}"
    files = {
        "/": (STATIC / "index.html", "text/html; charset=utf-8"),
        "/app.js": (STATIC / "app.js", "text/javascript; charset=utf-8"),
        "/styles.css": (STATIC / "styles.css", "text/css; charset=utf-8"),
    }

    class LocalHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # URL params or error bodies may leak review context; no access logs.
            pass

        def _reply(self, status, content, mime="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; img-src 'none'; object-src 'none'; "
                             "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(content)

        def _json(self, status, obj):
            self._reply(status, json.dumps(obj, ensure_ascii=False, sort_keys=True
                                           ).encode("utf-8"))

        def _trusted_host(self):
            return self.headers.get("Host") == allowed_host

        def do_GET(self):
            if not self._trusted_host():
                self._json(403, {"error": "local_host_required"})
                return
            parts = urlsplit(self.path)
            if parts.path in files and not parts.query:
                path, mime = files[parts.path]
                self._reply(200, path.read_bytes(), mime)
                return
            if parts.path == "/api/bootstrap" and not parts.query:
                self._json(200, {"csrf_token": token, "factions": ["horde", "alliance"],
                                 "approved_identity_by_this_ui": False,
                                 "text_policy": "local_ephemeral_only"})
                return
            if parts.path != "/api/queue":
                self._json(404, {"error": "not_found"})
                return
            try:
                params = parse_qs(parts.query, keep_blank_values=True)
                if (set(params) - {"faction", "offset", "limit"}
                        or any(len(values) != 1 for values in params.values())):
                    raise ValueError("invalid_query")
                faction = params.get("faction", ["horde"])[0]
                offset_value = params.get("offset", ["0"])[0]
                limit_value = params.get("limit", ["12"])[0]
                if not (offset_value.isascii() and offset_value.isdecimal()
                        and limit_value.isascii() and limit_value.isdecimal()):
                    raise ValueError("invalid_query")
                offset, limit = int(offset_value), int(limit_value)
                if offset > 100000:
                    raise ValueError("invalid_query")
                report = state.page(faction=faction, offset=offset, limit=limit)
                self._json(200, report)
            except (ValueError, TypeError):
                self._json(400, {"error": "invalid_review_queue_request"})

        def do_POST(self):
            if not self._trusted_host() or self.headers.get("Origin") != allowed_origin:
                self._json(403, {"error": "local_origin_required"})
                return
            if urlsplit(self.path).path != "/api/decisions" or "?" in self.path:
                self._json(404, {"error": "not_found"})
                return
            if (not hmac.compare_digest(
                    self.headers.get("X-Review-Token", ""), token)
                    or self.headers.get("Content-Type", "").split(";")[0].strip()
                    != "application/json"):
                self._json(403, {"error": "review_token_or_content_type_required"})
                return
            declared = self.headers.get("Content-Length", "")
            if not declared.isascii() or not declared.isdecimal():
                self._json(400, {"error": "invalid_content_length"})
                return
            length = int(declared)
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._json(413, {"error": "review_request_too_large"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                if type(payload) is not dict or set(payload) != {
                        "source_id", "target_id", "decision", "reason", "reviewer"}:
                    raise ValueError("invalid_decision_request")
                result = state.decide(**payload)
                self._json(200, result)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                self._json(400, {"error": "invalid_or_duplicate_review_decision"})

    return LocalHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    parser.add_argument("--decisions", type=Path,
                        default=ROOT / "build/stage4b-decisions.json")
    parser.add_argument("--reviews", type=Path, help="Optional existing Stage 3 reviews")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    try:
        decisions = guarded_decisions_path(args.decisions, ROOT / "build")
        if (any(decisions.is_relative_to(path.resolve())
                for path in (args.classicua, args.spoken))
                or args.reviews is not None and decisions == args.reviews.resolve()):
            raise ValueError("decisions_path_conflicts_with_input")
        state = build_state(args.classicua, args.spoken, decisions, args.reviews)
        # Not 0.0.0.0 or a hostname resolving to all interfaces.
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            create_handler(state, secrets.token_urlsafe(32), args.port))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        print("review_ui_pinned_sources_or_local_bind_failed", file=sys.stderr)
        return 1
    print(f"Quest review UI: http://127.0.0.1:{args.port}/", flush=True)
    print("Local-only. Reject/Defer writes audited metadata; no approval button.", flush=True)
    try:
        with server:
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
