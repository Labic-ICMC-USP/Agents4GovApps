"""GNews backend -- free, scraping-based, subject to Google throttling."""

from datetime import date
from typing import Optional

from ._base_backend import NewsBackend


class GNewsBackend(NewsBackend):
    """Fetches news via the `gnews` library (scrapes Google News RSS).

    Free to use -- no API key required.  May be throttled by Google on
    high-volume or long-running collections.
    """

    def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        max_results: int,
        language: str,
        country: str,
    ) -> list[dict]:
        try:
            from gnews import GNews
        except ImportError as exc:
            raise RuntimeError(
                f"Dependencia ausente: {exc}. "
                "Execute: pip install agents4gov-apps[gnews]"
            ) from exc

        g = GNews(
            language=language,
            country=country,
            max_results=max_results,
            start_date=(start_date.year, start_date.month, start_date.day),
            end_date=(end_date.year, end_date.month, end_date.day),
        )

        try:
            raw = g.get_news(query) or []
        except Exception as exc:
            print(
                f"[WARN] gnews falhou: query={query!r} "
                f"periodo={start_date}/{end_date} erro={exc}"
            )
            return []

        return [self._normalize(a) for a in raw]

    def _normalize(self, article: dict) -> dict:
        published_raw = (
            article.get("published_date")
            or article.get("published date")
            or article.get("publishedDate")
        )
        return {
            "title": article.get("title"),
            "description": article.get("description"),
            "url": article.get("url"),
            "published_raw": published_raw,
            "publisher": self._extract_publisher(article.get("publisher")),
        }

    @staticmethod
    def _extract_publisher(value) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("title", "name", "href"):
                if key in value:
                    return value[key]
            return str(value)
        return str(value)
