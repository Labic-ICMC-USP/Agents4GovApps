# Agents4Gov Tool Protocol

This repository is now structured as an installable Python library. The canonical package is `agents4gov-tools`, built from `pyproject.toml` and the `src/agents4gov_tools/` namespace.

## Package Layout

Each tool lives in its own subpackage so teams can keep isolated internal structure while sharing one external contract.

- `src/agents4gov_tools/<tool_group>/<tool_module>.py`
- Every tool module exports a `Tools` class.
- Tool methods are the public entry points used by Open WebUI or other agents.
- Module docstrings can keep Open WebUI metadata such as `title`, `description`, `version`, and `requirements`.

## Registry Contract

The library exposes a small discovery layer in `src/agents4gov_tools/registry.py`.

- `AVAILABLE_TOOLS` maps stable keys to import paths.
- `get_tool_spec(key)` returns metadata for one tool.
- `load_tool_class(key)` imports the `Tools` class for that module.
- `load_tool_instance(key)` builds an instance directly.

## Installing Locally

```bash
pip install -e .
```

## Adding a New Tool

1. Create a new subpackage under `src/agents4gov_tools/`.
2. Add a module that exports `Tools`.
3. Add any optional dependencies to `pyproject.toml`.
4. Register the module in `src/agents4gov_tools/registry.py`.
5. Document the tool in the relevant README.

## Notes on Legacy Docs

The older single-file examples under `docs/how_to_create_tool.md` were extracted from a different repository layout. Keep them as reference material, but use this protocol as the current source of truth for new tools.
