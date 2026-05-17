"""
Análise inicial do dataset de violência de gênero coletado por
`collect_violencia_genero.py`. Produz:

  1. Frequência de notícias por categoria ao longo do tempo (anual + mensal).
  2. Distribuição de fontes (publishers) — geral e por categoria.
  3. Detecção de picos de notícias (z-score sobre média móvel de 12 meses).

Lê parquets diretamente de `step1_general/**/*.parquet` e enriquece com
`categoria` via join no xlsx de queries.

Uso:
    cd /home/samuel/personal/Agents4GovApps
    python3 scripts/analyze_violencia_genero.py \\
        --output-dir ./gnews_output_violencia_genero \\
        --queries-xlsx ./gnews_queries_violencia_genero.xlsx \\
        --report-xlsx ./gnews_output_violencia_genero/relatorio_indicadores.xlsx \\
        --figs-dir ./gnews_output_violencia_genero/figs
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
from dateutil.relativedelta import relativedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("analyze_violencia_genero")


# ── Parsing de datas relativas em PT-BR ──────────────────────────────────────
#
# SerpAPI devolve `published_raw` em forma relativa ("27 meses atrás", "ontem",
# etc.). pandas não parseia esse formato, então `published_date_parsed` chega
# como NaT em todas as linhas. Usamos `collected_at` como âncora para
# reconstruir a data absoluta.

_REL_PATTERN = re.compile(
    r"(?i)^\s*(?:(?:h[aá]|faz)\s+)?(\d+)\s+(\w+?)\s+atr[aá]s\s*$"
)


def _unit_to_kwarg(unit: str) -> str | None:
    """Normaliza unidade PT-BR (singular/plural, com acento) → kwarg de timedelta/relativedelta."""
    u = unit.lower().strip()
    # mês/mes/meses
    if u in ("mês", "mes", "meses"):
        return "months"
    # ano/anos
    if u in ("ano", "anos"):
        return "years"
    # remove plural simples
    if u.endswith("s"):
        u = u[:-1]
    return {
        "minuto": "minutes",
        "hora": "hours",
        "dia": "days",
        "semana": "weeks",
    }.get(u)


def _parse_relative_pt(raw: str, anchor: pd.Timestamp) -> pd.Timestamp:
    """Converte 'N <unidade> atrás' em data absoluta usando `anchor`."""
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


def reparse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche `published_date_parsed` para linhas com NaT usando `published_raw`
    + `collected_at` como âncora. Último fallback: midpoint da janela."""
    anchor = pd.to_datetime(df["collected_at"], utc=True, errors="coerce")
    parsed = df["published_date_parsed"]
    needs_fix = parsed.isna() & df["published_raw"].notna()

    if needs_fix.any():
        fixed = [
            _parse_relative_pt(raw, anc) if pd.notna(anc) else pd.NaT
            for raw, anc in zip(df.loc[needs_fix, "published_raw"], anchor.loc[needs_fix])
        ]
        parsed = parsed.copy()
        parsed.loc[needs_fix] = pd.to_datetime(pd.Series(fixed, index=df.index[needs_fix]), utc=True)

    still_nat = parsed.isna() & df.get("window_start", pd.Series([None] * len(df))).notna()
    if still_nat.any():
        midpoints = pd.to_datetime(df.loc[still_nat, "window_start"], utc=True, errors="coerce") + timedelta(days=15)
        parsed = parsed.copy()
        parsed.loc[still_nat] = midpoints

    df = df.copy()
    df["published_date_parsed"] = parsed
    return df


# ── Loading ─────────────────────────────────────────────────────────────────


def load_queries_mapping(queries_xlsx: Path) -> dict[str, str]:
    """Lê xlsx de queries → dict {query: categoria}."""
    df = pd.read_excel(queries_xlsx)
    if "query" not in df.columns or "categoria da query" not in df.columns:
        raise ValueError(
            f"xlsx deve ter colunas 'query' e 'categoria da query'. Encontradas: {list(df.columns)}"
        )
    df["query"] = df["query"].astype(str).str.strip()
    df["categoria da query"] = df["categoria da query"].astype(str).str.strip()
    return dict(zip(df["query"], df["categoria da query"]))


