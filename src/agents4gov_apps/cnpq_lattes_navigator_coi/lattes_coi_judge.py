"""
title: COI Validator
author: agents4gov
description: Analisa conflito de interesse entre aluno e membros da banca
required_open_webui_version: 0.4.0
version: 1.0.0
licence: MIT
"""

import json
import re

from pydantic import BaseModel


class Tools:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()

    async def validate_coi(self, student_json: str, member_json: str, __event_emitter__=None) -> str:
        """
        Analisa conflito de interesse entre aluno e membro da banca.
        :param student_json: JSON do aluno (output do collector)
        :param member_json: JSON do membro da banca (output do collector)
        """
        try:
            student = json.loads(student_json)
            member = json.loads(member_json)

            conflicts = []

            # R1: Co-autoria
            s_pubs = [self._norm(p.get('title', '')) for p in student.get('publications', [])]
            m_pubs = [self._norm(p.get('title', '')) for p in member.get('publications', [])]
            shared = set(s_pubs) & set(m_pubs) - {''}
            if shared:
                conflicts.append({"rule": "R1", "desc": "Co-autoria", "evidence": list(shared)[:3]})

            # R1b: Coautor direto
            s_coauthors = [self._norm(c.get('name', '')) for c in student.get('coauthors', [])]
            m_name = self._norm(member.get('person', {}).get('name', '') or member.get('name', ''))
            if m_name and m_name in s_coauthors:
                conflicts.append({"rule": "R1b", "desc": "Coautor direto", "evidence": [m_name]})

            # R3: Mesma instituicao
            s_inst = [self._norm(a.get('institution', '')) for a in student.get('affiliations', [])]
            m_inst = [self._norm(a.get('institution', '')) for a in member.get('affiliations', [])]
            shared_inst = set(s_inst) & set(m_inst) - {''}
            if shared_inst:
                conflicts.append({"rule": "R3", "desc": "Mesma instituicao", "evidence": list(shared_inst)})

            # R4: Mesmo projeto
            s_proj = [self._norm(p.get('title', '')) for p in student.get('projects', [])]
            m_proj = [self._norm(p.get('title', '')) for p in member.get('projects', [])]
            shared_proj = set(s_proj) & set(m_proj) - {''}
            if shared_proj:
                conflicts.append({"rule": "R4", "desc": "Mesmo projeto", "evidence": list(shared_proj)[:3]})

            result = {
                "has_conflict": len(conflicts) > 0,
                "conflicts": conflicts,
                "summary": f"{len(conflicts)} conflito(s) detectado(s)" if conflicts else "Sem conflitos",
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({"error": f"JSON invalido: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def validate_committee(self, student_json: str, members_json: str, __event_emitter__=None) -> str:
        """
        Valida banca inteira: analisa aluno contra todos os membros.
        :param student_json: JSON do aluno
        :param members_json: JSON array dos membros: [{...}, {...}]
        """
        try:
            student = json.loads(student_json)
            members = json.loads(members_json)

            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Analisando {len(members)} membros...", "done": False}})

            all_conflicts = []
            for i, member in enumerate(members):
                member_name = member.get('person', {}).get('name', '') or member.get('name', f'Membro {i+1}')
                result = json.loads(await self.validate_coi(json.dumps(student), json.dumps(member)))

                if result.get('has_conflict'):
                    all_conflicts.append({
                        "member": member_name,
                        "conflicts": result['conflicts'],
                    })

            status = "invalid" if all_conflicts else "valid"
            summary = f"Banca {'INVALIDA' if all_conflicts else 'VALIDA'}. {len(all_conflicts)} membro(s) com conflito."

            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": summary, "done": True}})

            return json.dumps({
                "status": status,
                "conflicts": all_conflicts,
                "summary": summary,
            }, ensure_ascii=False, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({"error": f"JSON invalido: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _norm(self, s: str) -> str:
        if not s:
            return ""
        s = re.sub(r'\s+', ' ', s.lower().strip())
        for a, b in [('á', 'a'), ('à', 'a'), ('â', 'a'), ('ã', 'a'), ('é', 'e'), ('ê', 'e'), ('í', 'i'), ('ó', 'o'), ('ô', 'o'), ('õ', 'o'), ('ú', 'u'), ('ç', 'c')]:
            s = s.replace(a, b)
        return s
