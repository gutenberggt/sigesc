"""P0-F6.2 — interface humana para a estação privada de adjudicação P0-F6.

Esta camada reutiliza integralmente o P0-F6.1 e altera somente a apresentação do
HTML gerado. Os códigos técnicos, review_unit_id e valores de decisão continuam
inalterados no contrato exportado; a tela passa a exibir rótulos humanos e neutros.

Nenhum acesso a banco de dados é realizado.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

HOTFIX_PATH = Path(__file__).resolve().with_name(
    "build_p0f6_private_human_adjudication_station_hotfix.py"
)

spec = importlib.util.spec_from_file_location("p0f6_hotfix", HOTFIX_PATH)
if not spec or not spec.loader:
    raise RuntimeError("P0F6_HOTFIX_IMPORT_FAILED")
hotfix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hotfix)

P0F5_PHASE = hotfix.P0F5_PHASE
STATION_PHASE = hotfix.STATION_PHASE
RAW_DECISION_PHASE = hotfix.RAW_DECISION_PHASE
SEALED_DECISION_PHASE = hotfix.SEALED_DECISION_PHASE
MANIFEST_VERSION = hotfix.MANIFEST_VERSION
ALLOWED_DECISIONS = hotfix.ALLOWED_DECISIONS
HUMAN_UI_PHASE = "P0F6.2-HUMAN-READABLE-ADJUDICATION-UI-2026"

canonical_sha256 = hotfix.canonical_sha256
validate_p0f5_packet = hotfix.validate_p0f5_packet
validate_raw_decisions = hotfix.validate_raw_decisions
seal_decisions = hotfix.seal_decisions


def _replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"P0F6_2_UI_PATTERN_{label}_COUNT:{count}")
    return text.replace(old, new, 1)


def humanize_generated_html(html_text: str) -> str:
    """Humaniza apenas a apresentação, preservando o contrato técnico interno."""
    prelude_old = "const pretty=v=>JSON.stringify(v,null,2);"
    prelude_new = r"""const pretty=v=>JSON.stringify(v,null,2);
