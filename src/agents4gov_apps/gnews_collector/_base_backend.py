"""Abstract base class for news collection backends."""

from abc import ABC, abstractmethod
from datetime import date


class NewsBackend(ABC):
    """Contract that every news-source backend must fulfil.

    Implementors fetch articles for a single time window and return them as a
    flat list of normalised dicts.  They must never raise -- return an empty
    list on failure and print a [WARN] message instead.

    Normalised dict schema (all fields always present, value may be None):
        title        : str | None
        description  : str | None  -- snippet / lead paragraph
        url          : str | None
        published_raw: str | None  -- date string as returned by the source
        publisher    : str | None
    """

    needs_sleep: bool = True
    name: str = "unknown"

    @abstractmethod
    def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        max_results: int,
        language: str,
        country: str,
    ) -> list[dict]:
        """Fetch up to *max_results* articles for *query* in [start_date, end_date].

        Args:
            query:       Search expression (backend-specific operators allowed).
            start_date:  Inclusive start of the time window.
            end_date:    Inclusive end of the time window.
            max_results: Upper bound on returned articles.
            language:    ISO 639-1 language code, e.g. "pt".
            country:     ISO 3166-1 alpha-2 country code, e.g. "BR".

        Returns:
            List of normalised article dicts.  Empty list on error or no results.
        """
