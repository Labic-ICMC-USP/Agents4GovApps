"""
title: GNews Collector
author: agents4gov
description: Coleta noticias do Google News com janelas trimestrais automaticas para superar o limite de 100 resultados por consulta
required_open_webui_version: 0.4.0
requirements: gnews, pandas, pyarrow, python-dateutil
version: 1.0.0
licence: MIT
"""

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
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
            description="Maximo de resultados por consulta GNews (limite da API: 100)",
        )
        sleep_seconds: float = Field(
            default=1.0,
            description="Pausa em segundos entre consultas para evitar bloqueio",
        )
        output_dir: str = Field(
            default="./gnews_output",
            description="Pasta de saida padrao para os arquivos Parquet",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ------------------------------------------------------------------ #
    # Public tool methods                                                  #
    # ------------------------------------------------------------------ #

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
        __event_emitter__=None,
    ) -> str:
        """
        Coleta noticias gerais via GNews para uma query e periodo, sem filtro de fonte.

        O periodo e automaticamente dividido em janelas de 3 meses para contornar
        o limite de 100 resultados por consulta do GNews. Cada janela gera um
        arquivo Parquet individual em output_dir/step1_general/.

        Args:
            query: Termo de busca GNews
            start_year_month: Inicio do periodo (YYYY-MM)
            end_year_month: Fim do periodo (YYYY-MM)
            output_dir: Pasta de saida (opcional, sobrescreve Valves.output_dir)

        Returns:
            JSON com resumo da coleta: janelas processadas, arquivos salvos,
            total de linhas e lista de erros.
        """
        try:
            import pandas  # noqa: F401  — validate dependency before starting
        except ImportError:
            return self._error(
                "missing_dependency",
                "pandas nao instalado. Execute: pip install agents4gov-apps[gnews]",
            )

        out_dir = Path(output_dir or self.valves.output_dir)

        try:
            windows = self._build_quarter_windows(start_year_month, end_year_month)
        except ValueError as e:
            return self._error("invalid_period", str(e))

        collected: list[dict] = []
        errors: list[str] = []

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {
                "description": f"Coleta geral: {len(windows)} janelas trimestrais | query={query}",
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
            "query": query,
            "period": {"start": start_year_month, "end": end_year_month},
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
        Coleta noticias filtradas por dominios/fontes especificos via GNews.

        Para cada dominio da lista, repete a busca em todas as janelas trimestrais
        do periodo. A query e automaticamente combinada com 'site:<domain>'.
        Cada combinacao dominio+janela gera um arquivo Parquet em output_dir/step2_sources/.

        Args:
            query: Termo de busca base
            start_year_month: Inicio do periodo (YYYY-MM)
            end_year_month: Fim do periodo (YYYY-MM)
            source_domains: Lista de dominios a filtrar
            output_dir: Pasta de saida (opcional, sobrescreve Valves.output_dir)

        Returns:
            JSON com resumo por dominio: total de consultas, arquivos salvos,
            artigos coletados por fonte e erros.
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
            windows = self._build_quarter_windows(start_year_month, end_year_month)
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

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_quarter_windows(self, start_ym: str, end_ym: str) -> list[tuple[date, date]]:
        """Gera janelas trimestrais consecutivas entre start_ym e end_ym."""
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
            window_end = self._end_of_month(current + relativedelta(months=2))
            if window_end > global_end:
                window_end = global_end
            windows.append((current, window_end))
            current = current + relativedelta(months=3)

        return windows

    def _parse_year_month(self, ym: str) -> date:
        return datetime.strptime(ym, "%Y-%m").date().replace(day=1)

    def _end_of_month(self, d: date) -> date:
        from dateutil.relativedelta import relativedelta
        return (d.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)

    def _search_window(
        self,
        query: str,
        start_date_obj: date,
        end_date_obj: date,
        stage: str,
        source_domain: Optional[str] = None,
    ):
        """Executa uma consulta GNews e retorna DataFrame normalizado.

        Nunca lanca excecao: retorna DataFrame vazio em caso de erro.
        """
        try:
            import pandas as pd
            from gnews import GNews
        except ImportError as e:
            raise RuntimeError(
                f"Dependencia ausente: {e}. "
                "Execute: pip install agents4gov-apps[gnews]"
            )

        g = GNews(
            language=self.valves.language,
            country=self.valves.country,
            max_results=self.valves.max_results,
            start_date=(start_date_obj.year, start_date_obj.month, start_date_obj.day),
            end_date=(end_date_obj.year, end_date_obj.month, end_date_obj.day),
        )

        try:
            articles = g.get_news(query) or []
        except Exception as e:
            print(
                f"[WARN] Consulta falhou: query={query!r} "
                f"periodo={start_date_obj}/{end_date_obj} erro={e}"
            )
            return pd.DataFrame()

        if not articles:
            return pd.DataFrame()

        rows = [
            self._normalize_article(
                article=a,
                stage=stage,
                query_used=query,
                window_start=start_date_obj,
                window_end=end_date_obj,
                source_domain=source_domain,
            )
            for a in articles
        ]

        df = pd.DataFrame(rows)
        df["published_date_parsed"] = pd.to_datetime(
            df["published_raw"], errors="coerce", utc=True
        )
        return df

    def _normalize_article(
        self,
        article: dict,
        stage: str,
        query_used: str,
        window_start: date,
        window_end: date,
        source_domain: Optional[str] = None,
    ) -> dict:
        published_raw = (
            article.get("published_date")
            or article.get("published date")
            or article.get("publishedDate")
        )
        return {
            "stage": stage,
            "query_used": query_used,
            "source_domain": source_domain,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "title": article.get("title"),
            "description": article.get("description"),
            "url": article.get("url"),
            "published_raw": published_raw,
            "publisher": self._normalize_publisher(article.get("publisher")),
            "collected_at": datetime.utcnow().isoformat(),
        }

    def _normalize_publisher(self, value) -> Optional[str]:
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
        text = re.sub(r'[^a-zA-Z0-9._-]+', "_", text)
        text = re.sub(r"_+", "_", text)
        return text.strip("_")

    @staticmethod
    def _error(error_type: str, message: str, **extra) -> str:
        return json.dumps(
            {"status": "error", "error_type": error_type, "message": message, **extra},
            ensure_ascii=False,
            indent=2,
        )
