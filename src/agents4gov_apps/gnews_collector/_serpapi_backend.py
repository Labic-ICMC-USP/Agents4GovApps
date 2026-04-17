"""SerpAPI backend -- fast, paginated, no Google throttling."""

from datetime import date

from ._base_backend import NewsBackend

_SERPAPI_ENDPOINT = "https://serpapi.com/search"
_PAGE_SIZE = 10


class SerpAPIBackend(NewsBackend):
    """Fetches news via SerpAPI's Google News Light endpoint.

    Requires a valid SerpAPI key.  Handles pagination automatically up to
    *max_results* articles per call.
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
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                print(
                    f"[WARN] serpapi falhou: query={query!r} "
                    f"periodo={start_date}/{end_date} offset={offset} erro={exc}"
                )
                break

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
