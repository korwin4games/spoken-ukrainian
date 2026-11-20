#!/usr/bin/env python3
"""Serve local-only Spoken_Quests translation import/review. Not a game AddOn.

Needs clean exact pinned ClassicUA + Spoken checkouts. Reviewed translations
persist only in private ignored build storage. No pack activation or publication.
"""
import argparse
import gzip
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
from tools.manager_timing import timing

STATIC = ROOT / "tools/review_ui/static"
MAX_REQUEST_BYTES = 262144
LOGGER = logging.getLogger("spoken.review_ui")
SAFE_REASON = re.compile(r"[a-z][a-z0-9_]{1,79}\Z")


def _reason(exc):
    """Never log request text, reviewer IDs, or an exception's arbitrary payload."""
    value = str(exc)
    return value if SAFE_REASON.fullmatch(value) else type(exc).__name__




def load_review_inputs(classicua_path, spoken_path, *, keep_lines=False):
    """Load committed, hash-verified source data independently of the local ledger."""
    lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "tests/stage3_sources.json").read_text(encoding="utf-8"))
    if manifest["revision"] != lock["spoken"]["revision"]:
        raise ValueError("pinned_spoken_manifest_mismatch")
    with timing("spoken_index"):
        reader = PublicSource(spoken_path, manifest)
        corpus = json.loads(gzip.decompress(reader.read("pipelines/quests/corpus/corpus.json.gz")))
        inventory = build_index(reader, corpus=corpus)
        original_index = index_verified_originals(reader, inventory, corpus=corpus)
    with timing("classicua_audit"):
        dataset, audit = audit_checkout(classicua_path, lock["classicua"]["files"])
        source = from_audit(dataset, audit)
    if source.revision != lock["classicua"]["revision"]:
        raise ValueError("pinned_classicua_revision_mismatch")
    return (dataset, source, inventory, original_index, corpus["lines"] if keep_lines else None)


def build_state(classicua_path, spoken_path, decisions_path, reviews_path=None,
                local_reviews_path=None, translations_path=None, policy_path=None, *, inputs=None):
    """Read the current local ledger against verified source data."""
    dataset, source, inventory, original_index, _ = (
        load_review_inputs(classicua_path, spoken_path) if inputs is None else inputs)
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
        if (fresh.source.revision != state.source.revision
                or fresh.inventory.revision != state.inventory.revision):
            raise ValueError("pinned_sources_changed_restart_required")
        if fresh.policy != state.policy:
            raise ValueError("source_policy_changed_restart_required")
        fresh.translation_observations()
    state.revalidate_inputs = revalidate
    return state


def create_handler(token, port, manager=None):
    """Return the localhost Translation Manager request handler."""
    allowed_host = f"127.0.0.1:{port}"
    allowed_origin = f"http://{allowed_host}"
    files = {
        "/": (STATIC / "manager.html", "text/html; charset=utf-8"),
        "/manager.js": (STATIC / "manager.js", "text/javascript; charset=utf-8"),
        "/manager.css": (STATIC / "manager.css", "text/css; charset=utf-8"),
    }
    actions = {"list", "detail", "reimport", "import_ready", "confirm_candidate", "save_translation", "review_mapping",
               "register_candidate", "withdraw_quest_approval", "choose_quest", "save_quest",
               "choose_gossip", "save_gossip", "install"}
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
                self._json(200, {"csrf_token": token})
                return
            if parts.path == "/api/import-stats" and manager is not None:
                try:
                    params = parse_qs(parts.query, strict_parsing=True, max_num_fields=1)
                    if set(params) != {"module"} or len(params["module"]) != 1:
                        raise ValueError("manager_unknown_module")
                    with timing("api_response", action="stats"):
                        self._json(200, manager.action("stats", {"module": params["module"][0]}))
                except (ValueError, OSError, TypeError, KeyError) as exc:
                    self._json(400, {"error": _reason(exc)})
                return
            self._json(404, {"error": "not_found"})

        def do_POST(self):
            if not self._trusted_host() or self.headers.get("Origin") != allowed_origin:
                self._json(403, {"error": "local_origin_required"})
                return
            route = urlsplit(self.path).path
            action = route.removeprefix("/api/manager/")
            if action not in actions or route != "/api/manager/" + action or "?" in self.path:
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
            event = 'manager.' + action
            self._event(event, "requested")
            try:
                payload = strict_json(self.rfile.read(length))
                if type(payload) is not dict:
                    raise ValueError("invalid_review_request")
                if manager is None:
                    raise ValueError("manager_unavailable")
                with timing("api_response", action=action):
                    result = manager.action(action, payload)
                    self._event(event, "succeeded")
                    self._json(200, result)
            except (ValueError, TypeError, KeyError, UnicodeError, OSError) as exc:
                reason = _reason(exc)
                self._event(event, "failed", reason)
                self._json(400, {"error": "invalid_or_duplicate_review_decision",
                                 "reason": reason})

    return LocalHandler


