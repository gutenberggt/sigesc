from pathlib import Path

PATH = Path('frontend/src/pages/StudentsComplete.js')
text = PATH.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: esperado 1 ocorrência, encontrado {count}')
    text = text.replace(old, new, 1)


replace_once(
    "import { computeCompleteness, completenessColor } from '@/utils/registrationCompleteness';\n",
    "import { computeCompleteness, completenessColor } from '@/utils/registrationCompleteness';\n"
    "import {\n"
    "  SPECIAL_EDUCATION_TARGET_OPTIONS,\n"
    "  LEARNING_DISORDER_OPTIONS,\n"
    "  OTHER_CONDITION_OPTIONS,\n"
    "  LEGACY_SPECIAL_EDUCATION_OPTIONS,\n"
    "  hasAeeTargetCondition,\n"
    "  getLegacySpecialEducationValues,\n"
    "  hasCondition,\n"
    "  toggleCondition,\n"
    "} from '@/utils/specialEducation';\n",
    'imports',
)

replace_once(
    "// Opções de deficiências/transtornos\n"
    "const DISABILITIES_OPTIONS = [\n"
    "  'Deficiência Física',\n"
    "  'Deficiência Intelectual',\n"
    "  'Deficiência Visual',\n"
    "  'Deficiência Auditiva',\n"
    "  'Deficiência Múltipla',\n"
    "  'Transtorno do Espectro Autista (TEA)',\n"
    "  'Altas Habilidades/Superdotação',\n"
    "  'Transtorno de Déficit de Atenção e Hiperatividade (TDAH)',\n"
    "  'Transtorno do Desenvolvimento da Linguagem (TDL)',\n"
    "  'Dislexia',\n"
    "  'Discalculia',\n"
    "  'Síndrome de Down'\n"
    "];\n\n",
    "",
    'remove-lista-mista',
)

old_checkbox_handler = """  const handleCheckboxChange = (field, value, checked) => {
    setFormData(prev => {
      const currentValues = prev[field] || [];
      if (checked) {
        return { ...prev, [field]: [...currentValues, value] };
      } else {
        return { ...prev, [field]: currentValues.filter(v => v !== value) };
      }
    });
  };
"""
new_checkbox_handler = old_checkbox_handler + """
  // Condições educacionais específicas usam normalização própria para manter
  // compatibilidade com grafias legadas sem duplicar valores no cadastro.
  const handleSpecialConditionChange = (option, checked) => {
    setFormData(prev => ({
      ...prev,
      disabilities: toggleCondition(prev.disabilities || [], option, checked),
    }));
  };
"""
replace_once(old_checkbox_handler, new_checkbox_handler, 'handler-condicoes')

old_program_logic = """  const programSchool = schools.find(s => s.id === formData.atendimento_programa_school_id);
  const availableProgramTypes = programSchool ? [
    ...(programSchool.aee ? [{ value: 'aee', label: 'Atendimento Educacional Especializado - AEE' }] : []),
    ...(programSchool.reforco_escolar ? [{ value: 'reforco_escolar', label: 'Reforço Escolar' }] : []),
    ...(programSchool.recomposicao_aprendizagem ? [{ value: 'recomposicao_aprendizagem', label: 'Recomposição da Aprendizagem' }] : []),
  ] : [];
"""
new_program_logic = """  const selectedSpecialConditions = formData.disabilities || [];
  const hasAeeTarget = formData.has_disability && hasAeeTargetCondition(selectedSpecialConditions);
  const legacySpecialEducationValues = getLegacySpecialEducationValues(selectedSpecialConditions);
  const currentAeeRequiresReview = formData.atendimento_programa_tipo === 'aee' && !hasAeeTarget;

  const programSchool = schools.find(s => s.id === formData.atendimento_programa_school_id);
  const availableProgramTypes = programSchool ? [
    ...(programSchool.aee && hasAeeTarget
      ? [{ value: 'aee', label: 'Atendimento Educacional Especializado - AEE' }]
      : []),
    ...(programSchool.reforco_escolar ? [{ value: 'reforco_escolar', label: 'Reforço Escolar' }] : []),
    ...(programSchool.recomposicao_aprendizagem ? [{ value: 'recomposicao_aprendizagem', label: 'Recomposição da Aprendizagem' }] : []),
  ] : [];
"""
replace_once(old_program_logic, new_program_logic, 'regra-programas')

