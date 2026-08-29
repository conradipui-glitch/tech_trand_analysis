"""Provider adapters that normalize external records into Observation objects."""

from .openalex import OpenAlexAdapter, OpenAlexProtocolError, OpenAlexQuery

__all__ = ["OpenAlexAdapter", "OpenAlexProtocolError", "OpenAlexQuery"]
