"""Adiciona auditoria somente leitura de raça/cor x comunidade tradicional.

Nenhum registro é migrado por este script.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "backend/routers/students.py"
UI = ROOT / "frontend/src/pages/StudentsComplete.js"
MATRIX = ROOT / "memory/audit/SGP_STUDENT_CANONICAL_MAPPING.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Trecho esperado não encontrado: {label}")
    return text.replace(old, new, 1)


router = ROUTER.read_text(encoding="utf-8")
audit_endpoint = '''    @router.get("/race-community-audit")
    async def get_race_community_audit(request: Request):
        """Auditoria somente leitura de raça/cor x comunidade tradicional.

        Não altera nem reinterpreta registros. O objetivo é medir o legado antes
        de estreitar o domínio de ``color_race`` e planejar revisão assistida.
        """
        current_user = await AuthMiddleware.require_roles(
            ['super_admin', 'admin', 'admin_teste', 'gerente', 'semed', 'semed1', 'semed2', 'semed3']
        )(request)
        current_db = get_db_for_user(current_user)

        from utils.student_demographics import audit_race_community_record

        base_filter = {}
        if current_user.get('role') != 'super_admin':
            tenant_id = current_user.get('mantenedora_id')
            if tenant_id:
                base_filter['mantenedora_id'] = tenant_id

        color_counts = {}
        community_counts = {}
        issue_counts = {}
        samples = []
        total_scanned = 0
        needs_review_total = 0

        projection = {
            "_id": 0,
            "id": 1,
            "full_name": 1,
            "school_id": 1,
            "color_race": 1,
            "comunidade_tradicional": 1,
        }
        cursor = current_db.students.find(base_filter, projection).sort("full_name", 1)
        async for student in cursor:
            total_scanned += 1
            color_key = student.get("color_race") or "__nao_informado__"
            community_key = student.get("comunidade_tradicional") or "__nao_informado__"
            color_counts[color_key] = color_counts.get(color_key, 0) + 1
            community_counts[community_key] = community_counts.get(community_key, 0) + 1

            audit = audit_race_community_record(student)
            if not audit["needs_review"]:
                continue

            needs_review_total += 1
            for issue in audit["issues"]:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

            if len(samples) < 100:
                samples.append({
                    "id": student.get("id"),
                    "full_name": student.get("full_name"),
                    "school_id": student.get("school_id"),
                    "color_race": audit["color_race"],
                    "comunidade_tradicional": audit["comunidade_tradicional"],
                    "issues": audit["issues"],
                })

        return {
            "mode": "read_only",
            "total_scanned": total_scanned,
            "needs_review_total": needs_review_total,
            "migration_ready": needs_review_total == 0,
            "color_race_counts": color_counts,
            "traditional_community_counts": community_counts,
            "issue_counts": issue_counts,
            "sample_limit": 100,
            "samples": samples,
        }

'''
anchor = '    @router.get("/inconsistencies")\n'
if audit_endpoint not in router:
    if anchor not in router:
        raise RuntimeError("Âncora /inconsistencies não encontrada")
    router = router.replace(anchor, audit_endpoint + anchor, 1)
ROUTER.write_text(router, encoding="utf-8")

ui = UI.read_text(encoding="utf-8")
benefits_anchor = """const BENEFITS_OPTIONS = [\n  'Bolsa Família',\n  'BPC - Benefício de Prestação Continuada',\n  'Auxílio Brasil',\n  'Programa de Erradicação do Trabalho Infantil (PETI)',\n  'Outros'\n];\n"""
legacy_constants = benefits_anchor + """\nconst LEGACY_RACE_LABELS = {\n  cigano: 'Cigano',\n  quilombola: 'Quilombola',\n  ribeirinho: 'Ribeirinho',\n  extrativista: 'Extrativista',\n};\n"""
ui = replace_once(ui, benefits_anchor, legacy_constants, "constantes de raça legado")
old_options = """            <option value=\"branca\">Branca</option>\n            <option value=\"preta\">Preta</option>\n            <option value=\"parda\">Parda</option>\n            <option value=\"amarela\">Amarela</option>\n            <option value=\"indigena\">Indígena</option>\n            <option value=\"cigano\">Cigano</option>\n            <option value=\"quilombola\">Quilombola</option>\n            <option value=\"ribeirinho\">Ribeirinho</option>\n            <option value=\"extrativista\">Extrativista</option>\n            <option value=\"nao_declarada\">Não Declarada</option>\n          </select>\n"""
new_options = """            <option value=\"branca\">Branca</option>\n            <option value=\"preta\">Preta</option>\n            <option value=\"parda\">Parda</option>\n            <option value=\"amarela\">Amarela</option>\n            <option value=\"indigena\">Indígena</option>\n            <option value=\"nao_declarada\">Não Declarada</option>\n            {LEGACY_RACE_LABELS[formData.color_race] && (\n              <option value={formData.color_race} disabled>\n                Legado: {LEGACY_RACE_LABELS[formData.color_race]} — revisar\n              </option>\n            )}\n          </select>\n          {LEGACY_RACE_LABELS[formData.color_race] && (\n            <p className=\"text-xs text-amber-700 mt-1\">\n              Este valor pertence a Comunidade Tradicional, não a Cor/Raça. Selecione a raça/cor correta e confira o campo ao lado.\n            </p>\n          )}\n"""
ui = replace_once(ui, old_options, new_options, "opções canônicas de raça/cor")
UI.write_text(ui, encoding="utf-8")

matrix = MATRIX.read_text(encoding="utf-8")
marker = "### 5.1 Raça/cor × comunidade tradicional\n\n"
addition = """### 5.1 Raça/cor × comunidade tradicional\n\n**Implementação de contenção:** novos cadastros deixam de oferecer `quilombola`, `cigano`, `ribeirinho` e `extrativista` como opções de raça/cor. Registros legados continuam legíveis e são sinalizados para revisão. O endpoint administrativo somente leitura `/students/race-community-audit` mede os registros afetados e conflitos antes de qualquer migração. Nenhuma correção automática de raça/cor é permitida, pois comunidade tradicional não permite inferir raça/cor.\n\n"""
matrix = replace_once(matrix, marker, addition, "decisão de auditoria demográfica")
MATRIX.write_text(matrix, encoding="utf-8")
