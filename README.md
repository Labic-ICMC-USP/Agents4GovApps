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

## Documentation

- **[Developer Guide](docs/developer_guide.md)** — architecture, standard interface, how to create and use tools across Open WebUI, LangChain, OpenAI, and other frameworks
- **[Tool Protocol](docs/tool_protocol.md)** — quick-reference packaging contract
- **[Available Tools](TOOLS.md)** — full list of tools with source links