def load_dataset(output_dir: Path, queries_xlsx: Path) -> pd.DataFrame:
    base = output_dir / "step1_general"
    if not base.exists():
        raise FileNotFoundError(f"Diretório de parquets inexistente: {base}")

    files = sorted(base.glob("**/*.parquet"))
    if not files:
        raise FileNotFoundError(f"Nenhum parquet em {base}")

    log.info("Lendo %d parquets...", len(files))
    df = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
    log.info("Bruto: %d linhas", len(df))

    df = df.drop_duplicates(subset=["url"], keep="first")
    log.info("Após dedup por URL: %d linhas", len(df))

    mapping = load_queries_mapping(queries_xlsx)
    df["categoria"] = df["query_used"].map(mapping).fillna("(sem categoria)")

    df["published_date_parsed"] = pd.to_datetime(
        df["published_date_parsed"], utc=True, errors="coerce"
    )
    pre_fix_nat = df["published_date_parsed"].isna().sum()
    if pre_fix_nat > 0:
        df = reparse_dates(df)
        post_fix_nat = df["published_date_parsed"].isna().sum()
        log.info(
            "Datas relativas reparseadas: %d → %d NaT (recuperadas %d via collected_at/window_start).",
            pre_fix_nat, post_fix_nat, pre_fix_nat - post_fix_nat,
        )

    valid_dates = df["published_date_parsed"].notna()
    if (~valid_dates).any():
        log.warning("%d linhas com data inválida descartadas das séries temporais.", (~valid_dates).sum())

    df["year"] = df["published_date_parsed"].dt.year
    df["month"] = df["published_date_parsed"].dt.month
    df["year_month"] = df["published_date_parsed"].dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("M")

    return df


# ── Indicadores ──────────────────────────────────────────────────────────────


