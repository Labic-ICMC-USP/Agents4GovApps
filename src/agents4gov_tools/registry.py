"""Tool registry for agnostic discovery and import."""

from __future__ import annotations

from importlib import import_module

from .protocol import ToolSpecification


AVAILABLE_TOOLS: dict[str, ToolSpecification] = {
    "cnpq_lattes_navigator_coi": ToolSpecification(
        key="cnpq_lattes_navigator_coi",
        import_path="agents4gov_tools.cnpq_lattes_navigator_coi_tools.lattes_coi_judge",
        title="COI Validator",
        description="Analisa conflito de interesse entre aluno e membros da banca.",
        legacy_paths=("cnpq-lattes-navigator-coi-tools/lattes_coi_judge.py",),
        optional_dependencies=("browser-use", "playwright", "langchain-openai"),
    ),
    "cnpq_lattes_collector": ToolSpecification(
        key="cnpq_lattes_collector",
        import_path="agents4gov_tools.cnpq_lattes_navigator_coi_tools.lattes_collector",
        title="Lattes Collector",
        description="Coleta dados do Curriculo Lattes usando browser-use.",
        legacy_paths=("cnpq-lattes-navigator-coi-tools/lattes_collector.py",),
        optional_dependencies=("browser-use", "playwright", "langchain-openai"),
    ),
    "openalex_doi": ToolSpecification(
        key="openalex_doi",
        import_path="agents4gov_tools.openalex.open_alex_doi",
        title="OpenAlex DOI Metadata",
        description="Recupera metadados e indicadores de impacto para uma publicacao via DOI.",
        legacy_paths=("openalex/open_alex_doi.py",),
        optional_dependencies=("requests",),
    ),
    "openml_search": ToolSpecification(
        key="openml_search",
        import_path="agents4gov_tools.openml.openml_search",
        title="OpenML Dataset Search",
        description="Busca datasets do OpenML por similaridade semantica.",
        legacy_paths=("openml/openml_search.py",),
        optional_dependencies=("openml", "pandas", "numpy", "scikit-learn", "sentence-transformers"),
    ),
    "openml_download": ToolSpecification(
        key="openml_download",
        import_path="agents4gov_tools.openml.openml_download",
        title="OpenML Dataset Download",
        description="Baixa datasets do OpenML e salva como CSV.",
        legacy_paths=("openml/openml_download.py",),
        optional_dependencies=("openml", "pandas"),
    ),
    "openml_knn_train": ToolSpecification(
        key="openml_knn_train",
        import_path="agents4gov_tools.openml.openml_knn_train",
        title="OpenML KNN Trainer",
        description="Treina modelos KNN com validacao cruzada.",
        legacy_paths=("openml/openml_knn_train.py",),
        optional_dependencies=("openml", "pandas", "numpy", "scikit-learn", "joblib"),
    ),
}


def iter_tool_specs() -> tuple[ToolSpecification, ...]:
    """Return all known tool specifications."""

    return tuple(AVAILABLE_TOOLS.values())


def get_tool_spec(key: str) -> ToolSpecification:
    """Return a single tool specification by registry key."""

    return AVAILABLE_TOOLS[key]


def load_tool_class(key: str):
    """Import and return the tool class referenced by a registry key."""

    spec = get_tool_spec(key)
    module = import_module(spec.import_path)
    return getattr(module, spec.class_name)


def load_tool_instance(key: str, **kwargs):
    """Create a tool instance from the registry."""

    tool_class = load_tool_class(key)
    return tool_class(**kwargs)
