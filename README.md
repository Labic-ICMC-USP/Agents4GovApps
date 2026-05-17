# Agents4GovApps

**Laboratory of Computational Intelligence (LABIC – ICMC/USP)**

## Overview

**Agents4Gov** is a research and development project from **LABIC – Institute of Mathematics and Computer Sciences (ICMC/USP)** focused on building **LLM-based tools** to support and modernize **public sector services**.
The project emphasizes **local Large Language Models (LLMs)** for privacy, **data anonymization**, and the **development and evaluation of tools** for use in government and institutional environments.

## Installation

```bash
# Base package
pip install agents4gov-apps

# With OpenML tools
pip install agents4gov-apps[openml]

# With browser-based tools (Lattes)
pip install agents4gov-apps[browser]

# With GNews collector
pip install agents4gov-apps[gnews]
```

## Quick start

```python
from agents4gov_apps import load_tool_instance
import json

# OpenAlex
tool = load_tool_instance("openalex_doi")
result = json.loads(tool.get_openalex_metadata_by_doi(doi="10.1038/s41586-021-03819-2"))

# GNews (async)
import asyncio
tool = load_tool_instance("gnews_collector")
result = asyncio.run(tool.collect_general_news(
    query='"ICMC USP"',
    start_year_month="2023-01",
    end_year_month="2024-12",
))
```

## Research pipelines

End-to-end scripts that drive the bundled tools for concrete research tasks.
They use only the public API (`load_tool_instance` + the tool's documented
methods) so they keep working with any `pip install agents4gov-apps` version.

### Gender-violence news monitoring (10-year window)

Crawls Brazilian Portuguese news for a curated list of gender-violence queries
(read from an Excel file with `query` + `categoria da query` columns), then
produces initial indicators: frequency by category over time, top publishers,
spike detection.

Pipeline files (under `scripts/`):

- `collect_violencia_genero.py` — drives `gnews_collector.collect_general_news`
  one query at a time across monthly windows. Idempotent (skips parquets
  already on disk via the library's built-in checkpoint), supports SerpAPI
  primary + gnews fallback, and exports an Excel workbook with one sheet per
  category.
- `analyze_violencia_genero.py` — reads the parquets, joins the category from
  the queries Excel, and writes a report workbook with `freq_yearly`,
  `freq_monthly`, `top_publishers`, `top_publishers_por_cat`, and `spikes`
  sheets, plus optional PNG/SVG plots.

Usage:

```bash
pip install agents4gov-apps[gnews] openpyxl python-dotenv matplotlib

# 1) Smoke test (one query, one month)
SERPAPI_KEY=... python3 scripts/collect_violencia_genero.py \
    --auto-fallback --limit-queries 1 --start 2024-01 --end 2024-01

# 2) Full collection (81 queries × 121 months, ~10-14h on SerpAPI)
SERPAPI_KEY=... python3 scripts/collect_violencia_genero.py --auto-fallback \
    2>&1 | tee collect.log

# 3) Indicators
python3 scripts/analyze_violencia_genero.py \
    --output-dir ./gnews_output_violencia_genero \
    --queries-xlsx ./gnews_queries_violencia_genero.xlsx
```

The collector is resumable — interrupt with Ctrl+C and re-run; it skips every
window whose parquet is already on disk.

Adapt the same shape to other query sets by replacing the Excel file (any
two-column `query` + `categoria da query` workbook works).

## Documentation

- **[Developer Guide](docs/developer_guide.md)** — architecture, standard interface, how to create and use tools across Open WebUI, LangChain, OpenAI, and other frameworks
- **[Tool Protocol](docs/tool_protocol.md)** — quick-reference packaging contract
- **[Available Tools](TOOLS.md)** — full list of tools with source links
