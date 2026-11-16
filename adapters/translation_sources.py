"""Offline, configurable Ukrainian translation-source discovery (NOT pack generation).

The ordered source list is an allow-list. For an indexed Spoken batch, each
subsequent source sees only objects for which earlier sources found no actual
translation candidate. Candidates are never automatically approved for release.
"""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Mapping, Protocol

SOURCES = frozenset(("classicua", "another", "own_translator", "original_english"))
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
CLIENT_LOCALE = re.compile(r"[a-z]{2}[A-Z]{2}\Z")


@dataclass(frozen=True)
class SourcePolicy:
    sources: tuple[str, ...]

    def __post_init__(self):
        if type(self.sources) is not tuple or any(type(x) is not str or x not in SOURCES for x in self.sources):
            raise ValueError("unknown_translation_source")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("duplicate_translation_source")

    @classmethod
    def from_mapping(cls, value):
        if type(value) is dict and value == {}:
            return cls(())
        if type(value) is not dict or set(value) != {"schema_version", "sources"}:
            raise ValueError("invalid_translation_source_config_schema")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("unsupported_translation_source_config_version")
        if type(value["sources"]) is not list:
            raise ValueError("translation_sources_must_be_array")
        return cls(tuple(value["sources"]))


def load_source_policy(path):
    try:
        return SourcePolicy.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot_load_translation_source_config") from exc


class CandidateState(str, Enum):
    NEEDS_REVIEW = "needs_review"
    MOCK_ONLY = "mock_only"


