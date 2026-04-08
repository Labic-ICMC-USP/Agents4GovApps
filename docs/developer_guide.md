# Agents4Gov Developer Guide

This guide covers the library architecture, current best-practice adherence, gaps to address, and step-by-step instructions for using tools across different platforms (Open WebUI, LangChain, OpenAI function calling, plain Python).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Best Practices Reference](#2-best-practices-reference)
3. [The Standard Tool Interface](#3-the-standard-tool-interface)
4. [Creating a New Tool](#4-creating-a-new-tool)
5. [Using Tools in Open WebUI](#5-using-tools-in-open-webui)
6. [Using Tools in Plain Python](#6-using-tools-in-plain-python)
7. [Using Tools with LangChain](#7-using-tools-with-langchain)
8. [Using Tools with OpenAI Function Calling](#8-using-tools-with-openai-function-calling)
9. [Adapting to Other Agent Frameworks](#9-adapting-to-other-agent-frameworks)

---

## 1. Architecture Overview

```
agents4gov-apps (pip package)
└── src/agents4gov_apps/
    ├── __init__.py          # Public API surface
    ├── protocol.py          # ToolSpecification metadata dataclass
    ├── registry.py          # Discovery: AVAILABLE_TOOLS, load_tool_class()
    └── <tool_group>/
        ├── __init__.py
        └── <tool_module>.py # One Tools class per file
```

**Key contracts:**

| Contract | Location | Purpose |
|----------|----------|---------|
| `ToolSpecification` | `protocol.py` | Import-agnostic metadata (key, path, deps) |
| `AVAILABLE_TOOLS` | `registry.py` | Registry dict keyed by stable string |
| `Tools` class | each tool module | The implementation unit |
| JSON string return | convention | Uniform output for any consumer |
| `Valves` inner class | optional convention | Runtime configuration injection |
| `__event_emitter__` | optional convention | Async progress callbacks |

The design goal is **platform agnosticism**: the library is a pure Python package and the caller decides how to adapt tool methods to their framework.

---

## 2. Best Practices Reference

The following conventions are enforced across all tools in this library. New tools must comply with all of them.

| Convention | Where enforced | Rationale |
|------------|---------------|-----------|
| Registry-based discovery via `AVAILABLE_TOOLS` | `registry.py` | Single source of truth; no filesystem scanning |
| Stable string registry keys | `registry.py` | Decouples callers from module import paths |
| `version` field on every `ToolSpecification` | `protocol.py` + `registry.py` | Allows programmatic version queries |
| `BaseTool` optional ABC in `protocol.py` | `protocol.py` | Formalises the contract; enables static type checking |
| One `Tools` class per module | every tool module | Registry and Open WebUI both expect exactly this |
| All public methods return `str` (JSON) | every tool module | LLM tool calls require strings; avoids serialization surprises |
| Error envelope `{"status": "error", "error_type": "...", "message": "..."}` | every tool module | Uniform error parsing for all callers |
| No bare exceptions raised from public methods | every tool module | Caller cannot safely catch framework-internal exceptions |
| `Valves` inner `BaseModel` on every tool | every tool module | Uniform configuration surface; Open WebUI renders it as a settings form |
| All external config in `Valves`, not `os.getenv` | every tool module | Testable, injectable, UI-configurable |
| Lazy imports of heavy optional dependencies | every tool module | Package stays importable without optional extras |
| `Pydantic Field` descriptors on all parameters | every tool module | Open WebUI reads these to auto-generate input forms |
| `src/` package layout | `pyproject.toml` | Prevents accidental imports of the uninstalled package |
| Optional dependency groups in `pyproject.toml` | `pyproject.toml` | Enables `pip install agents4gov-apps[openml]` partial installs |

---

## 3. The Standard Tool Interface

Every tool module must satisfy the contract below. Subclassing `BaseTool` is optional but recommended for static type checking — Open WebUI only cares that a class named `Tools` exists.

```python
# src/agents4gov_apps/<group>/<tool>.py

"""
title: Human-Readable Tool Name      # consumed by Open WebUI
author: agents4gov
description: One-sentence summary.
required_open_webui_version: 0.4.0   # minimum Open WebUI version
version: 1.0.0
licence: MIT
"""

import json
from agents4gov_apps import BaseTool
from pydantic import BaseModel, Field


class Tools(BaseTool):  # BaseTool is optional but documents the contract
    # --- Optional: runtime configuration ---
    class Valves(BaseModel):
        """Variables set by the administrator in Open WebUI or by the caller."""
        some_api_key: str = Field(default="", description="API key for the service")

    def __init__(self):
        self.valves = self.Valves()

    # --- Public tool method ---
    def my_tool_action(
        self,
        param_a: str = Field(..., description="Required parameter description"),
        param_b: int = Field(default=5, description="Optional parameter description"),
        # Optional: event emitter for async streaming progress
        __event_emitter__=None,
    ) -> str:
        """
        One-sentence summary of what this method does.

        Returns a JSON string with the result or an error envelope.

        Args:
            param_a: Description of param_a
            param_b: Description of param_b

        Returns:
            JSON string with {"status": "success", ...} or {"status": "error", ...}
        """
        try:
            # implementation
            result = {"status": "success", "data": {}}
            return json.dumps(result, ensure_ascii=False, indent=2)
        except SomeExpectedException as e:
            return json.dumps({
                "status": "error",
                "error_type": "some_expected_error",
                "message": str(e),
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({
                "status": "error",
                "error_type": "unexpected_error",
                "message": f"Unexpected error: {e}",
            }, ensure_ascii=False, indent=2)

    # --- Private helpers ---
    def _helper(self, value: str) -> str:
        return value.strip()
```

**Rules summary:**

| Rule | Rationale |
|------|-----------|
| One `Tools` class per module | Registry convention; Open WebUI expects exactly this |
| All public methods return `str` (JSON) | LLM tool calls work with strings; avoids serialization surprises |
| Error envelope: `{"status": "error", "error_type": "...", "message": "..."}` | Consistent parsing for callers |
| No bare exceptions raised from public methods | Caller cannot catch framework-internal errors safely |
| Private helpers prefixed with `_` | Open WebUI only exposes non-underscore methods as callable tools |
| Lazy imports of heavy dependencies | Package stays importable without optional extras |
| `Valves` for all external configuration | Allows Open WebUI UI injection and clean testability |

---

## 4. Creating a New Tool

### Step 1 — Create the subpackage

```
src/agents4gov_apps/my_service/
├── __init__.py          # empty or re-export Tools
└── my_action.py         # the tool module
```

### Step 2 — Write the module

Follow the template in Section 3. Pick a clear group name (e.g., `capes`, `sinaes`, `ibge`) and a descriptive module name.

### Step 3 — Add optional dependencies

In `pyproject.toml`:

```toml
[project.optional-dependencies]
my_service = [
  "requests",
  "some-library>=2.0"
]
```

### Step 4 — Register in the registry

In `src/agents4gov_apps/registry.py`, add to `AVAILABLE_TOOLS`:

```python
"my_service_action": ToolSpecification(
    key="my_service_action",
    import_path="agents4gov_apps.my_service.my_action",
    title="My Service Action",
    description="Does X for Y.",
    optional_dependencies=("some-library",),
),
```

### Step 5 — Document in TOOLS.md

Add a line under the relevant section in `TOOLS.md`.

### Step 6 — Write tests

```
tests/
└── test_my_service_action.py
```

```python
from agents4gov_apps import load_tool_class
import json

def test_my_action_success():
    Tools = load_tool_class("my_service_action")
    tool = Tools()
    raw = tool.my_tool_action(param_a="valid input")
    result = json.loads(raw)
    assert result["status"] == "success"

def test_my_action_error():
    Tools = load_tool_class("my_service_action")
    tool = Tools()
    raw = tool.my_tool_action(param_a="")
    result = json.loads(raw)
    assert result["status"] == "error"
```

---

## 5. Using Tools in Open WebUI

Open WebUI reads the `Tools` class directly from a Python file. Because the library is installed as a package, there are two integration paths.

### Option A — Paste the file directly (standalone)

Copy the content of any tool module (e.g., `open_alex_doi.py`) into Open WebUI's **Workspace → Tools → + Create Tool** editor. This works without installing the package.

Requirements for the pasted file to be recognized by Open WebUI:
- A `Tools` class at module level.
- Public methods with Pydantic `Field` descriptors (Open WebUI reads these for the UI form).
- Module-level docstring with `title:`, `description:`, `version:` metadata.

### Option B — Package-backed thin wrapper

Install the package in the Open WebUI environment, then create a thin wrapper that delegates to the registry:

```python
"""
title: OpenAlex DOI Metadata
author: agents4gov
description: Recupera metadados e indicadores de impacto via DOI.
required_open_webui_version: 0.4.0
version: 1.0.0
licence: MIT
"""

# This file lives in Open WebUI's tools directory or is pasted into the UI.
# The actual implementation is in the installed agents4gov-apps package.

from agents4gov_apps import load_tool_class as _load

_Impl = _load("openalex_doi")


class Tools(_Impl):
    """Thin Open WebUI wrapper — inherits everything from the package."""
    pass
```

This keeps the implementation in version-controlled source and avoids copy-paste drift.

### Async tools and event emitters

Tools with `__event_emitter__` can stream progress messages to the Open WebUI chat:

```python
async def validate_committee(self, student_json: str, members_json: str, __event_emitter__=None) -> str:
    if __event_emitter__:
        await __event_emitter__({"type": "status", "data": {"description": "Processing...", "done": False}})
    # ... work ...
    if __event_emitter__:
        await __event_emitter__({"type": "status", "data": {"description": "Done", "done": True}})
    return json.dumps(result)
```

Open WebUI will display these status messages as inline progress indicators.

### Valves configuration

When a tool has a `Valves` inner class, Open WebUI renders a settings form for administrators. Users can set API keys and model names through the UI without touching the code.

---

## 6. Using Tools in Plain Python

```python
from agents4gov_apps import load_tool_instance
import json

# Instantiate by registry key
tool = load_tool_instance("openalex_doi")

# Call the tool method directly
raw = tool.get_openalex_metadata_by_doi(doi="10.1371/journal.pone.0000000")
result = json.loads(raw)

if result["status"] == "success":
    print(result["metadata"]["title"])
else:
    print("Error:", result["message"])
```

For tools with `Valves`:

```python
from agents4gov_apps import load_tool_class
import os

Tools = load_tool_class("cnpq_lattes_collector")
tool = Tools()
tool.valves.openrouter_api_key = os.environ["OPENROUTER_API_KEY"]
tool.valves.model = "openai/gpt-4o-mini"
```

For async tools:

```python
import asyncio
from agents4gov_apps import load_tool_instance

tool = load_tool_instance("cnpq_lattes_navigator_coi")

async def run():
    raw = await tool.validate_committee(student_json="...", members_json="...")
    return raw

result = asyncio.run(run())
```

---

## 7. Using Tools with LangChain

LangChain expects tools that either subclass `BaseTool` or are decorated with `@tool`. Write a generic adapter:

```python
from langchain.tools import StructuredTool
from agents4gov_apps import load_tool_instance, iter_tool_specs
import json
import inspect


def agents4gov_to_langchain(key: str) -> StructuredTool:
    """Wrap an agents4gov tool as a LangChain StructuredTool."""
    instance = load_tool_instance(key)
    spec = None
    for s in iter_tool_specs():
        if s.key == key:
            spec = s
            break

    # Find the first non-private, non-dunder public method
    public_methods = [
        name for name, _ in inspect.getmembers(instance, predicate=inspect.ismethod)
        if not name.startswith("_")
    ]
    assert public_methods, f"No public methods found on tool '{key}'"
    method_name = public_methods[0]
    method = getattr(instance, method_name)

    def run_tool(**kwargs) -> str:
        raw = method(**kwargs)
        return raw  # already a JSON string — LangChain passes it to the LLM as-is

    # Build argument schema from Pydantic Fields on the method signature
    sig = inspect.signature(method)
    fields = {}
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "__event_emitter__"):
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        default = param.default if param.default != inspect.Parameter.empty else ...
        fields[param_name] = (annotation, default)

    from pydantic import create_model
    ArgsSchema = create_model(f"{key}_args", **fields)

    return StructuredTool.from_function(
        func=run_tool,
        name=spec.title if spec else key,
        description=spec.description if spec else "",
        args_schema=ArgsSchema,
    )


# Usage
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

tools = [
    agents4gov_to_langchain("openalex_doi"),
    agents4gov_to_langchain("openml_search"),
]

llm = ChatOpenAI(model="gpt-4o")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a research assistant."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
executor.invoke({"input": "Find datasets about climate change"})
```

---

## 8. Using Tools with OpenAI Function Calling

The OpenAI API accepts tools as JSON Schema definitions. Write a converter:

```python
import inspect
import json
from typing import get_type_hints
from agents4gov_apps import load_tool_instance, load_tool_class, iter_tool_specs
from pydantic.fields import FieldInfo


def agents4gov_to_openai_tool(key: str) -> dict:
    """Convert an agents4gov tool method to an OpenAI tool definition."""
    spec_map = {s.key: s for s in iter_tool_specs()}
    spec = spec_map[key]
    klass = load_tool_class(key)
    instance = klass()

    public_methods = [
        (name, getattr(instance, name))
        for name in dir(instance)
        if not name.startswith("_") and callable(getattr(instance, name))
    ]
    assert public_methods, f"No public methods on '{key}'"
    method_name, method = public_methods[0]

    sig = inspect.signature(method)
    parameters = {"type": "object", "properties": {}, "required": []}

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "__event_emitter__"):
            continue

        field_info = param.default if isinstance(param.default, FieldInfo) else None
        description = field_info.description if field_info else param_name
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str

        # Map Python types to JSON Schema types
        type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
        json_type = type_map.get(annotation, "string")

        parameters["properties"][param_name] = {
            "type": json_type,
            "description": description,
        }

        # Required if no default or default is PydanticUndefined
        has_default = field_info is not None and field_info.default is not None and str(field_info.default) != "PydanticUndefined"
        if not has_default and param.default is inspect.Parameter.empty:
            parameters["required"].append(param_name)

    return {
        "type": "function",
        "function": {
            "name": key,
            "description": spec.description,
            "parameters": parameters,
        },
    }


def dispatch_tool_call(key: str, arguments: str) -> str:
    """Execute a tool given its registry key and JSON arguments string."""
    instance = load_tool_instance(key)
    args = json.loads(arguments)
    public_methods = [
        (name, getattr(instance, name))
        for name in dir(instance)
        if not name.startswith("_") and callable(getattr(instance, name))
    ]
    _, method = public_methods[0]
    return method(**args)


# Usage example
from openai import OpenAI

client = OpenAI()
tool_keys = ["openalex_doi", "openml_search"]
openai_tools = [agents4gov_to_openai_tool(k) for k in tool_keys]

messages = [{"role": "user", "content": "Get metadata for DOI 10.1038/s41586-021-03819-2"}]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=openai_tools,
    tool_choice="auto",
)

# Handle tool calls
for tool_call in (response.choices[0].message.tool_calls or []):
    result = dispatch_tool_call(tool_call.function.name, tool_call.function.arguments)
    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
```

---

## 9. Adapting to Other Agent Frameworks

### Crew AI

```python
from crewai_tools import BaseTool as CrewBaseTool
from agents4gov_apps import load_tool_instance
import json


class OpenAlexDOITool(CrewBaseTool):
    name: str = "OpenAlex DOI Metadata"
    description: str = "Retrieves publication metadata and impact indicators by DOI."

    def _run(self, doi: str) -> str:
        tool = load_tool_instance("openalex_doi")
        return tool.get_openalex_metadata_by_doi(doi=doi)
```

### AutoGen / AG2

```python
from autogen import AssistantAgent, UserProxyAgent
from agents4gov_apps import load_tool_instance
import json

def get_openalex_metadata(doi: str) -> str:
    tool = load_tool_instance("openalex_doi")
    return tool.get_openalex_metadata_by_doi(doi=doi)

# Register as a function tool in AutoGen
assistant = AssistantAgent(
    name="ResearchAssistant",
    llm_config={
        "functions": [{
            "name": "get_openalex_metadata",
            "description": "Get publication metadata by DOI from OpenAlex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doi": {"type": "string", "description": "The publication DOI"}
                },
                "required": ["doi"]
            }
        }]
    }
)
```

### Generic adapter pattern

For any new framework, the pattern is always:

1. Instantiate with `load_tool_instance(key)`.
2. Identify the public method(s) using `inspect`.
3. Wrap the method in the framework's tool abstraction.
4. Pass JSON strings returned by the method back to the LLM.

