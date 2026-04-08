# Agents4Gov Documentation

## Project Structure

```
Agents4Gov/
├── src/agents4gov_apps/   # Installable Python package
│   ├── protocol.py        # BaseTool ABC + ToolSpecification dataclass
│   ├── registry.py        # Tool discovery and dynamic loading
│   ├── openalex/          # OpenAlex tools
│   ├── openml/            # OpenML tools
│   └── cnpq_lattes_navigator_coi/  # Lattes/CNPq tools
├── docs/                  # Documentation
└── pyproject.toml         # Package configuration
```

## Documentation

- **[Developer Guide](developer_guide.md)** — Architecture, standard interface, how to create and use tools across Open WebUI, LangChain, OpenAI, and other frameworks.
- **[Tool Protocol](tool_protocol.md)** — Concise packaging contract for contributors.

## External Resources

- **[Open WebUI GitHub](https://github.com/open-webui/open-webui)**
- **[Open WebUI Documentation](https://docs.openwebui.com/)**
- **[Open WebUI Tools Guide](https://docs.openwebui.com/features/plugin/tools)**