old_mixed_ui = '''      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Deficiências / Transtornos</h3>
      <div className="flex items-center gap-2 mb-4">
        <input
          type="checkbox"
          id="has_disability"
          checked={formData.has_disability}
          onChange={(e) => updateFormData('has_disability', e.target.checked)}
          disabled={viewMode}
          className="h-4 w-4 text-blue-600 rounded"
        />
        <label htmlFor="has_disability" className="text-sm text-gray-700">Possui deficiência ou transtorno</label>
      </div>
      
      {formData.has_disability && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
            {DISABILITIES_OPTIONS.map(disability => (
              <label key={disability} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.disabilities.some(d => d.toLowerCase() === disability.toLowerCase())}
                  onChange={(e) => handleCheckboxChange('disabilities', disability, e.target.checked)}
                  disabled={viewMode}
                  className="h-4 w-4 text-blue-600 rounded"
                />
                <span className="text-sm text-gray-700">{disability}</span>
              </label>
            ))}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Detalhes / Necessidades Especiais</label>
            <SpellCheckTextarea
              value={formData.disability_details}
              onChange={(e) => updateFormData('disability_details', e.target.value)}
              disabled={viewMode}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              placeholder="Descreva detalhes sobre as necessidades especiais do aluno..."
            />
          </div>
        </>
      )}
'''
new_mixed_ui = '''      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Condições Educacionais Específicas</h3>
      <div className="flex items-start gap-2 mb-4">
        <input
          type="checkbox"
          id="has_disability"
          checked={formData.has_disability}
          onChange={(e) => updateFormData('has_disability', e.target.checked)}
          disabled={viewMode}
          className="h-4 w-4 mt-0.5 text-blue-600 rounded"
        />
        <div>
          <label htmlFor="has_disability" className="text-sm font-medium text-gray-700">
            Possui condição de Educação Especial, transtorno de aprendizagem ou outra condição relevante
          </label>
          <p className="text-xs text-gray-500 mt-1">
            As categorias abaixo são separadas para evitar que transtornos de aprendizagem sejam confundidos com o público da Educação Especial/AEE.
          </p>
        </div>
      </div>
      
      {formData.has_disability && (
        <div className="space-y-4">
          <section className="rounded-lg border border-blue-200 bg-blue-50/40 p-4" data-testid="special-education-target-section">
            <div className="mb-3">
              <h4 className="text-sm font-semibold text-blue-900">Público da Educação Especial / AEE</h4>
              <p className="text-xs text-blue-700 mt-1">
                Deficiências, Transtorno do Espectro Autista (TEA) e Altas Habilidades/Superdotação. A marcação identifica o público da Educação Especial; o atendimento AEE é vinculado separadamente conforme necessidade e oferta.
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {SPECIAL_EDUCATION_TARGET_OPTIONS.map(option => (
                <label key={option} className="flex items-start gap-2">
                  <input type="checkbox" checked={hasCondition(selectedSpecialConditions, option)} onChange={(e) => handleSpecialConditionChange(option, e.target.checked)} disabled={viewMode} className="h-4 w-4 mt-0.5 text-blue-600 rounded" />
                  <span className="text-sm text-gray-700">{option}</span>
                </label>
              ))}
            </div>
            {hasAeeTarget && (
              <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800" data-testid="aee-eligibility-indicator">
                <strong>✓ Público da Educação Especial identificado.</strong>{' '}O AEE pode ser vinculado conforme a necessidade educacional e a oferta da escola.
              </div>
            )}
            {legacySpecialEducationValues.length > 0 && (
              <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3" data-testid="legacy-special-education-warning">
                <p className="text-sm font-semibold text-amber-900">Cadastro legado — revisão recomendada</p>
                <p className="text-xs text-amber-800 mt-1">
                  O SIGESC preservou classificações antigas para não perder informação histórica. “Deficiência Visual” deve ser detalhada como Baixa Visão, Cegueira ou Visão Monocular, quando cabível. “Deficiência Múltipla” não é marcada manualmente no padrão atual do Censo Escolar; ela decorre da associação de duas ou mais deficiências.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
                  {LEGACY_SPECIAL_EDUCATION_OPTIONS.filter(option => legacySpecialEducationValues.includes(option)).map(option => (
                    <label key={option} className="flex items-center gap-2 text-sm text-amber-900">
                      <input type="checkbox" checked={hasCondition(selectedSpecialConditions, option)} onChange={(e) => handleSpecialConditionChange(option, e.target.checked)} disabled={viewMode} className="h-4 w-4 text-amber-600 rounded" />
                      <span>{option} <em className="text-xs">(legado)</em></span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="rounded-lg border border-slate-200 bg-slate-50/60 p-4" data-testid="learning-disorders-section">
            <div className="mb-3">
              <h4 className="text-sm font-semibold text-slate-900">Transtornos que impactam o desenvolvimento da aprendizagem</h4>
              <p className="text-xs text-slate-600 mt-1">Categorias coletadas pelo Censo Escolar desde 2025. Isoladamente, não caracterizam o estudante como público do AEE.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {LEARNING_DISORDER_OPTIONS.map(option => (
                <label key={option} className="flex items-start gap-2">
                  <input type="checkbox" checked={hasCondition(selectedSpecialConditions, option)} onChange={(e) => handleSpecialConditionChange(option, e.target.checked)} disabled={viewMode} className="h-4 w-4 mt-0.5 text-slate-600 rounded" />
                  <span className="text-sm text-gray-700">{option}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-gray-200 bg-white p-4" data-testid="other-conditions-section">
            <div className="mb-3">
              <h4 className="text-sm font-semibold text-gray-900">Outras condições relevantes ao acompanhamento pedagógico</h4>
              <p className="text-xs text-gray-600 mt-1">São registradas para acompanhamento, mas não constituem, por si só, categoria autônoma de deficiência, TEA ou Altas Habilidades/Superdotação no Censo Escolar.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {OTHER_CONDITION_OPTIONS.map(option => (
                <label key={option} className="flex items-start gap-2">
                  <input type="checkbox" checked={hasCondition(selectedSpecialConditions, option)} onChange={(e) => handleSpecialConditionChange(option, e.target.checked)} disabled={viewMode} className="h-4 w-4 mt-0.5 text-gray-600 rounded" />
                  <span className="text-sm text-gray-700">{option}</span>
                </label>
              ))}
            </div>
            {hasCondition(selectedSpecialConditions, 'Síndrome de Down') && (
              <p className="text-xs text-amber-700 mt-3">Síndrome de Down é registrada como condição. Para fins de Educação Especial/Censo, informe também a deficiência efetivamente apresentada pelo estudante, quando houver.</p>
            )}
          </section>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Detalhes / Necessidades Educacionais Específicas</label>
            <SpellCheckTextarea value={formData.disability_details} onChange={(e) => updateFormData('disability_details', e.target.value)} disabled={viewMode} rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Descreva necessidades educacionais, apoios, adaptações ou informações relevantes para o acompanhamento do aluno..." />
          </div>
        </div>
      )}
'''
replace_once(old_mixed_ui, new_mixed_ui, 'ui-condicoes')

