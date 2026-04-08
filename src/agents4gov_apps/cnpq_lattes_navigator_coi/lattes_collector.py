"""
title: Lattes Collector
author: agents4gov
description: Coleta dados do Lattes usando browser-use
required_open_webui_version: 0.4.0
requirements: browser-use, playwright, langchain-openai
version: 1.0.0
licence: MIT
"""

import json
import re
from datetime import datetime

from pydantic import BaseModel, Field

BROWSER_AVAILABLE = False
try:
    from browser_use import Agent, Browser

    BROWSER_AVAILABLE = True
except Exception:
    pass


class Tools:
    class Valves(BaseModel):
        openrouter_api_key: str = Field(
            "",
            description="OpenRouter API Key (https://openrouter.ai/keys)",
        )
        model: str = Field(
            "openrouter/auto",
            description="Modelo OpenRouter (ex: openrouter/auto, google/gemini-2.5-flash, openai/gpt-4o-mini)",
        )
        headless: bool = Field(
            True,
            description="Executar browser sem interface grafica",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _get_llm(self):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.valves.model,
            base_url="https://openrouter.ai/api/v1",
            api_key=self.valves.openrouter_api_key,
        )

    async def collect_lattes(self, name: str, lattes_id: str, is_student: bool = False, __event_emitter__=None) -> str:
        """
        Coleta dados do curriculo Lattes de um pesquisador.

        Args:
            name: Nome completo do pesquisador.
            lattes_id: ID Lattes de 16 digitos.
            is_student: Se True, usa a busca para demais pesquisadores.

        Returns:
            JSON string com os dados extraidos ou um erro estruturado.
        """
        if not BROWSER_AVAILABLE:
            return json.dumps({"status": "error", "error_type": "missing_dependency", "message": "browser-use nao instalado"})

        if not self.valves.openrouter_api_key:
            return json.dumps({"status": "error", "error_type": "missing_configuration", "message": "Configure openrouter_api_key nas Valves"})

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Buscando {name}...", "done": False}})

        try:
            result = await self._extract(name, lattes_id, is_student, __event_emitter__)

            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": "Coleta concluida", "done": True}})

            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Erro: {e}", "done": True}})
            return json.dumps({"status": "error", "error_type": "unexpected_error", "message": str(e)})

    async def _extract(self, name: str, lattes_id: str, is_student: bool, emitter=None):
        task = f"""
TASK: Coletar dados Lattes de "{name}" (ID: {lattes_id}).

Siga esta sequencia:
1. Acesse https://buscatextual.cnpq.br/buscatextual/busca.do?metodo=apresentar
2. Busque por "{name}"
3. {"Marque a opcao #buscarDemais e depois" if is_student else ""} clique em "#botaoBuscaFiltros"
4. Abra o resultado correspondente a "{name}"
5. Clique em "#idbtnabrircurriculo"
6. Confirme se o topo mostra exatamente o ID Lattes "{lattes_id}"

Extraia apenas informacoes recentes e relevantes: instituicoes, publicacoes, projetos, orientacoes e coautores.

Retorne JSON valido no formato:
{{"person": {{"name": "{name}", "lattes_id": "{lattes_id}"}}, "affiliations": [{{"institution": "..."}}], "publications": [{{"title": "...", "year": 2024, "coauthors": ["..."]}}], "projects": [{{"title": "..."}}], "advising": [{{"name": "...", "level": "PhD"}}], "coauthors": [{{"name": "...", "count": 1}}], "warnings": []}}
"""

        if emitter:
            await emitter({"type": "status", "data": {"description": f"Usando modelo: {self.valves.model}", "done": False}})

        browser = Browser(headless=self.valves.headless, disable_security=True)
        llm = self._get_llm()
        agent = Agent(task=task, llm=llm, browser=browser, max_actions_per_step=1)

        if emitter:
            await emitter({"type": "status", "data": {"description": "Navegando no Lattes...", "done": False}})

        history = await agent.run(max_steps=50)

        all_content = []
        if hasattr(history, 'all_results'):
            for r in history.all_results:
                if hasattr(r, 'extracted_content') and r.extracted_content:
                    all_content.append(str(r.extracted_content))
        if hasattr(history, 'final_result') and history.final_result:
            all_content.append(str(history.final_result))

        full_text = '\n'.join(all_content)

        json_block = re.search(r'```json\s*([\s\S]*?)\s*```', full_text)
        if json_block:
            try:
                return json.loads(json_block.group(1))
            except Exception:
                pass

        json_match = re.search(r'\{[\s\S]*\}', full_text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except Exception:
                pass

        return {"warnings": ["no_json_response"], "raw": full_text[:500]}
