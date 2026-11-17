#!/usr/bin/env python3
"""Serve local-only Spoken_Quests translation import/review. Not a game AddOn.

Needs clean exact pinned ClassicUA + Spoken checkouts. Reviewed translations
persist only in private ignored build storage. No pack activation or publication.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import re
from pathlib import Path
import secrets
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.classicua.source import audit_checkout
from adapters.classicua.evidence import from_audit
from adapters.mapping import load_reviews
from adapters.local_review_store import strict_json
from adapters.import_summary import format_import_table
from adapters.translation_sources import load_source_policy
from adapters.review_ui import LocalReviewState, guarded_decisions_path
from adapters.spoken import PublicSource, build_index
from adapters.spoken.text_index import index_verified_originals

STATIC = ROOT / "tools/review_ui/static"
MAX_REQUEST_BYTES = 262144
LOGGER = logging.getLogger("spoken.review_ui")
SAFE_REASON = re.compile(r"[a-z][a-z0-9_]{1,79}\Z")


def _reason(exc):
    """Never log request text, reviewer IDs, or an exception's arbitrary payload."""
    value = str(exc)
    return value if SAFE_REASON.fullmatch(value) else type(exc).__name__




def build_state(classicua_path, spoken_path, decisions_path, reviews_path=None,
                local_reviews_path=None, translations_path=None, policy_path=None):
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
    state = LocalReviewState(dataset, source, inventory, original_index,
                            decisions_path, ROOT / "build", tuple(reviews),
                            local_reviews_path, translations_path,
                            load_source_policy(policy_path or ROOT / "config/translation_sources.json"),
                            reviews_path)
    # HTTP writes must not trust a snapshot after someone edits an input
    # checkout/proof. Re-audit the exact pins without changing any local files.
    def revalidate():
        fresh = build_state(classicua_path, spoken_path, decisions_path, reviews_path,
                            local_reviews_path, translations_path, policy_path)
        if fresh.policy != state.policy:
            raise ValueError("source_policy_changed_restart_required")
        fresh.translation_observations()
    state.revalidate_inputs = revalidate
    return state


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
        def _event(self, event, outcome, reason=None):
            # Event and outcome are code constants, never request data.
            if reason is None:
                LOGGER.info("%s %s", event, outcome)
            else:
                LOGGER.warning("%s %s reason=%s", event, outcome, reason)


        def log_message(self, format, *args):
            # URL params or error bodies may leak review context; no access logs.
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def _reply(self, status, content, mime="application/json; charset=utf-8"):
            self.close_connection = True
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
            return self.headers.get_all("Host") == [allowed_host]

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
                                 "text_policy": "private_ignored_local_storage",
                                 "mapping_proof_required": True})
                return
            if parts.path == "/api/translations" and not parts.query:
                try:
                    self._json(200, state.translation_page())
                except (ValueError, TypeError, KeyError) as exc:
                    self._event("translation.list", "failed", _reason(exc))
                    self._json(400, {"error": "translation_evidence_revalidation_failed"})
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
            route = urlsplit(self.path).path
            routes = {"/api/decisions", "/api/mapping/approve", "/api/translations/refresh",
                      "/api/translations/edit", "/api/translations/decide", "/api/translations/import",
                      "/api/translations/auto_import_one_to_one"}
            if route not in routes or "?" in self.path:
                self._json(404, {"error": "not_found"})
                return
            supplied_token = self.headers.get("X-Review-Token", "")
            if (not supplied_token.isascii() or not hmac.compare_digest(supplied_token, token)
                    or len(self.headers.get_all("Content-Type", [])) != 1
                    or self.headers.get("Content-Type", "").split(";")[0].strip()
                    != "application/json"):
                self._json(403, {"error": "review_token_or_content_type_required"})
                return
            if (self.headers.get("Transfer-Encoding") is not None
                    or len(self.headers.get_all("Content-Length", [])) != 1
                    or len(self.headers.get_all("Origin", [])) != 1
                    or len(self.headers.get_all("X-Review-Token", [])) != 1):
                self._json(400, {"error": "ambiguous_request_headers"})
                return
            declared = self.headers.get("Content-Length", "")
            if not declared.isascii() or not declared.isdecimal():
                self._json(400, {"error": "invalid_content_length"})
                return
            length = int(declared)
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._json(413, {"error": "review_request_too_large"})
                return
            event = {"/api/decisions": "mapping.decision",
                     "/api/mapping/approve": "mapping.approve",
                     "/api/translations/refresh": "translation.refresh",
                     "/api/translations/edit": "translation.edit",
                     "/api/translations/decide": "translation.decision",
                     "/api/translations/import": "translation.import",
                     "/api/translations/auto_import_one_to_one": "translation.auto_import_one_to_one"}[route]
            self._event(event, "requested")
            try:
                payload = strict_json(self.rfile.read(length))
                if type(payload) is not dict:
                    raise ValueError("invalid_review_request")
                if route == "/api/decisions":
                    if set(payload) != {"source_id", "target_id", "decision", "reason", "reviewer"}:
                        raise ValueError("invalid_decision_request")
                    result = state.decide(**payload)
                elif route == "/api/mapping/approve":
                    result = state.approve_mapping(payload)
                else:
                    result = state.translation_action(route.rsplit("/", 1)[1], payload)
                self._event(event, "succeeded")
                self._json(200, result)
            except (ValueError, TypeError, KeyError, UnicodeError, OSError) as exc:
                reason = _reason(exc)
                self._event(event, "failed", reason)
                self._json(400, {"error": "invalid_or_duplicate_review_decision",
                                 "reason": reason})

    return LocalHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classicua", type=Path, required=True)
    parser.add_argument("--spoken", type=Path, required=True)
    parser.add_argument("--decisions", type=Path,
                        default=ROOT / "build/stage4b-decisions.json")
    parser.add_argument("--reviews", type=Path, help="Optional existing Stage 3 reviews")
    parser.add_argument("--local-reviews", type=Path, default=ROOT / "build/stage3-ui-reviews.json")
    parser.add_argument("--translations", type=Path, default=ROOT / "build/translation-reviews.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/translation_sources.json")
    parser.add_argument("--auto-import-one-to-one", action="store_true",
                        help="Import Quest (accept/progress/complete) ClassicUA 1:1 candidates into inert private store, report all Spoken records; no in-game AddOn is generated")
    parser.add_argument("--import-approved", action="store_true",
                        help="Revalidate and explicitly import an inert local snapshot, then exit")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [review-ui] %(message)s", stream=sys.stderr)
    LOGGER.info("startup requested; local-only")
    if args.auto_import_one_to_one and args.import_approved:
        parser.error("choose only one import mode")
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    try:
        outputs = [guarded_decisions_path(p, ROOT / "build") for p in
                   (args.decisions, args.local_reviews, args.translations)]
        inputs = [ROOT / "sources.lock.json", args.policy]
        if args.reviews is not None:
            inputs.append(args.reviews)
        if (len(set(outputs)) != len(outputs)
                or any(out.is_relative_to(path.resolve()) for out in outputs
                       for path in (args.classicua, args.spoken))
                or any(out == path.resolve() for out in outputs for path in inputs)):
            raise ValueError("review_storage_conflicts_with_input")
        state = build_state(args.classicua, args.spoken, outputs[0], args.reviews,
                            outputs[1], outputs[2], args.policy)
        if args.auto_import_one_to_one:
            LOGGER.info("translation.auto_import_one_to_one requested (CLI)")
            result = state.translation_action(
                "auto_import_one_to_one", {"source": "classicua"})
            LOGGER.info("translation.auto_import_one_to_one succeeded imported=%d auto_approved=%d",
                        result["imported"], result["auto_approved"])
            print(format_import_table(result["report"]))
            return 0
        if args.import_approved:
            LOGGER.info("translation.import requested (CLI)")
            result = state.translation_action("import", {})
            LOGGER.info("translation.import succeeded (CLI) imported=%d changed=%s",
                        result["imported"], result["changed"])
            print(format_import_table(result["report"]))
            print(json.dumps(result, sort_keys=True))
            return 0
        # Not 0.0.0.0 or a hostname resolving to all interfaces.
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            create_handler(state, secrets.token_urlsafe(32), args.port))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        LOGGER.error("startup failed reason=%s", _reason(exc))
        print("review_ui_pinned_sources_or_local_bind_failed", file=sys.stderr)
        return 1
    LOGGER.info("startup succeeded; listening on localhost port %d", args.port)
    print(f"Spoken_Quests offline translation review/import UI: http://127.0.0.1:{args.port}/", flush=True)
    print("Offline-only (not a WoW AddOn): Quest content only; 1:1 machine imports are provisional. No game installation.", flush=True)
    try:
        with server:
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
