"""
Coleta de notícias sobre violência de gênero (2016-05 → 2026-05) via Google News.

Entrada:
    gnews_queries_violencia_genero.xlsx — 81 queries em 29 categorias,
    colunas: `query`, `categoria da query`.

Estratégia:
  - Janelas mensais (1 mês por consulta) para maximizar cobertura.
  - 81 queries × 121 meses = 9.801 consultas.
  - Backend primário: SerpAPI (rápido, paginado).
    Fallback: gnews (gratuito, ~8s/consulta, ~100 resultados/janela).

Este script usa APENAS a API pública de `agents4gov_apps` (método
`collect_general_news` retornando JSON string). Funciona de forma agnóstica
com qualquer instalação via `pip install agents4gov-apps`. Checkpoint, retry,
fallback de backend, sleep entre janelas e dedup por janela ficam dentro da
biblioteca.

Output:
  - ./gnews_output_violencia_genero/step1_general/*.parquet
  - ./gnews_output_violencia_genero/noticias_violencia_genero_por_categoria.xlsx
    (uma sheet por categoria + _resumo)

Uso:
    cd /home/samuel/personal/Agents4GovApps

    # smoke test
    SERPAPI_KEY=... python3 scripts/collect_violencia_genero.py \\
        --auto-fallback --limit-queries 1 --start 2024-01 --end 2024-01

    # full run
    SERPAPI_KEY=... python3 scripts/collect_violencia_genero.py --auto-fallback
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from agents4gov_apps import load_tool_instance
from agents4gov_apps.gnews_collector import console_emitter

# ── Configuração ────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
QUERIES_XLSX = REPO_ROOT / "gnews_queries_violencia_genero.xlsx"

DEFAULT_START = "2016-05"
DEFAULT_END = "2026-05"
WINDOW_MONTHS = 1

OUTPUT_DIR = "./gnews_output_violencia_genero"
EXPORT_XLSX = Path(OUTPUT_DIR) / "noticias_violencia_genero_por_categoria.xlsx"

EXPORT_COLUMNS = [
    "categoria",
    "query",
    "title",
    "description",
    "url",
    "publisher",
    "published_raw",
    "published_date_parsed",
    "source_domain",
    "stage",
    "query_used",
    "window_start",
    "window_end",
    "backend",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("collect_violencia_genero")


# ── Loader de queries ────────────────────────────────────────────────────────


def load_queries() -> list[tuple[str, str]]:
    """Lê o xlsx de queries. Retorna [(query, categoria), ...]."""
    import pandas as pd

    if not QUERIES_XLSX.exists():
        raise FileNotFoundError(f"Arquivo de queries não encontrado: {QUERIES_XLSX}")

    df = pd.read_excel(QUERIES_XLSX)
    expected = {"query", "categoria da query"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(
            f"Colunas faltando no xlsx: {missing}. Encontradas: {list(df.columns)}"
        )

    df["query"] = df["query"].astype(str).str.strip()
    df["categoria da query"] = df["categoria da query"].astype(str).str.strip()
    df = df[(df["query"] != "") & (df["query"].str.lower() != "nan")]

    return list(zip(df["query"], df["categoria da query"]))


# ── Coleta via API pública ───────────────────────────────────────────────────


async def collect_all(
    tool,
    queries: list[tuple[str, str]],
    start_ym: str,
    end_ym: str,
) -> None:
    log.info("Início da coleta")
    log.info("  Queries     : %d", len(queries))
    log.info("  Período     : %s → %s (janelas de %d mês)", start_ym, end_ym, WINDOW_MONTHS)
    log.info("  Output dir  : %s", OUTPUT_DIR)
    log.info("  Auto-fallback: %s", tool.valves.auto_fallback)

    grand_files = 0
    grand_rows = 0
    grand_skipped = 0

    for qi, (query, categoria) in enumerate(queries, 1):
        log.info("── Query %d/%d :: [%s] '%s' ──", qi, len(queries), categoria, query)
        t0 = time.time()

        result_json = await tool.collect_general_news(
            query=query,
            start_year_month=start_ym,
            end_year_month=end_ym,
            output_dir=OUTPUT_DIR,
            window_months=WINDOW_MONTHS,
            __event_emitter__=console_emitter(log, prefix=f"  q={qi}/{len(queries)} :: "),
        )
        result = json.loads(result_json)

        if result.get("status") == "error":
            log.error(
                "  '%s' falhou: %s (%s) — windows_completed=%s, files_saved=%s",
                query,
                result.get("message"),
                result.get("error_type"),
                result.get("windows_completed"),
                result.get("files_saved"),
            )
            if not tool.valves.auto_fallback:
                log.warning("Abortando: auto_fallback=False e erro retornado.")
                return
            continue

        files = result.get("collected_files") or []
        new_files = [f for f in files if not f.get("skipped")]
        skipped = [f for f in files if f.get("skipped")]
        rows_this = sum(f["rows"] for f in new_files)

        grand_files += len(new_files)
        grand_rows += rows_this
        grand_skipped += len(skipped)

        log.info(
            "  '%s' :: %d janelas novas (+%d rows), %d puladas, backend=%s, %.1fs",
            query,
            len(new_files),
            rows_this,
            len(skipped),
            result.get("backend"),
            time.time() - t0,
        )

    log.info(
        "Coleta finalizada — %d arquivos novos, %d linhas, %d janelas puladas no total.",
        grand_files, grand_rows, grand_skipped,
    )


# ── Export XLS (uma sheet por categoria) ─────────────────────────────────────


_SHEET_FORBIDDEN = re.compile(r"[\\/?*\[\]:]")


def _sheet_name(categoria: str, used: set[str]) -> str:
    name = _SHEET_FORBIDDEN.sub("-", categoria).strip()[:31] or "categoria"
    base = name
    i = 2
    while name in used:
        suffix = f"_{i}"
        name = (base[: 31 - len(suffix)] + suffix)
        i += 1
    used.add(name)
    return name


def export_xls_per_categoria(queries: list[tuple[str, str]]) -> None:
    import pandas as pd

    log.info("Lendo parquets para exportação xlsx por categoria...")

    base = Path(OUTPUT_DIR) / "step1_general"
    if not base.exists():
        log.warning("Diretório de saída inexistente; nada para exportar.")
        return

    files = sorted(base.glob("**/*.parquet"))
    if not files:
        log.warning("Nenhum parquet encontrado; export abortado.")
        return

    dfs = []
    for pq in files:
        try:
            dfs.append(pd.read_parquet(pq))
        except Exception as e:
            log.warning("Falha ao ler %s: %s", pq, e)

    if not dfs:
        log.warning("Nenhum parquet legível; export abortado.")
        return

    merged = pd.concat(dfs, ignore_index=True)
    query_to_categoria = {q: c for q, c in queries}
    merged["query"] = merged["query_used"]
    merged["categoria"] = merged["query_used"].map(query_to_categoria)

    before = len(merged)
    merged = merged.drop_duplicates(subset=["url"], keep="first")
    after = len(merged)

    cols = [c for c in EXPORT_COLUMNS if c in merged.columns]
    export_df = merged[cols].copy()
    if "published_date_parsed" in export_df.columns:
        export_df["published_date_parsed"] = (
            export_df["published_date_parsed"].dt.tz_localize(None)
        )

    EXPORT_XLSX.parent.mkdir(parents=True, exist_ok=True)

    EXCEL_ROW_LIMIT = 1_048_575
    used_names: set[str] = set()
    sheet_counts: dict[str, int] = {}

    with pd.ExcelWriter(str(EXPORT_XLSX), engine="openpyxl") as writer:
        for categoria, group in export_df.groupby("categoria", dropna=False):
            label = "(sem categoria)" if pd.isna(categoria) else str(categoria)
            sheet = _sheet_name(label, used_names)
            if len(group) > EXCEL_ROW_LIMIT:
                log.warning("Categoria '%s' truncada de %d para %d linhas.", label, len(group), EXCEL_ROW_LIMIT)
                group = group.iloc[:EXCEL_ROW_LIMIT]
            group.to_excel(writer, sheet_name=sheet, index=False)
            sheet_counts[sheet] = len(group)

        resumo = (
            export_df.groupby("categoria", dropna=False)
            .size()
            .reset_index(name="artigos")
            .sort_values("artigos", ascending=False)
        )
        resumo.to_excel(writer, sheet_name="_resumo", index=False)

        if "published_date_parsed" in export_df.columns:
            export_df["_year"] = export_df["published_date_parsed"].dt.year
            cobertura = (
                export_df.dropna(subset=["_year"])
                .groupby(["categoria", "_year"], dropna=False)
                .size()
                .unstack(fill_value=0)
                .reset_index()
            )
            if not cobertura.empty:
                cobertura.to_excel(writer, sheet_name="_cobertura_anual", index=False)

    log.info("=" * 60)
    log.info("RESUMO DO EXPORT")
    log.info("  Parquets lidos       : %d", len(files))
    log.info("  Total linhas (bruto) : %d", before)
    log.info("  Após dedup (URL)     : %d", after)
    log.info("  xlsx salvo em        : %s", EXPORT_XLSX.resolve())
    log.info("  Sheets               : %d (uma por categoria) + _resumo", len(sheet_counts))
    for sheet, n in sorted(sheet_counts.items(), key=lambda kv: -kv[1])[:10]:
        log.info("    %-31s %d", sheet, n)


# ── Entrypoint ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--auto-fallback", action="store_true",
                   help="Troca silenciosa de backend ao esgotar rate-limit.")
    p.add_argument("--limit-queries", type=int, default=None, metavar="N",
                   help="Smoke test: apenas as primeiras N queries.")
    p.add_argument("--start", default=DEFAULT_START, help="YYYY-MM (default %s)" % DEFAULT_START)
    p.add_argument("--end", default=DEFAULT_END, help="YYYY-MM (default %s)" % DEFAULT_END)
    p.add_argument("--skip-collect", action="store_true",
                   help="Pula coleta; gera apenas xlsx a partir de parquets existentes.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    queries = load_queries()
    if args.limit_queries is not None:
        queries = queries[: args.limit_queries]
    log.info("Carregadas %d queries do xlsx.", len(queries))

    tool = load_tool_instance("gnews_collector")
    serpapi_key = os.environ.get("SERPAPI_KEY", "")
    if serpapi_key:
        tool.valves.serpapi_key = serpapi_key
    tool.valves.backend_priority = ["serpapi", "gnews"]
    tool.valves.auto_fallback = args.auto_fallback
    tool.valves.output_dir = OUTPUT_DIR

    if not args.skip_collect:
        t0 = time.time()
        asyncio.run(collect_all(tool, queries, args.start, args.end))
        log.info("Tempo total de coleta: %.2f h", (time.time() - t0) / 3600)

    export_xls_per_categoria(queries)
    log.info("Tudo pronto.")


if __name__ == "__main__":
    main()