def startup_failure_hint(reason):
    """Actionable, path-safe CLI diagnostics; never expose Git stderr or bodies."""
    if reason in ("public_git_read_failed", "public_checkout_root_required"):
        return (
            "Spoken source path is not a readable Git checkout root. "
            "Replace the example --spoken /absolute/path/to/spoken-wow with "
            "the REAL local repository root (containing .git).\n"
            "Check: git -C /your/real/spoken-wow rev-parse --show-toplevel\n"
            "Check: git -C /your/real/spoken-wow rev-parse HEAD\n"
            "Pinned Spoken HEAD: 3c896874e27ec9e07d51a3578c0b9fa8545c9ac7"
        )
    if reason == "public_revision_mismatch":
        return (
            "Spoken checkout HEAD differs from the pinned version. "
            "Use a separate clean checkout at "
            "3c896874e27ec9e07d51a3578c0b9fa8545c9ac7; "
            "do not overwrite local uncommitted work."
        )
    if reason == "public_checkout_modified":
        return (
            "The pinned Spoken checkout contains modified tracked files. "
            "Prepare a separate clean checkout; do not discard local changes."
        )
    if reason in ("classicua_checkout_path_missing", "spoken_checkout_path_missing"):
        return (
            "The supplied --classicua/--spoken path does not exist. "
            "Paths beginning /absolute/path/to/ are placeholders. "
            "Replace BOTH with actual absolute filesystem paths to Git checkouts."
        )
    if reason == "classicua_checkout_root_missing":
        return ("ClassicUA path must be a real Git repository root (including .git). "
                "Check: git -C /your/real/ClassicUA rev-parse HEAD; "
                "pinned ClassicUA HEAD: 1770d208ad853d23d61105cf510d53804770d916")
    if reason == "spoken_checkout_root_missing":
        return ("Spoken path must be a real Git repository root (including .git). "
                "Check: git -C /your/real/spoken-wow rev-parse HEAD")
    return None


def validate_source_paths(classicua, spoken):
    """Detect sample paths before any opaque Git subprocess error."""
    for label, candidate in (("classicua", classicua), ("spoken", spoken)):
        if not candidate.is_dir():
            raise ValueError(label + "_checkout_path_missing")
        # .git can be a directory or a file in Git worktrees.
        if not (candidate / ".git").exists():
            raise ValueError(label + "_checkout_root_missing")


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
        validate_source_paths(args.classicua, args.spoken)
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
        if args.auto_import_one_to_one or args.import_approved:
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
        from adapters.sqlite_translation_store import DB_ENV, default_db_path
        from tools.translation_manager import ManagerUI
        import os
        db_path = os.environ.get(DB_ENV) or default_db_path()
        manager = ManagerUI(args.classicua, args.spoken, db_path)
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            create_handler(secrets.token_urlsafe(32), args.port, manager))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        reason = _reason(exc)
        LOGGER.error("startup failed reason=%s", reason)
        print("review_ui_startup_error: " + reason, file=sys.stderr)
        hint = startup_failure_hint(reason)
        if hint:
            print("How to fix: " + hint, file=sys.stderr)
        print("review_ui_pinned_sources_or_local_bind_failed", file=sys.stderr)
        return 1
    LOGGER.info("startup succeeded; listening on localhost port %d", args.port)
    print(f"Quest + Gossip Translation Manager: http://127.0.0.1:{args.port}/", flush=True)
    print("Private local builds and review.", flush=True)
    try:
        with server:
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.close()
    return 0


if __name__ == "__main__":
    # Executed CLIs use the persistent SQLite store by default. Test/library
    # direct calls retain their explicit isolated JSON fixture backend.
    import os
    from adapters.sqlite_translation_store import enable_sqlite, DB_ENV
    with enable_sqlite(os.environ.get(DB_ENV)):
        raise SystemExit(main())