replace_once(
    "      {/* Matrícula em Atendimento/Programa (apenas para alunos com deficiência) */}\n      {formData.has_disability && formData.disabilities && formData.disabilities.length > 0 && (\n",
    "      {/* Matrícula em Atendimento/Programa. AEE é liberado apenas para o público da Educação Especial. */}\n      {formData.has_disability && selectedSpecialConditions.length > 0 && (\n",
    'condicao-programa',
)

replace_once(
    "            Aluno(a) com deficiência/transtorno identificado. Selecione a escola que oferece o programa, o tipo de atendimento e a turma.\n",
    "            Selecione o atendimento disponível. O AEE só é oferecido como opção quando o cadastro contém condição do público da Educação Especial; transtornos de aprendizagem isolados não habilitam AEE.\n",
    'texto-programa',
)

replace_once(
    '''              >
                <option value="">{formData.atendimento_programa_school_id ? (availableProgramTypes.length > 0 ? 'Selecione o tipo' : 'Nenhum programa disponível') : 'Selecione a escola primeiro'}</option>
                {availableProgramTypes.map(tipo => (
''',
    '''              >
                {currentAeeRequiresReview && (
                  <option value="aee" disabled>AEE — vínculo existente requer revisão</option>
                )}
                <option value="">{formData.atendimento_programa_school_id ? (availableProgramTypes.length > 0 ? 'Selecione o tipo' : 'Nenhum programa disponível') : 'Selecione a escola primeiro'}</option>
                {availableProgramTypes.map(tipo => (
''',
    'preserva-aee-legado',
)

replace_once(
    '''              {formData.atendimento_programa_school_id && availableProgramTypes.length === 0 && (
                <p className="text-sm text-yellow-600 mt-1">Esta escola não possui programas de atendimento cadastrados.</p>
              )}
''',
    '''              {currentAeeRequiresReview && (
                <p className="text-sm text-amber-700 mt-1" data-testid="aee-link-review-warning">
                  O vínculo AEE existente foi preservado, mas o cadastro atual não contém condição que caracterize público da Educação Especial. Revise antes de alterar o atendimento.
                </p>
              )}
              {formData.atendimento_programa_school_id && availableProgramTypes.length === 0 && !currentAeeRequiresReview && (
                <p className="text-sm text-yellow-600 mt-1">Esta escola não possui programas de atendimento cadastrados compatíveis com este cadastro.</p>
              )}
''',
    'aviso-aee-legado',
)

replace_once(
    "                { key: 'has_disability', label: 'Deficiência/Transtorno' },\n",
    "                { key: 'has_disability', label: 'Condição educacional específica' },\n",
    'relatorio-label',
)

PATH.write_text(text, encoding='utf-8')
print('StudentsComplete.js atualizado com sucesso.')
