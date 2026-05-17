"""Date parsing helpers for news article timestamps.

SerpAPI returns Brazilian Portuguese relative dates ("27 meses atrás", "ontem",
"5 horas atrás") for `published_raw`. Pandas' `to_datetime(format='mixed')`
cannot parse these and emits NaT, leaving downstream analytics blind to the
publication date.

`parse_published_dates` performs a layered parse:
  1. ISO/RFC parse via pandas (handles gnews backend output).
  2. Brazilian Portuguese relative-date parse, anchored on `collected_at`.
  3. Window-midpoint fallback (best-effort approximation).
"""

from __future__ import annotations

import re
from datetime import timedelta

_REL_PATTERN = re.compile(
    r"(?i)^\s*(?:(?:h[aá]|faz)\s+)?(\d+)\s+(\w+?)\s+atr[aá]s\s*$"
)


def _unit_to_kwarg(unit: str):
    u = unit.lower().strip()
    if u in ("mês", "mes", "meses"):
        return "months"
    if u in ("ano", "anos"):
        return "years"
    if u.endswith("s"):
        u = u[:-1]
    return {"minuto": "minutes", "hora": "hours", "dia": "days", "semana": "weeks"}.get(u)


def parse_relative_pt(raw, anchor):
    """Convert a PT-BR relative-date string to absolute, anchored on `anchor`.

    Returns pd.NaT (via pandas import) on unparseable input.
    """
    import pandas as pd
    from dateutil.relativedelta import relativedelta

    if not isinstance(raw, str) or pd.isna(anchor):
        return pd.NaT
    s = raw.strip().lower()
    if s == "hoje":
        return anchor
    if s == "ontem":
        return anchor - timedelta(days=1)
    m = _REL_PATTERN.match(raw)
    if not m:
        return pd.NaT
    n = int(m.group(1))
    kwarg = _unit_to_kwarg(m.group(2))
    if kwarg is None:
        return pd.NaT
    if kwarg in ("minutes", "hours", "days", "weeks"):
        return anchor - timedelta(**{kwarg: n})
    return anchor - relativedelta(**{kwarg: n})


def parse_published_dates(df):
    """Populate `published_date_parsed` using a layered strategy.

    Expects columns: `published_raw`, `collected_at`, `window_start`.
    Returns the same DataFrame with `published_date_parsed` filled where
    possible. Mutates in place for efficiency.
    """
    import pandas as pd

    parsed = pd.to_datetime(
        df["published_raw"], errors="coerce", utc=True, format="mixed"
    )

    needs_fix = parsed.isna() & df["published_raw"].notna()
    if needs_fix.any() and "collected_at" in df.columns:
        anchor = pd.to_datetime(df["collected_at"], utc=True, errors="coerce")
        fixed = [
            parse_relative_pt(raw, anc)
            for raw, anc in zip(df.loc[needs_fix, "published_raw"], anchor.loc[needs_fix])
        ]
        parsed.loc[needs_fix] = pd.to_datetime(
            pd.Series(fixed, index=df.index[needs_fix]), utc=True
        )

    still_nat = parsed.isna()
    if still_nat.any() and "window_start" in df.columns:
        ws = pd.to_datetime(df.loc[still_nat, "window_start"], utc=True, errors="coerce")
        parsed.loc[still_nat] = ws + timedelta(days=15)

    df["published_date_parsed"] = parsed
    return df