@dataclass(frozen=True)
class TranslationRequest:
    source_identity: str
    original_english: str
    canonical_spoken_id: str | None = None
    client_locale: str | None = None

    def __post_init__(self):
        # A canonical Spoken target can be indexed before anyone proves which
        # ClassicUA source unit it corresponds to. None is *not* a source match.
        if ((self.source_identity is not None
             and (type(self.source_identity) is not str or not self.source_identity))
                or type(self.original_english) is not str or not self.original_english):
            raise ValueError("source_identity_and_english_text_required")
        if self.client_locale is not None and (
                type(self.client_locale) is not str or not CLIENT_LOCALE.fullmatch(self.client_locale)):
            raise ValueError("invalid_client_locale")
        if self.canonical_spoken_id is not None and (
                type(self.canonical_spoken_id) is not str or not self.canonical_spoken_id):
            raise ValueError("invalid_canonical_spoken_id")

    @property
    def original_sha256(self):
        return sha256(self.original_english.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EffectiveClassicUAField:
    """Already-audited effective Stage 2A field; no Lua or repository is read here."""
    text: str | None
    source_file: str
    source_revision: str
    source_file_sha256: str
    ai_marked: bool = False

    def __post_init__(self):
        if not self.source_file or not self.source_revision or not HEX64.fullmatch(self.source_file_sha256):
            raise ValueError("pinned_classicua_field_provenance_required")
        if self.text is not None and type(self.text) is not str:
            raise ValueError("effective_field_text_must_be_string_or_none")


@dataclass(frozen=True)
class TranslationCandidate:
    """In-memory only; candidates cannot bypass rights/grammar/identity review."""
    text_uk: str
    provider: str
    source_ref: str
    source_revision: str
    source_file_sha256: str
    field_sha256: str
    rights_status: str
    state: CandidateState
    ai_marked: bool = False

    def __post_init__(self):
        if (type(self.text_uk) is not str or not self.text_uk
                or type(self.provider) is not str or not self.provider
                or type(self.source_ref) is not str or not self.source_ref
                or type(self.source_revision) is not str or not self.source_revision):
            raise ValueError("translation_candidate_requires_provenance")
        if (type(self.source_file_sha256) is not str or not HEX64.fullmatch(self.source_file_sha256)
                or type(self.field_sha256) is not str or not HEX64.fullmatch(self.field_sha256)):
            raise ValueError("translation_candidate_requires_revision_and_sha")
        if sha256(self.text_uk.encode("utf-8")).hexdigest() != self.field_sha256:
            raise ValueError("translation_candidate_field_digest_mismatch")
        if self.rights_status not in ("reviewed", "pending") or not isinstance(self.state, CandidateState):
            raise ValueError("invalid_candidate_review_state")

    @property
    def publishable(self):
        return False

    def report_metadata(self):
        return dict(provider=self.provider, revision=self.source_revision,
                    source_file_sha256=self.source_file_sha256, field_sha256=self.field_sha256,
                    rights_status=self.rights_status, state=self.state.value,
                    ai_marked=self.ai_marked, publishable=False)


class TranslationProvider(Protocol):
    def lookup(self, request: TranslationRequest) -> TranslationCandidate | None: ...


class ClassicUAProvider:
    def __init__(self, effective_fields: Mapping[str, EffectiveClassicUAField]):
        self.effective_fields = effective_fields

    def lookup(self, request):
        # An indexed Spoken target alone is not an independently reviewed
        # ClassicUA source-to-target join. Never look up an unbound identity,
        # even if a malformed provider registry happens to contain a None key.
        if request.source_identity is None:
            return None
        field = self.effective_fields.get(request.source_identity)
        if field is None or not field.text:
            return None
        return TranslationCandidate(field.text, "classicua", field.source_file,
                                    field.source_revision, field.source_file_sha256,
                                    sha256(field.text.encode("utf-8")).hexdigest(),
                                    "reviewed", CandidateState.NEEDS_REVIEW, field.ai_marked)


class AlternativeSourceStub:
    def lookup(self, request):
        return None


class OwnTranslatorMock:
    def lookup(self, request):
        text = "[MOCK — NOT A TRANSLATION / НЕ ПУБЛІКУВАТИ]"
        checksum = sha256(text.encode("utf-8")).hexdigest()
        return TranslationCandidate(text, "own_translator", "synthetic:mock", "synthetic",
                                    checksum, checksum, "pending", CandidateState.MOCK_ONLY)


@dataclass(frozen=True)
class SourceResolution:
    candidates: tuple[TranslationCandidate, ...]
    selected_source: str | None
    original_sha256: str
    attempted_providers: tuple[str, ...]
    client_locale: str | None = None

    @property
    def candidate(self):
        # Only an actual translation candidate may be selected. Mock drafts are
        # retained for diagnostics, but must never masquerade as translated text.
        return next((c for c in self.candidates if c.state == CandidateState.NEEDS_REVIEW), None)

    @property
    def needs_review(self):
        return any(c.state == CandidateState.NEEDS_REVIEW for c in self.candidates)

    @property
    def english_fallback_required(self):
        return self.selected_source == "original_english"

    @property
    def selected_language(self):
        return self.client_locale if self.selected_source == "client_language" else (
            "enUS" if self.selected_source == "original_english" else None)

    def report_metadata(self):
        return dict(selected_source=self.selected_source, selected_language=self.selected_language,
                    original_sha256=self.original_sha256,
                    attempted_providers=list(self.attempted_providers),
                    candidates=[c.report_metadata() for c in self.candidates])


def resolve_translation(request: TranslationRequest, policy: SourcePolicy,
                        registry: Mapping[str, TranslationProvider]) -> SourceResolution:
    """Resolve one record by first-real-candidate priority, as in resolve_spoken_batch.

    A MOCK_ONLY response may be recorded for diagnostics but never consumes the
    record. Neither a found candidate nor an English fallback is approved content.
    """
    if not policy.sources:
        if request.client_locale is None:
            raise ValueError("client_locale_required_for_empty_source_policy")
        return SourceResolution((), "client_language", request.original_sha256, (), request.client_locale)
    candidates, attempted = [], []
    for name in policy.sources:
        attempted.append(name)
        if name == "original_english":
            return SourceResolution(tuple(candidates), name, request.original_sha256, tuple(attempted))
        provider = registry.get(name)
        if provider is None or not callable(getattr(provider, "lookup", None)):
            raise ValueError("enabled_translation_provider_not_registered:" + name)
        item = provider.lookup(request)
        if item is None:
            continue
        if not isinstance(item, TranslationCandidate) or item.provider != name or item.publishable:
            raise ValueError("translation_provider_result_invalid:" + name)
        candidates.append(item)
        if item.state == CandidateState.NEEDS_REVIEW:
            return SourceResolution(tuple(candidates), name, request.original_sha256, tuple(attempted))
    return SourceResolution(tuple(candidates), None, request.original_sha256, tuple(attempted))


@dataclass(frozen=True)
class BatchAssignment:
    canonical_spoken_id: str
    status: str
    source: str | None
    field_sha256: str | None = None
    client_locale: str | None = None

    @property
    def translated(self):
        # Candidate discovery != human-approved mapping/content or publishability.
        return False


@dataclass(frozen=True)
class SourceStageStats:
    source: str
    candidate_translations: int
    english_fallback: int
    mock_skipped: int
    remaining_for_next_source: int
    without_ukrainian_candidate: int
    without_approved_translation: int
    total: int


@dataclass(frozen=True)
class BatchTranslationReport:
    assignments: tuple[BatchAssignment, ...]
    stages: tuple[SourceStageStats, ...]
    total: int

    def metadata(self):
        return {
            "schema_version": 1,
            "scope": "offline source discovery; no approved text or runtime fallback",
            "total": self.total,
            "translation_candidates_pending_review":
                sum(a.status == "candidate_pending_review" for a in self.assignments),
            "approved_translations": 0,
            "without_approved_translation": self.total,
            "untranslated_no_source": sum(a.status == "untranslated" for a in self.assignments),
            "original_english_fallback": sum(a.status == "original_english" for a in self.assignments),
            "client_language": sum(a.status == "client_language" for a in self.assignments),
            "by_source": [vars(stage).copy() for stage in self.stages],
            "records": [vars(row).copy() | {"translated": row.translated}
                        for row in self.assignments],
        }


def resolve_spoken_batch(requests, policy: SourcePolicy,
                         registry: Mapping[str, TranslationProvider],
                         known_canonical_ids) -> BatchTranslationReport:
    """Walk exact configured provider order over an increasingly small unresolved pool.

    Canonical IDs must be supplied from the independently verified Spoken inventory
    (Stage 3). Never derive them from Ukrainian text. A non-mock candidate reserves
    a record for later review, but DOES NOT count as an approved translation.
    """
    entries = list(requests)
    known, seen = set(known_canonical_ids), set()
    for req in entries:
        if not isinstance(req, TranslationRequest):
            raise ValueError("batch_requires_translation_requests")
        ident = req.canonical_spoken_id
        if type(ident) is not str or not ident or ident not in known or ident in seen:
            raise ValueError("unverified_or_duplicate_canonical_spoken_id")
        seen.add(ident)
    entries.sort(key=lambda r: r.canonical_spoken_id)
    pending = {r.canonical_spoken_id: r for r in entries}
    selected, stats = {}, []
    total = len(entries)

    if not policy.sources:
        for req in entries:
            if req.client_locale is None:
                raise ValueError("client_locale_required_for_empty_source_policy")
            selected[req.canonical_spoken_id] = BatchAssignment(
                req.canonical_spoken_id, "client_language", "client_language",
                client_locale=req.client_locale)
        return BatchTranslationReport(tuple(selected[k] for k in sorted(selected)), (), total)

    for name in policy.sources:
        found = english = mock = 0
        provider = registry.get(name)
        if name != "original_english" and (
                provider is None or not callable(getattr(provider, "lookup", None))):
            raise ValueError("enabled_translation_provider_not_registered:" + name)
        for key in tuple(sorted(pending)):
            req = pending[key]
            if name == "original_english":
                selected[key] = BatchAssignment(key, "original_english", name)
                pending.pop(key)
                english += 1
                continue
            result = provider.lookup(req)
            if result is None:
                continue
            if not isinstance(result, TranslationCandidate) or result.provider != name or result.publishable:
                raise ValueError("translation_provider_result_invalid:" + name)
            if result.state == CandidateState.MOCK_ONLY:
                mock += 1
                continue
            selected[key] = BatchAssignment(key, "candidate_pending_review", name,
                                            field_sha256=result.field_sha256)
            pending.pop(key)
            found += 1
        candidate_total = sum(row.status == "candidate_pending_review" for row in selected.values())
        stats.append(SourceStageStats(name, found, english, mock, len(pending),
                                      total - candidate_total, total, total))
        if name == "original_english":
            break

    for key in sorted(pending):
        selected[key] = BatchAssignment(key, "untranslated", None)
    return BatchTranslationReport(tuple(selected[k] for k in sorted(selected)), tuple(stats), total)
