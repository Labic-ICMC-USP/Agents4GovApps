"""
title: GNews Collector
author: agents4gov
description: Coleta noticias do Google News via SerpAPI (preferencial) ou gnews (fallback gratuito), com janelas configuraveis
required_open_webui_version: 0.4.0
requirements: gnews, pandas, pyarrow, python-dateutil, requests
version: 2.1.0
licence: MIT
"""

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from ._base_backend import NewsBackend
from ._gnews_backend import GNewsBackend
from ._serpapi_backend import SerpAPIBackend


class Tools:
    class Valves(BaseModel):
        serpapi_key: str = Field(
            default="",
            description=(
                "Chave da SerpAPI. Quando preenchida, usa Google News Light API "
                "(rapido, sem throttling). Quando vazia, usa gnews como fallback gratuito."
            ),
        )
        language: str = Field(
            default="pt",
            description="Idioma das buscas (ISO 639-1, ex: pt, en, es)",
        )
        country: str = Field(
            default="BR",
            description="Pais das buscas (ISO 3166-1 alpha-2, ex: BR, US)",
        )
        max_results: int = Field(
            default=100,
            description="Maximo de resultados por consulta (limite gnews: 100, serpapi: paginado)",
        )
        sleep_seconds: float = Field(
            default=8.0,
            description=(
                "Pausa em segundos entre consultas (aplicada apenas no backend gnews). "
                "Ignorada quando SerpAPI esta em uso. Recomendado: >= 8.0 para evitar throttling."
            ),
        )
        output_dir: str = Field(
            default="./gnews_output",
            description="Pasta de saida padrao para os arquivos Parquet",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def collect_general_news(
        self,
        query: str = Field(
            ...,
            description=(
                "Termo de busca. Aspas para expressoes exatas, ex: '\"ICMC USP\"'. "
                "Suporta operadores booleanos: AND, OR, -termo"
            ),
        ),
        start_year_month: str = Field(
            ...,
            description="Inicio do periodo no formato YYYY-MM, ex: '2020-01'",
        ),
        end_year_month: str = Field(
            ...,
            description="Fim do periodo no formato YYYY-MM, ex: '2026-03'",
        ),
        output_dir: str = Field(
            default="",
            description="Pasta de saida para os parquets. Usa Valves.output_dir se vazio.",
        ),
        window_months: int = Field(
            default=3,
            description=(
                "Tamanho de cada janela de busca em meses (padrao 3 = trimestral). "
                "Use 1 para cobertura maxima em periodos longos."
            ),
        ),
        __event_emitter__=None,
    ) -> str:
        """
        Coleta noticias gerais para uma query e periodo, sem filtro de fonte.

        O periodo e dividido em janelas de `window_months` meses para contornar
        o limite de resultados por consulta. Cada janela gera um arquivo Parquet
        individual em output_dir/step1_general/.

        Args:
            query:            Termo de busca
            start_year_month: Inicio do periodo (YYYY-MM)
            end_year_month:   Fim do periodo (YYYY-MM)
            output_dir:       Pasta de saida (opcional, sobrescreve Valves.output_dir)
            window_months:    Tamanho de cada janela em meses (padrao 3)

        Returns:
            JSON com resumo da coleta.
        """
        try:
            import pandas  # noqa: F401
        except ImportError:
            return self._error(
                "missing_dependency",
                "pandas nao instalado. Execute: pip install agents4gov-apps[gnews]",
            )

        out_dir = Path(output_dir or self.valves.output_dir)

        try:
            windows = self._build_windows(start_year_month, end_year_month, window_months)
        except ValueError as e:
            return self._error("invalid_period", str(e))

        collected: list[dict] = []
        errors: list[str] = []

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {
                "description": (
                    f"Coleta geral: {len(windows)} janelas de {window_months} mes(es)"
                    f" | query={query} | backend={self._backend.name}"
                ),
                "done": False,
            }})

        for i, (start_dt, end_dt) in enumerate(windows):
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {
                    "description": f"[{i + 1}/{len(windows)}] {start_dt} a {end_dt}",
                    "done": False,
                }})

            df = self._search_window(
                query=query,
                start_date_obj=start_dt,
                end_date_obj=end_dt,
                stage="general",
                source_domain=None,
            )

            if not df.empty:
                file_path = (
                    out_dir / "step1_general"
                    / f"general__{self._sanitize(query)}"
                      f"__{start_dt.isoformat()}__{end_dt.isoformat()}.parquet"
                )
                save = self._save_parquet(df, file_path)
                if save["ok"]:
                    collected.append({
                        "window": f"{start_dt.isoformat()}/{end_dt.isoformat()}",
                        "path": str(file_path),
                        "rows": save["rows"],
                    })
                else:
                    errors.append(save["error"])

            if self._backend.needs_sleep:
                await asyncio.sleep(self.valves.sleep_seconds)

        total_rows = sum(c["rows"] for c in collected)

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {
                "description": f"Concluido: {total_rows} artigos em {len(collected)} arquivos",
                "done": True,
            }})

        return json.dumps({
            "status": "success",
            "stage": "general",
            "backend": self._backend.name,
            "query": query,
            "period": {"start": start_year_month, "end": end_year_month},
            "window_months": window_months,
            "windows_total": len(windows),
            "files_saved": len(collected),
            "total_rows": total_rows,
            "output_dir": str(out_dir / "step1_general"),
            "collected_files": collected,
            "errors": errors or None,
        }, ensure_ascii=False, indent=2)

    async def collect_by_sources(
        self,
        query: str = Field(
            ...,
            description="Termo de busca base, ex: '\"ICMC USP\"'",
        ),
        start_year_month: str = Field(
            ...,
            description="Inicio do periodo no formato YYYY-MM, ex: '2020-01'",
        ),
        end_year_month: str = Field(
            ...,
            description="Fim do periodo no formato YYYY-MM, ex: '2026-03'",
        ),
        source_domains: List[str] = Field(
            ...,
            description=(
                "Lista de dominios para filtrar a busca, "
                "ex: ['g1.globo.com', 'jornal.usp.br', 'icmc.usp.br']"
            ),
        ),
        output_dir: str = Field(
            default="",
            description="Pasta de saida para os parquets. Usa Valves.output_dir se vazio.",
        ),
        __event_emitter__=None,
    ) -> str:
        """
        Coleta noticias filtradas por dominios/fontes especificos.

        Para cada dominio da lista, repete a busca em todas as janelas trimestrais
        do periodo. A query e automaticamente combinada com 'site:<domain>'.
        Cada combinacao dominio+janela gera um arquivo Parquet em output_dir/step2_sources/.

        Args:
            query:          Termo de busca base
            start_year_month: Inicio do periodo (YYYY-MM)
            end_year_month:   Fim do periodo (YYYY-MM)
            source_domains: Lista de dominios a filtrar
            output_dir:     Pasta de saida (opcional, sobrescreve Valves.output_dir)

        Returns:
            JSON com resumo por dominio.
        """
        try:
            import pandas  # noqa: F401
        except ImportError:
            return self._error(
                "missing_dependency",
                "pandas nao instalado. Execute: pip install agents4gov-apps[gnews]",
            )

        out_dir = Path(output_dir or self.valves.output_dir)

        try:
            windows = self._build_windows(start_year_month, end_year_month)
        except ValueError as e:
            return self._error("invalid_period", str(e))

        total_ops = len(source_domains) * len(windows)
        collected: list[dict] = []
        errors: list[str] = []
        domain_summary: dict[str, int] = {}
        op = 0

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {
                "description": (
                    f"Coleta por fontes: {len(source_domains)} dominios x "
                    f"{len(windows)} janelas = {total_ops} consultas"
                ),
                "done": False,
            }})

        for domain in source_domains:
            domain_rows = 0
            for start_dt, end_dt in windows:
                op += 1
                if __event_emitter__:
                    await __event_emitter__({"type": "status", "data": {
                        "description": f"[{op}/{total_ops}] {domain} | {start_dt} a {end_dt}",
                        "done": False,
                    }})

                domain_query = f"{query} site:{domain}"
                df = self._search_window(
                    query=domain_query,
                    start_date_obj=start_dt,
                    end_date_obj=end_dt,
                    stage="source_filtered",
                    source_domain=domain,
                )

                if not df.empty:
                    file_path = (
                        out_dir / "step2_sources"
                        / f"source__{self._sanitize(domain)}"
                          f"__{start_dt.isoformat()}__{end_dt.isoformat()}.parquet"
                    )
                    save = self._save_parquet(df, file_path)
                    if save["ok"]:
                        collected.append({
                            "domain": domain,
                            "window": f"{start_dt.isoformat()}/{end_dt.isoformat()}",
                            "path": str(file_path),
                            "rows": save["rows"],
                        })
                        domain_rows += save["rows"]
                    else:
                        errors.append(save["error"])

                if self._backend.needs_sleep:
                    await asyncio.sleep(self.valves.sleep_seconds)

            domain_summary[domain] = domain_rows

        total_rows = sum(c["rows"] for c in collected)

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {
                "description": f"Concluido: {total_rows} artigos em {len(collected)} arquivos",
                "done": True,
            }})

        return json.dumps({
            "status": "success",
            "stage": "source_filtered",
            "backend": self._backend.name,
            "query": query,
            "period": {"start": start_year_month, "end": end_year_month},
            "domains_searched": len(source_domains),
            "windows_per_domain": len(windows),
            "total_queries": total_ops,
            "files_saved": len(collected),
            "total_rows": total_rows,
            "output_dir": str(out_dir / "step2_sources"),
            "domain_summary": domain_summary,
            "collected_files": collected,
            "errors": errors or None,
        }, ensure_ascii=False, indent=2)

    @property
    def _backend(self) -> NewsBackend:
        if self.valves.serpapi_key:
            return SerpAPIBackend(self.valves.serpapi_key)
        return GNewsBackend()

    def _search_window(
        self,
        query: str,
        start_date_obj: date,
        end_date_obj: date,
        stage: str,
        source_domain: Optional[str] = None,
    ):
        """Runs one search window and returns a metadata-enriched DataFrame."""
        import pandas as pd

        articles = self._backend.search(
            query=query,
            start_date=start_date_obj,
            end_date=end_date_obj,
            max_results=self.valves.max_results,
            language=self.valves.language,
            country=self.valves.country,
        )

        if not articles:
            return pd.DataFrame()

        now = datetime.utcnow().isoformat()
        for a in articles:
            a["stage"] = stage
            a["query_used"] = query
            a["source_domain"] = source_domain
            a["window_start"] = start_date_obj.isoformat()
            a["window_end"] = end_date_obj.isoformat()
            a["collected_at"] = now

        df = pd.DataFrame(articles)
        df["published_date_parsed"] = pd.to_datetime(
            df["published_raw"], errors="coerce", utc=True, format="mixed"
        )
        return df

    def _build_windows(
        self, start_ym: str, end_ym: str, window_months: int = 3
    ) -> list[tuple[date, date]]:
        """Generates consecutive windows of *window_months* months."""
        from dateutil.relativedelta import relativedelta

        try:
            start = self._parse_year_month(start_ym)
            global_end = self._end_of_month(self._parse_year_month(end_ym))
        except ValueError:
            raise ValueError(
                f"Formato de periodo invalido: '{start_ym}' ou '{end_ym}'. "
                "Use o formato YYYY-MM, ex: '2020-01'."
            )

        windows = []
        current = start
        while current <= global_end:
            window_end = self._end_of_month(
                current + relativedelta(months=window_months - 1)
            )
            if window_end > global_end:
                window_end = global_end
            windows.append((current, window_end))
            current = current + relativedelta(months=window_months)

        return windows

    def _parse_year_month(self, ym: str) -> date:
        return datetime.strptime(ym, "%Y-%m").date().replace(day=1)

    def _end_of_month(self, d: date) -> date:
        from dateutil.relativedelta import relativedelta
        return (d.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)

    def _save_parquet(self, df, filepath: Path) -> dict:
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(filepath, index=False)
            return {"ok": True, "rows": len(df)}
        except Exception as e:
            return {"ok": False, "error": f"Erro ao salvar {filepath}: {e}", "rows": 0}

    def _sanitize(self, text: str) -> str:
        text = text.strip().lower()
        text = re.sub(r"https?://", "", text)
        text = re.sub(r"[^a-zA-Z0-9._-]+", "_", text)
        text = re.sub(r"_+", "_", text)
        return text.strip("_")

    @staticmethod
    def _error(error_type: str, message: str, **extra) -> str:
        return json.dumps(
            {"status": "error", "error_type": error_type, "message": message, **extra},
            ensure_ascii=False,
            indent=2,
        )
