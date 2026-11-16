"""Trusted offline source inventories from the Stage 2A audit, never review JSON.

Like the public Spoken inventory, this is an application-supplied trust boundary.
Production callers must use from_audit() with a successful audit_checkout() result;
tests may construct inventories from invented, independently hashed fixture bytes.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType

from adapters.classicua.source import REPOSITORY, safe_relative
from adapters.crosswalk import FULL_SHA, effective_units

# Matching evidence is separate from translated content and origin line numbers.
SOURCE_FIELDS = ('source_id', 'family', 'source_revision', 'source_file_sha256',
                 'origin_file', 'origin_layer', 'source_category', 'context_sha256',
                 'effective_sha256', 'grammar_sha256', 'ai')


@dataclass(frozen=True)
class SourceInventory:
    revision: str
    files: dict
    units: dict

    def __post_init__(self):
        if not re.fullmatch(r'[a-f0-9]{40}', self.revision):
            raise ValueError('invalid_source_inventory_revision')
        files, units = dict(self.files), dict(self.units)
        for path, sha in files.items():
            if safe_relative(path) != path or not FULL_SHA.fullmatch(sha):
                raise ValueError('invalid_source_inventory_file')
        for identity, unit in units.items():
            if (identity != unit.source_id or unit.source_revision != self.revision
                    or files.get(unit.origin_file) != unit.source_file_sha256
                    or unit.context_sha256 is None or not unit.source_category):
                raise ValueError('inconsistent_source_inventory_unit')
        object.__setattr__(self, 'files', MappingProxyType(files))
        object.__setattr__(self, 'units', MappingProxyType(units))


def from_audit(dataset, report):
    """Use only the dataset/report pair returned by a successful Stage 2A audit."""
    source = report['source']
    if source['repository'] != REPOSITORY:
        raise ValueError('classicua_source_inventory_required')
    return SourceInventory(source['revision'], source['files'], effective_units(dataset))


def source_reference(unit):
    """Immutable artifact plus exact effective field; no text or line-number locator."""
    return f'classicua:{unit.source_revision}:{unit.origin_file}#{unit.source_id}'


def validate_source_unit(unit, inventory):
    if not isinstance(inventory, SourceInventory):
        raise ValueError('validated_source_inventory_required')
    expected = inventory.units.get(unit.source_id)
    if expected is None or any(getattr(unit, k) != getattr(expected, k) for k in SOURCE_FIELDS):
        raise ValueError('source_unit_provenance_mismatch')
    return expected


def validate_source_proof(unit, proof, inventory):
    validate_source_unit(unit, inventory)
    # Other artifacts have no independently validated manifest in this workflow.
    # Reject them, rather than treating a reviewer-supplied digest as validation.
    if proof.source_reference != source_reference(unit):
        raise ValueError('source_reference_mismatch')
    if proof.source_blob_sha256 != inventory.files[unit.origin_file]:
        raise ValueError('source_blob_digest_mismatch')
