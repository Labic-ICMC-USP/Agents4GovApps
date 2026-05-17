"""SerpAPI backend -- fast, paginated, no Google throttling."""

from datetime import date

from ._base_backend import NewsBackend, RateLimitError

_SERPAPI_ENDPOINT = "https://serpapi.com/search"
_PAGE_SIZE = 10

_RATE_LIMIT_HTTP_CODES = {429, 403}
_RATE_LIMIT_MESSAGES = (
    "your account has run out of searches",
    "rate limit",
    "quota",
    "exceeded",
)


class SerpAPIBackend(NewsBackend):
    """Fetches news via SerpAPI's Google News Light endpoint.

    Requires a valid SerpAPI key.  Handles pagination automatically up to
    *max_results* articles per call.

    Raises:
        RateLimitError: on HTTP 429/403 or quota-exceeded JSON error.
        Exception:      on network failure, invalid API key, or any other
                        non-rate-limit error -- so the orchestrator can fall
                        back to the next backend instead of silently returning [].
    """

    needs_sleep: bool = False
    name: str = "serpapi"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        max_results: int,
        language: str,
        country: str,
    ) -> list[dict]:
        import requests as _requests

        date_query = (
            f"{query} after:{start_date.isoformat()} before:{end_date.isoformat()}"
        )

        articles: list[dict] = []
        offset = 0

        while len(articles) < max_results:
            params = {
                "engine": "google_news_light",
                "q": date_query,
                "gl": country.lower(),
                "hl": language,
                "start": offset,
                "api_key": self._api_key,
            }

            try:
                resp = _requests.get(_SERPAPI_ENDPOINT, params=params, timeout=30)
            except Exception as exc:
                raise Exception(
                    f"serpapi erro de rede: query={query!r} "
                    f"periodo={start_date}/{end_date} offset={offset} — {exc}"
                ) from exc

            if resp.status_code in _RATE_LIMIT_HTTP_CODES:
                raise RateLimitError(
                    self.name,
                    f"SerpAPI retornou HTTP {resp.status_code} (rate limit / quota esgotada). "
                    f"query={query!r} periodo={start_date}/{end_date}",
                )

            try:
                resp.raise_for_status()
            except Exception as exc:
                raise Exception(
                    f"serpapi HTTP {resp.status_code}: query={query!r} "
                    f"periodo={start_date}/{end_date} offset={offset} — {exc}"
                ) from exc

            try:
                data = resp.json()
            except Exception as exc:
                raise Exception(
                    f"serpapi resposta invalida (nao-JSON): query={query!r} "
                    f"periodo={start_date}/{end_date} offset={offset} — {exc}"
                ) from exc

            error_msg = (data.get("error") or "").lower()
            if error_msg:
                if any(kw in error_msg for kw in _RATE_LIMIT_MESSAGES):
                    raise RateLimitError(
                        self.name,
                        f"SerpAPI reportou limite: {data['error']!r}. "
                        f"query={query!r} periodo={start_date}/{end_date}",
                    )
                # Any other API-level error (invalid key, bad params, etc.).
                raise Exception(
                    f"serpapi erro da API: {data['error']!r}. "
                    f"query={query!r} periodo={start_date}/{end_date}"
                )

            page = data.get("news_results") or []
            if not page:
                break

            articles.extend(page)

            if not data.get("serpapi_pagination", {}).get("next"):
                break

            offset += _PAGE_SIZE

        return [self._normalize(a) for a in articles[:max_results]]

    @staticmethod
    def _normalize(article: dict) -> dict:
        return {
            "title": article.get("title"),
            "description": article.get("snippet"),
            "url": article.get("link"),
            "published_raw": article.get("date"),
            "publisher": article.get("source"),
        }
