"""
Coleta de notícias por palavras-chave (2010–2025) via Google News.

Palavras-chave: polícia, crime, prisão, violência, justiça,
                violência policial, crime organizado

Estratégia:
  - Janelas mensais (1 mês por consulta) para maximizar cobertura.
  - 7 keywords × 192 meses = 1.344 consultas no total.
  - Backend automático: SerpAPI se SERPAPI_KEY estiver definida no ambiente,
    senão gnews (fallback gratuito, ~8 s/consulta ≈ 3 h).

Checkpoint/retomada:
  - Parquets já existentes são pulados automaticamente.
  - Pode ser interrompido e retomado sem retrabalho.

Uso:
    cd /home/samuel/personal/Agents4GovApps

    # com SerpAPI (rápido):
    SERPAPI_KEY=sua_chave python3 scripts/collect_keywords_sp_rj.py

    # sem chave (gnews fallback):
    python3 scripts/collect_keywords_sp_rj.py
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass 
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents4gov_apps import load_tool_instance  # noqa: E402

# ── Configuração ────────────────────────────────────────────────────────────

KEYWORDS = [
    "polícia",
    "crime",
    "prisão",
    "violência",
    "justiça",
    "violência policial",
    "crime organizado",
]

START = "2010-01"
END   = "2025-12"

OUTPUT_DIR = "./gnews_output_keywords"
XLS_PATH   = Path(OUTPUT_DIR) / "noticias_keywords_2010_2025.xlsx"

EXPORT_COLUMNS = [
    "keyword",
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
]

# ── Helpers ─────────────────────────────────────────────────────────────────


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _parquet_path(tool, keyword: str, start_dt, end_dt) -> Path:
    """Replica a lógica de nomeação usada pelo tool para poder checar checkpoint."""
    sanitized = tool._sanitize(keyword)
    return (
        Path(OUTPUT_DIR)
        / "step1_general"
        / tool._sanitize(keyword)
        / f"general__{sanitized}__{start_dt.isoformat()}__{end_dt.isoformat()}.parquet"
    )


# ── Coleta ───────────────────────────────────────────────────────────────────


async def collect_all(tool):
    windows = tool._build_windows(START, END, window_months=1)
    total_windows = len(windows)
    total_queries = len(KEYWORDS) * total_windows

    print(f"[{_ts()}] Início da coleta")
    print(
        f"  Keywords  : {len(KEYWORDS)}")
    print(
        f"  Janelas   : {total_windows} (mensais, {START} → {END})")
    print(
        f"  Total ops : {total_queries}")
    backend_name = tool._backend.name
    print(f"  Backend   : {backend_name}")
    print()

    grand_total_rows = 0
    grand_skipped    = 0
    op = 0

    for ki, keyword in enumerate(KEYWORDS, 1):
        kw_rows    = 0
        kw_skipped = 0

        print(f"[{_ts()}] ── Keyword {ki}/{len(KEYWORDS)}: '{keyword}' ──────────────")

        for wi, (start_dt, end_dt) in enumerate(windows, 1):
            op += 1
            pq_path = _parquet_path(tool, keyword, start_dt, end_dt)

            if pq_path.exists():
                kw_skipped += 1
                grand_skipped += 1
                continue

            df = tool._search_window(
                query=keyword,
                start_date_obj=start_dt,
                end_date_obj=end_dt,
                stage="general",
                source_domain=None,
            )

            rows_this = 0
            if not df.empty:
                pq_path.parent.mkdir(parents=True, exist_ok=True)
                save = tool._save_parquet(df, pq_path)
                if save["ok"]:
                    rows_this = save["rows"]
                    kw_rows += rows_this
                    grand_total_rows += rows_this
                else:
                    print(f"  [ERRO] {save['error']}")

            print(
                f"  [{_ts()}] kw={ki}/{len(KEYWORDS)} "
                f"janela={wi}/{total_windows} "
                f"{start_dt}→{end_dt}  "
                f"rows={rows_this}  "
                f"(total op {op}/{total_queries})"
            )

            if tool._backend.needs_sleep:
                await asyncio.sleep(tool.valves.sleep_seconds)

        print(
            f"[{_ts()}] '{keyword}' concluído: "
            f"{kw_rows} artigos novos, {kw_skipped} janelas puladas (checkpoint)\n"
        )

    print(
        f"[{_ts()}] Coleta finalizada — "
        f"{grand_total_rows} artigos novos, "
        f"{grand_skipped} janelas puladas no total."
    )


# ── Export XLS ───────────────────────────────────────────────────────────────


def export_xls():
    import pandas as pd

    print(f"\n[{_ts()}] Lendo todos os parquets para exportação XLS...")

    base = Path(OUTPUT_DIR) / "step1_general"
    if not base.exists():
        print("  Nenhum diretório de saída encontrado. Abortando export.")
        return

    dfs = []
    for kw_dir in sorted(base.iterdir()):
        if not kw_dir.is_dir():
            continue
        keyword_label = kw_dir.name.replace("_", " ")
        for pq in sorted(kw_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(pq)
                df["keyword"] = keyword_label
                dfs.append(df)
            except Exception as e:
                print(f"  [WARN] Não foi possível ler {pq}: {e}")

    if not dfs:
        print("  Nenhum parquet encontrado. Export abortado.")
        return

    merged = pd.concat(dfs, ignore_index=True)
    before = len(merged)
    merged = merged.drop_duplicates(subset=["url"], keep="first")
    after  = len(merged)

    cols = [c for c in EXPORT_COLUMNS if c in merged.columns]
    export_df = merged[cols].copy()

    if "published_date_parsed" in export_df.columns:
        export_df["published_date_parsed"] = (
            export_df["published_date_parsed"].dt.tz_localize(None)
        )

    XLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_excel(str(XLS_PATH), index=False, sheet_name="Keywords 2010-2025")

    print()
    print("=" * 70)
    print("RESUMO DO EXPORT")
    print("=" * 70)
    print(f"  Parquets lidos       : {len(dfs)}")
    print(f"  Total linhas (bruto) : {before}")
    print(f"  Após dedup (URL)     : {after}")
    print(f"  XLS salvo em         : {XLS_PATH.resolve()}")
    print()

    if "keyword" in export_df.columns:
        print("  Artigos por keyword:")
        for kw, n in export_df["keyword"].value_counts().items():
            print(f"    {kw}: {n}")
        print()


# ── Entrypoint ───────────────────────────────────────────────────────────────


def main():
    tool = load_tool_instance("gnews_collector")
    serpapi_key = os.environ.get("SERPAPI_KEY", "")
    if serpapi_key:
        tool.valves.serpapi_key = serpapi_key

    t0 = time.time()
    asyncio.run(collect_all(tool))
    elapsed = time.time() - t0
    print(f"[{_ts()}] Tempo total de coleta: {elapsed / 3600:.2f} h\n")

    export_xls()
    print(f"\n[{_ts()}] Tudo pronto.")


if __name__ == "__main__":
    main()
