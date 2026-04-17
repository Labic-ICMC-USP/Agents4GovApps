"""Abstract base class for news collection backends."""

from abc import ABC, abstractmethod
from datetime import date


class RateLimitError(Exception):
    """Raised when a backend detects it has been rate-limited or its quota is exhausted.

    Always carries the originating backend name so the orchestrator and caller
    can decide whether to fall back or abort.
    """

    def __init__(self, backend_name: str, message: str) -> None:
        self.backend_name = backend_name
        super().__init__(message)


class NewsBackend(ABC):
    """Contract that every news-source backend must fulfil.

    Implementors fetch articles for a single time window and return them as a
    flat list of normalised dicts.  They must never raise for ordinary errors
    (network timeouts, bad responses) -- return an empty list and print a
    [WARN] message instead.  They MUST raise RateLimitError when rate-limited
    or quota-exhausted so the orchestrator can fall back.

    Normalised dict schema (all fields always present, value may be None):
        title        : str | None
        description  : str | None  -- snippet / lead paragraph
        url          : str | None
        published_raw: str | None  -- date string as returned by the source
        publisher    : str | None
    """

    #: Whether the orchestrator should sleep between consecutive calls.
    #: Set to False for backends backed by a proper API (e.g. SerpAPI).
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
            List of normalised article dicts.  Empty list on non-rate-limit errors.

        Raises:
            RateLimitError: when the backend is rate-limited or quota-exhausted.
        """