const COLLECTION_LABELS={
  attendance:'Frequência',
  grades:'Notas',
  learning_objects:'Conteúdo pedagógico'
};
const UNIT_TYPE_LABELS={
  ATTENDANCE_STUDENT_DECISION:'Divergência de frequência',
  GRADE_FIELD_DECISION:'Divergência em nota',
  PEDAGOGICAL_CONTENT_FIELD_DECISION:'Divergência em conteúdo pedagógico'
};
const FIELD_LABELS={
  methodology:'Metodologia',
  content:'Conteúdo da aula',
  observations:'Observações',
  resources:'Recursos utilizados',
  number_of_classes:'Quantidade de aulas',
  skill_codigos:'Habilidades trabalhadas',
  adaptation_ids:'Adaptações pedagógicas',
  evidencia_aprendizagem:'Evidência de aprendizagem',
  pratica_pedagogica:'Prática pedagógica',
  dependency_id:'Dependência curricular',
  b1:'Nota do 1º bimestre',
  b2:'Nota do 2º bimestre',
  b3:'Nota do 3º bimestre',
  b4:'Nota do 4º bimestre',
  rec_s1:'Recuperação do 1º semestre',
  rec_s2:'Recuperação do 2º semestre',
  recovery:'Recuperação final',
  'records.status_or_dependency_id':'Situação de frequência do estudante'
};
const STATUS_LABELS={
  present:'Presente',
  absent:'Ausente',
  justified:'Falta justificada',
  excused:'Falta justificada',
  late:'Atraso'
};
const PERIOD_LABELS={regular:'Regular'};
const labelCollection=v=>COLLECTION_LABELS[v]||v||'Registro';
const labelUnitType=v=>UNIT_TYPE_LABELS[v]||'Divergência que exige decisão';
const labelField=v=>FIELD_LABELS[v]||String(v||'Informação divergente').replaceAll('_',' ');
const formatDate=v=>{
  const s=String(v||'');
  const m=s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m?`${m[3]}/${m[2]}/${m[1]}`:s;
};
const humanScalar=v=>{
  if(v===null||v===undefined||v==='')return 'Não informado';
  if(typeof v==='boolean')return v?'Sim':'Não';
  if(Array.isArray(v))return v.length?v.map(humanScalar).join('; '):'Nenhum';
  if(typeof v==='object'){
    const parts=[];
    for(const [k,val] of Object.entries(v)){
      if(k==='status')parts.push('Situação: '+(STATUS_LABELS[val]||humanScalar(val)));
      else if(k==='dependency_id'&&val)parts.push('Dependência curricular registrada');
      else if(k==='name'&&val)parts.push(String(val));
    }
    return parts.length?parts.join(' · '):JSON.stringify(v,null,2);
  }
  return String(v);
};
const humanValue=(v,field)=>{
  if(field==='records.status_or_dependency_id'){
    const rows=Array.isArray(v)?v:[v];
    return rows.map(humanScalar).join('\n');
  }
  return humanScalar(v);
};
const humanContext=ctx=>{
  const c=ctx||{};
  const rows=[];
  if(c.school_name)rows.push('Escola: '+c.school_name);
  if(c.class_name)rows.push('Turma: '+c.class_name);
  if(c.academic_year)rows.push('Ano letivo: '+c.academic_year);
  if(c.date)rows.push('Data: '+formatDate(c.date));
  if(c.period)rows.push('Período: '+(PERIOD_LABELS[c.period]||c.period));
  if(c.aula_numero!==null&&c.aula_numero!==undefined&&c.aula_numero!=='')rows.push('Aula: '+c.aula_numero);
  if(c.student_name)rows.push('Estudante: '+c.student_name);
  return rows.length?rows.join('\n'):'Contexto não informado';
};
const actorText=actor=>{
  const a=actor||{};
  const candidate=a.recorded_by||a.created_by||a.updated_by||a;
  if(candidate&&typeof candidate==='object'&&candidate.name)return candidate.name;
  if(a.name)return a.name;
  return 'Autoria não identificada';
};"""

    text = _replace_exact(html_text, prelude_old, prelude_new, "PRELUDE")

    replacements = (
        ('<div><label>Grupo</label>', '<div><label>Componente curricular</label>', 'GROUP_LABEL'),
        ('<div><label>Coleção</label>', '<div><label>Tipo de registro</label>', 'COLLECTION_LABEL'),
        ('${esc(row.collection)}', '${esc(labelCollection(row.collection))}', 'COLLECTION_PILL'),
        ('${esc(u.unit_type)}', '${esc(labelUnitType(u.unit_type))}', 'UNIT_TYPE_PILL'),
        ('${esc(u.field_name||u.unit_type)}', '${esc(labelField(u.field_name||u.unit_type))}', 'FIELD_TITLE'),
        ('${esc(pretty(u.context||{}))}', '${esc(humanContext(u.context||{}))}', 'CONTEXT'),
        ('<strong>Origem/autoria SOURCE</strong><pre>${esc(pretty(u.source_actor||{}))}</pre>', '<strong>Quem registrou — Registro 1</strong><pre>${esc(actorText(u.source_actor||{}))}</pre>', 'SOURCE_ACTOR'),
        ('<strong>Origem/autoria TARGET</strong><pre>${esc(pretty(u.target_actor||{}))}</pre>', '<strong>Quem registrou — Registro 2</strong><pre>${esc(actorText(u.target_actor||{}))}</pre>', 'TARGET_ACTOR'),
        ('<strong>Valor SOURCE</strong><pre>${esc(pretty(u.source_value))}</pre>', '<strong>Registro 1</strong><pre>${esc(humanValue(u.source_value,u.field_name))}</pre>', 'SOURCE_VALUE'),
        ('<strong>Valor TARGET</strong><pre>${esc(pretty(u.target_value))}</pre>', '<strong>Registro 2</strong><pre>${esc(humanValue(u.target_value,u.field_name))}</pre>', 'TARGET_VALUE'),
        ('>Manter SOURCE</button>', '>Manter Registro 1</button>', 'SOURCE_BUTTON'),
        ('>Manter TARGET</button>', '>Manter Registro 2</button>', 'TARGET_BUTTON'),
        ('>Reconciliação manual</button>', '>Conciliar manualmente</button>', 'MANUAL_BUTTON'),
        ('placeholder="Obrigatória para Reconciliação manual; recomendada nos demais casos."', 'placeholder="Obrigatória para conciliação manual; recomendada nos demais casos."', 'NOTE_PLACEHOLDER'),
        ('<div class="muted">review_unit_id: ${esc(id)}</div>', '<details class="muted"><summary>Detalhes técnicos</summary><div>Identificador da decisão: ${esc(id)}</div></details>', 'TECHNICAL_ID'),
        ("o.textContent=v;document.getElementById('filterCollection').appendChild(o)", "o.textContent=labelCollection(v);document.getElementById('filterCollection').appendChild(o)", 'COLLECTION_FILTER'),
    )

    for old, new, label in replacements:
        text = _replace_exact(text, old, new, label)

    governance_old = (
        '<strong>Regra de governança:</strong> esta tela apenas registra decisões de um responsável autorizado. '
        'Ela não recomenda qual lado deve prevalecer e não altera o banco de dados.'
    )
    governance_new = governance_old + (
        '<br><span class="muted"><strong>Registro 1 e Registro 2 são rótulos neutros.</strong> '
        'Nenhum deles significa automaticamente certo, errado, mais novo ou mais antigo.</span>'
    )
    text = _replace_exact(text, governance_old, governance_new, "GOVERNANCE_HELP")

    return text


def build_station(packet_path: Path, output_path: Path) -> dict[str, Any]:
    result = hotfix.build_station(packet_path, output_path)
    html_text = output_path.read_text(encoding="utf-8")
    human_text = humanize_generated_html(html_text)
    hotfix.base.private_write_text(output_path, human_text)
    result = dict(result)
    result.update(
        {
            "human_ui_phase": HUMAN_UI_PHASE,
            "human_readable_ui": True,
            "neutral_record_labels": True,
            "technical_contract_preserved": True,
            "database_mutation": False,
        }
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="P0-F6.2 interface humana para adjudicação offline"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Gerar estação P0-F6 com linguagem humana")
    build.add_argument("--packet", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)

    seal = sub.add_parser("seal", help="Delegar selagem ao contrato P0-F6 original")
    seal.add_argument("--packet", required=True, type=Path)
    seal.add_argument("--decisions", required=True, type=Path)
    seal.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "build":
        result = build_station(args.packet, args.output)
    else:
        result = hotfix.seal_decisions(args.packet, args.decisions, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