def freq_by_category_time(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sub = df.dropna(subset=["published_date_parsed"])
    yearly = (
        sub.groupby(["categoria", "year"]).size().unstack(fill_value=0).sort_index()
    )
    monthly = (
        sub.groupby(["categoria", "year_month"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    monthly.columns = monthly.columns.astype(str)
    return {"yearly": yearly, "monthly": monthly}


def source_distribution(df: pd.DataFrame, top_n: int = 30) -> dict[str, pd.DataFrame]:
    top_overall = (
        df["publisher"]
        .fillna("(desconhecido)")
        .value_counts()
        .head(top_n)
        .rename_axis("publisher")
        .reset_index(name="artigos")
    )

    by_cat = (
        df.assign(publisher=df["publisher"].fillna("(desconhecido)"))
        .groupby(["categoria", "publisher"])
        .size()
        .reset_index(name="artigos")
        .sort_values(["categoria", "artigos"], ascending=[True, False])
        .groupby("categoria", group_keys=False)
        .head(10)
    )

    return {"top_overall": top_overall, "top_by_categoria": by_cat}


def detect_spikes(df: pd.DataFrame, z_threshold: float = 2.5) -> pd.DataFrame:
    sub = df.dropna(subset=["published_date_parsed"]).copy()
    if sub.empty:
        return pd.DataFrame(columns=["categoria", "year_month", "count", "mean", "std", "z"])

    counts = (
        sub.groupby(["categoria", "year_month"]).size().rename("count").reset_index()
    )

    rows = []
    for categoria, g in counts.groupby("categoria"):
        g = g.sort_values("year_month").copy()
        g["mean"] = g["count"].rolling(12, center=True, min_periods=3).mean()
        g["std"] = g["count"].rolling(12, center=True, min_periods=3).std()
        g["z"] = (g["count"] - g["mean"]) / g["std"].replace(0, pd.NA)
        spikes = g[g["z"] > z_threshold].copy()
        if not spikes.empty:
            spikes["categoria"] = categoria
            spikes["year_month"] = spikes["year_month"].astype(str)
            rows.append(spikes[["categoria", "year_month", "count", "mean", "std", "z"]])

    if not rows:
        return pd.DataFrame(columns=["categoria", "year_month", "count", "mean", "std", "z"])
    return pd.concat(rows, ignore_index=True).sort_values("z", ascending=False)


# ── Plots ────────────────────────────────────────────────────────────────────


def plot_temporal(freq: dict[str, pd.DataFrame], figs_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib não instalado; pulando plots.")
        return

    figs_dir.mkdir(parents=True, exist_ok=True)

    yearly = freq["yearly"]
    if not yearly.empty:
        ax = yearly.T.plot(figsize=(14, 8), marker="o")
        ax.set_title("Frequência anual de notícias por categoria")
        ax.set_xlabel("Ano")
        ax.set_ylabel("Número de notícias")
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=7, ncol=1)
        fig = ax.get_figure()
        fig.tight_layout()
        fig.savefig(figs_dir / "freq_anual_por_categoria.png", dpi=120, bbox_inches="tight")
        fig.savefig(figs_dir / "freq_anual_por_categoria.svg", bbox_inches="tight")
        plt.close(fig)
        log.info("Salvo: freq_anual_por_categoria.{png,svg}")

    monthly = freq["monthly"]
    if not monthly.empty:
        ax = monthly.T.plot(figsize=(16, 8), linewidth=0.8)
        ax.set_title("Frequência mensal de notícias por categoria")
        ax.set_xlabel("Mês")
        ax.set_ylabel("Número de notícias")
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=7, ncol=1)
        fig = ax.get_figure()
        fig.tight_layout()
        fig.savefig(figs_dir / "freq_mensal_por_categoria.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        log.info("Salvo: freq_mensal_por_categoria.png")


# ── Entrypoint ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./gnews_output_violencia_genero"),
        help="Diretório raiz da coleta (contém step1_general/).",
    )
    p.add_argument(
        "--queries-xlsx",
        type=Path,
        default=Path("./gnews_queries_violencia_genero.xlsx"),
        help="xlsx com as queries (colunas: query, categoria da query).",
    )
    p.add_argument(
        "--report-xlsx",
        type=Path,
        default=Path("./gnews_output_violencia_genero/relatorio_indicadores.xlsx"),
        help="xlsx de saída com os indicadores.",
    )
    p.add_argument(
        "--figs-dir",
        type=Path,
        default=Path("./gnews_output_violencia_genero/figs"),
        help="Diretório de saída para PNGs/SVGs.",
    )
    p.add_argument("--z-threshold", type=float, default=2.5)
    p.add_argument("--top-publishers", type=int, default=30)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    df = load_dataset(args.output_dir, args.queries_xlsx)

    freq = freq_by_category_time(df)
    pubs = source_distribution(df, top_n=args.top_publishers)
    spikes = detect_spikes(df, z_threshold=args.z_threshold)

    args.report_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(str(args.report_xlsx), engine="openpyxl") as w:
        freq["yearly"].to_excel(w, sheet_name="freq_yearly")
        freq["monthly"].to_excel(w, sheet_name="freq_monthly")
        pubs["top_overall"].to_excel(w, sheet_name="top_publishers", index=False)
        pubs["top_by_categoria"].to_excel(w, sheet_name="top_publishers_por_cat", index=False)
        spikes.to_excel(w, sheet_name="spikes", index=False)

    log.info("Relatório salvo em: %s", args.report_xlsx.resolve())

    plot_temporal(freq, args.figs_dir)

    log.info("=" * 60)
    log.info("RESUMO")
    log.info("  Linhas totais        : %d", len(df))
    log.info("  Categorias distintas : %d", df["categoria"].nunique())
    valid = df["published_date_parsed"].notna()
    if valid.any():
        log.info(
            "  Range temporal       : %s → %s",
            df.loc[valid, "published_date_parsed"].min().date(),
            df.loc[valid, "published_date_parsed"].max().date(),
        )
    log.info("  Top-5 publishers     :")
    for _, row in pubs["top_overall"].head(5).iterrows():
        log.info("    %-40s %d", row["publisher"], row["artigos"])
    log.info("  Spikes detectados    : %d (z > %.1f)", len(spikes), args.z_threshold)


if __name__ == "__main__":
    main()
