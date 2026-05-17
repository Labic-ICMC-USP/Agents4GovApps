"""Tool registry for agnostic discovery and import."""

from __future__ import annotations

from importlib import import_module

from .protocol import ToolSpecification


AVAILABLE_TOOLS: dict[str, ToolSpecification] = {
    "cnpq_lattes_navigator_coi": ToolSpecification(
        key="cnpq_lattes_navigator_coi",
        import_path="agents4gov_apps.cnpq_lattes_navigator_coi.lattes_coi_judge",
        title="COI Validator",
        description="Analisa conflito de interesse entre aluno e membros da banca.",
        version="1.0.0",
        optional_dependencies=("browser-use", "playwright", "langchain-openai"),
    ),
    "cnpq_lattes_collector": ToolSpecification(
        key="cnpq_lattes_collector",
        import_path="agents4gov_apps.cnpq_lattes_navigator_coi.lattes_collector",
        title="Lattes Collector",
        description="Coleta dados do Curriculo Lattes usando browser-use.",
        version="1.0.0",
        optional_dependencies=("browser-use", "playwright", "langchain-openai"),
    ),
    "gnews_collector": ToolSpecification(
        key="gnews_collector",
        import_path="agents4gov_apps.gnews_collector.gnews_collector",
        title="GNews Collector",
        description="Coleta noticias do Google News com janelas trimestrais automaticas para superar o limite de 100 resultados por consulta.",
        version="1.0.0",
        optional_dependencies=("gnews", "pandas", "pyarrow", "python-dateutil"),
    ),
    "openalex_doi": ToolSpecification(
        key="openalex_doi",
        import_path="agents4gov_apps.openalex.open_alex_doi",
        title="OpenAlex DOI Metadata",
        description="Recupera metadados e indicadores de impacto para uma publicacao via DOI.",
        version="1.0.0",
    ),
    "openml_search": ToolSpecification(
        key="openml_search",
        import_path="agents4gov_apps.openml.openml_search",
        title="OpenML Dataset Search",
        description="Busca datasets do OpenML por similaridade semantica.",
        version="1.0.0",
        optional_dependencies=("openml", "pandas", "numpy", "scikit-learn", "sentence-transformers"),
    ),
    "openml_download": ToolSpecification(
        key="openml_download",
        import_path="agents4gov_apps.openml.openml_download",
        title="OpenML Dataset Download",
        description="Baixa datasets do OpenML e salva como CSV.",
        version="1.0.0",
        optional_dependencies=("openml", "pandas"),
    ),
    "openml_knn_train": ToolSpecification(
        key="openml_knn_train",
        import_path="agents4gov_apps.openml.openml_knn_train",
        title="OpenML KNN Trainer",
        description="Treina modelos KNN com validacao cruzada.",
        version="1.0.0",
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
