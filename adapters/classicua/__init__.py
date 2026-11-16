"""Pinned ClassicUA data preparation; no runtime Lua execution or pack generation."""
from .source import PINNED_REVISION, audit_checkout

__all__ = ["PINNED_REVISION", "audit_checkout"]
