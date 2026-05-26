/**
 * StudentDependencySection — UI de Dependência de Estudos.
 *
 * Fase 1 [Fev/2026] — ver /app/docs/STUDENT_DEPENDENCY.md
 *
 * Renderiza:
 *   1. Radio: modo (none / with_dependency / dependency_only).
 *      → Visibilidade de cada opção depende das flags da mantenedora.
 *      → Mutuamente exclusivo (modelado como enum, sem estado inválido).
 *   2. Card resumido (ativas / concluídas / falhadas / limite).
 *   3. Lista de dependências ativas com botão "Remover".
 *   4. Form para vincular novo componente (turma + curso → cria registro).
 *
 * Props:
 *   studentId: id do aluno (obrigatório para CRUD; opcional em criação).
 *   value: dependency_mode atual ("none" | "with_dependency" | "dependency_only").
 *   onChange: (newMode) => void — chamado ao trocar o radio.
 *   mantenedoraConfig: { aprovacao_com_dependencia, max_componentes_dependencia,
 *                        cursar_apenas_dependencia, qtd_componentes_apenas_dependencia }
 *   readOnly: bool — modo somente leitura (visualização).
 */
import { useState, useEffect, useCallback } from 'react';
import { studentDependenciesAPI, classesAPI, schoolsAPI } from '@/services/api';
import { GraduationCap, Trash2, Plus, AlertCircle, CheckCircle2, X } from 'lucide-react';

const MODE_LABELS = {
  none: 'Sem dependência',
  with_dependency: 'Com dependência (aprovado parcialmente)',
  dependency_only: 'Apenas dependência (matrícula exclusiva)',
};

const STATUS_BADGE = {
  active: { label: 'Em andamento', className: 'bg-blue-100 text-blue-800' },
  completed: { label: 'Concluída', className: 'bg-green-100 text-green-800' },
  failed: { label: 'Reprovada', className: 'bg-red-100 text-red-800' },
  cancelled: { label: 'Cancelada', className: 'bg-gray-100 text-gray-800' },
};

export function StudentDependencySection({
  studentId,
  value = 'none',
  onChange,
  mantenedoraConfig = {},
  readOnly = false,
}) {
  const [summary, setSummary] = useState(null);
  const [deps, setDeps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [error, setError] = useState(null);

  const allowWith = !!mantenedoraConfig?.aprovacao_com_dependencia;
  const allowOnly = !!mantenedoraConfig?.cursar_apenas_dependencia;
  const sectionVisible = allowWith || allowOnly;

  const loadDeps = useCallback(async () => {
    if (!studentId) return;
    setLoading(true);
    try {
      const [list, sum] = await Promise.all([
        studentDependenciesAPI.listByStudent(studentId),
        studentDependenciesAPI.summary(studentId),
      ]);
      setDeps(list || []);
      setSummary(sum);
    } catch (e) {
      console.error('[StudentDependencySection] erro ao carregar:', e);
    } finally {
      setLoading(false);
    }
  }, [studentId]);

  useEffect(() => {
    loadDeps();
  }, [loadDeps]);

  if (!sectionVisible) {
    return null; // Mantenedora não habilitou nenhum modo — seção oculta.
  }

  const handleModeChange = (e) => {
    if (readOnly) return;
    const newMode = e.target.value;
    // [Fev/2026] Guard: alterar para 'none' com vínculos ativos exige confirmação.
    // Backend também valida (header X-Confirm-Cancel-Dependencies), aqui é UX.
    const activeCount = summary?.active || 0;
    if (newMode === 'none' && value !== 'none' && activeCount > 0) {
      const ok = window.confirm(
        `Atenção: o aluno possui ${activeCount} dependência(s) ativa(s). ` +
        `Mudar para "Sem dependência" cancelará automaticamente esses vínculos. Continuar?`
      );
      if (!ok) return;
    }
    onChange?.(newMode);
  };

  const handleDelete = async (depId) => {
    if (!window.confirm('Remover esta dependência? Esta ação não pode ser desfeita.')) return;
    try {
      await studentDependenciesAPI.delete(depId);
      await loadDeps();
    } catch (e) {
      setError(e.response?.data?.detail || 'Erro ao remover dependência.');
    }
  };

  return (
    <div data-testid="dependency-section" className="border border-amber-200 bg-amber-50 rounded-lg p-4 mt-4">
      <div className="flex items-center gap-2 mb-3">
        <GraduationCap className="text-amber-700" size={20} />
        <h3 className="text-sm font-semibold text-amber-900">Dependência de Estudos</h3>
      </div>

      {/* Radio de modo */}
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="dependency_mode"
            value="none"
            checked={value === 'none' || !value}
            onChange={handleModeChange}
            disabled={readOnly}
            data-testid="dep-mode-none"
          />
          <span>{MODE_LABELS.none}</span>
        </label>

        {allowWith && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="dependency_mode"
              value="with_dependency"
              checked={value === 'with_dependency'}
              onChange={handleModeChange}
              disabled={readOnly}
              data-testid="dep-mode-with"
            />
            <span>{MODE_LABELS.with_dependency}</span>
            {mantenedoraConfig.max_componentes_dependencia && (
              <span className="text-xs text-amber-700">
                (até {mantenedoraConfig.max_componentes_dependencia} componentes)
              </span>
            )}
          </label>
        )}

        {allowOnly && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="dependency_mode"
              value="dependency_only"
              checked={value === 'dependency_only'}
              onChange={handleModeChange}
              disabled={readOnly}
              data-testid="dep-mode-only"
            />
            <span>{MODE_LABELS.dependency_only}</span>
            {mantenedoraConfig.qtd_componentes_apenas_dependencia && (
              <span className="text-xs text-amber-700">
                (até {mantenedoraConfig.qtd_componentes_apenas_dependencia} componentes)
              </span>
            )}
          </label>
        )}
      </div>

      {/* Card resumo + lista — apenas se modo != none e aluno já existe */}
      {value && value !== 'none' && studentId && (
        <div className="mt-4 bg-white rounded-md border border-amber-200 p-3">
          {summary && (
            <div className="grid grid-cols-4 gap-2 mb-3 text-center text-xs">
              <div>
                <div className="font-bold text-blue-700">{summary.active}</div>
                <div className="text-gray-600">Ativas</div>
              </div>
              <div>
                <div className="font-bold text-green-700">{summary.completed}</div>
                <div className="text-gray-600">Concluídas</div>
              </div>
              <div>
                <div className="font-bold text-red-700">{summary.failed}</div>
                <div className="text-gray-600">Reprovadas</div>
              </div>
              <div>
                <div className="font-bold text-gray-700">{summary.limit ?? '—'}</div>
                <div className="text-gray-600">Limite</div>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-2 rounded mb-2 flex items-start gap-1">
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
              <button onClick={() => setError(null)} className="ml-auto"><X size={14} /></button>
            </div>
          )}

          {loading ? (
            <p className="text-xs text-gray-500 italic">Carregando…</p>
          ) : deps.length === 0 ? (
            <p className="text-xs text-gray-500 italic">Nenhuma dependência vinculada.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {deps.map((d) => {
                const badge = STATUS_BADGE[d.status] || STATUS_BADGE.active;
                return (
                  <li key={d.id} className="py-2 flex items-center gap-2 text-xs" data-testid={`dep-item-${d.id}`}>
                    <CheckCircle2 size={14} className="text-amber-600 flex-shrink-0" />
                    <div className="flex-1">
                      <div className="font-medium text-gray-900">
                        {d.course_name || d.course_id} — {d.class_name || d.class_id}
                      </div>
                      <div className="text-gray-500">
                        Origem: {d.origin_academic_year} • Cursando em {d.academic_year}
                      </div>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[10px] ${badge.className}`}>{badge.label}</span>
                    {!readOnly && (
                      <button
                        onClick={() => handleDelete(d.id)}
                        className="p-1 text-red-600 hover:bg-red-50 rounded"
                        title="Remover dependência"
                        data-testid={`dep-delete-${d.id}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          {!readOnly && (
            <button
              type="button"
              onClick={() => setShowAddForm(true)}
              className="mt-2 inline-flex items-center gap-1 px-3 py-1.5 bg-amber-600 text-white text-xs rounded hover:bg-amber-700"
              data-testid="dep-add-btn"
            >
              <Plus size={14} /> Vincular componente
            </button>
          )}
        </div>
      )}

      {showAddForm && (
        <AddDependencyModal
          studentId={studentId}
          schoolId={null /* será obtido do form pai via window quando refinarmos */}
          onClose={() => setShowAddForm(false)}
          onSaved={async () => {
            setShowAddForm(false);
            await loadDeps();
          }}
        />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------
// Modal de adicionar dependência
// ----------------------------------------------------------------------
// Heurística para identificar turmas de "anos finais" (6º ao 9º ano).
// Aceita variantes de cadastro: nivel_ensino canônico OU grade_level textual.
const ANOS_FINAIS_NIVEL = 'fundamental_anos_finais';
const ANOS_FINAIS_GRADE_REGEX = /\b(6º?\s?ano|7º?\s?ano|8º?\s?ano|9º?\s?ano|6\s?ano|7\s?ano|8\s?ano|9\s?ano)\b/i;

function isAnosFinaisClass(cls) {
  if (!cls) return false;
  const nivel = (cls.nivel_ensino || cls.education_level || '').toLowerCase();
  if (nivel === ANOS_FINAIS_NIVEL) return true;
  const gl = cls.grade_level || cls.name || '';
  return ANOS_FINAIS_GRADE_REGEX.test(String(gl));
}

function AddDependencyModal({ studentId, schoolId: schoolIdProp, onClose, onSaved }) {
  const [schools, setSchools] = useState([]);
  const [allClasses, setAllClasses] = useState([]);
  const [classCurriculum, setClassCurriculum] = useState(null); // resposta crua do /curriculum (com is_multi_grade/series)
  const [loadingCurriculum, setLoadingCurriculum] = useState(false);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedSeries, setSelectedSeries] = useState(''); // [Fev/2026] série da dependência (multisseriada)
  const [selectedCourse, setSelectedCourse] = useState('');
  const [originYear, setOriginYear] = useState(new Date().getFullYear() - 1);
  const [academicYear] = useState(new Date().getFullYear());
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [sc, cl] = await Promise.all([
          schoolsAPI.getAll(),
          classesAPI.getAll(),
        ]);
        setSchools(sc || []);
        setAllClasses(cl || []);
      } catch (e) {
        console.error('[AddDependencyModal] erro ao carregar:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Quando trocar a turma, busca a matriz curricular oficial dela
  // (class.course_ids ∪ teacher_assignments) via endpoint dedicado.
  useEffect(() => {
    if (!selectedClass) {
      setClassCurriculum(null);
      return;
    }
    let cancelled = false;
    setLoadingCurriculum(true);
    classesAPI.getCurriculum(selectedClass)
      .then((data) => {
        if (cancelled) return;
        setClassCurriculum(data || null);
      })
      .catch((e) => {
        if (cancelled) return;
        console.error('[AddDependencyModal] erro ao carregar currículo:', e);
        setClassCurriculum(null);
      })
      .finally(() => { if (!cancelled) setLoadingCurriculum(false); });
    return () => { cancelled = true; };
  }, [selectedClass]);

  // Turmas filtradas: só da escola selecionada + anos finais.
  // Dependência de estudos é regulamentada apenas para 6º–9º ano (fund. anos finais).
  const filteredClasses = selectedSchool
    ? allClasses.filter((c) => c.school_id === selectedSchool && isAnosFinaisClass(c))
    : [];

  // [Fev/2026] Detecção de multisseriada para mostrar seletor de série.
  // Considera multi APENAS quando is_multi_grade=true E series.length >= 2.
  // Multi com series=[única] cai no caminho normal (sem ambiguidade).
  const isMultiGradeWithChoice = !!(classCurriculum
    && classCurriculum.is_multi_grade
    && Array.isArray(classCurriculum.series)
    && classCurriculum.series.length >= 2);

  const allComponents = classCurriculum?.components || [];

  // Filtragem por série quando multisseriada:
  //   - componente com grade_levels vazio = aplica a todas → mantém
  //   - componente com grade_levels = ["6º Ano",...] → mostra só se inclui a série escolhida
  const filteredCourses = isMultiGradeWithChoice
    ? (selectedSeries
        ? allComponents.filter((c) =>
            !c.grade_levels || c.grade_levels.length === 0
            || c.grade_levels.includes(selectedSeries))
        : [] // sem série escolhida → não mostra componentes ainda
      )
    : allComponents;

  // Ao trocar de escola, limpa a turma selecionada para evitar estado inválido.
  const handleSchoolChange = (e) => {
    setSelectedSchool(e.target.value);
    setSelectedClass('');
    setSelectedSeries('');
    setSelectedCourse('');
  };

  // Ao trocar de turma, limpa série + componente.
  const handleClassChange = (e) => {
    setSelectedClass(e.target.value);
    setSelectedSeries('');
    setSelectedCourse('');
  };

  // Ao trocar de série (multisseriada), limpa componente (filtragem muda).
  const handleSeriesChange = (e) => {
    setSelectedSeries(e.target.value);
    setSelectedCourse('');
  };

  const handleSave = async () => {
    if (!selectedSchool || !selectedClass || !selectedCourse) {
      setError('Selecione escola, turma e componente.');
      return;
    }
    if (isMultiGradeWithChoice && !selectedSeries) {
      setError('Selecione a série da dependência (turma multisseriada).');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await studentDependenciesAPI.create({
        student_id: studentId,
        school_id: selectedSchool || schoolIdProp || '',
        class_id: selectedClass,
        course_id: selectedCourse,
        academic_year: academicYear,
        origin_academic_year: parseInt(originYear, 10),
        // [Fev/2026] Série da dependência só quando turma destino é multisseriada
        // com 2+ séries. Para turmas regulares fica null (backend infere por
        // classes.grade_level).
        target_series: isMultiGradeWithChoice ? selectedSeries : null,
      });
      await onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || 'Erro ao vincular dependência.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" data-testid="dep-add-modal">
      <div className="bg-white rounded-lg p-5 max-w-md w-full">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold">Vincular componente em dependência</h4>
          <button onClick={onClose}><X size={18} /></button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-2 rounded mb-3">{error}</div>
        )}

        <p className="text-[11px] text-gray-500 italic mb-3 leading-snug">
          A dependência funciona como uma matrícula nova em outra turma — possivelmente em
          outra escola e em turno diferente. Selecione primeiro a escola para listar as
          turmas disponíveis (apenas anos finais: 6º ao 9º ano).
        </p>

        <label className="block text-xs font-medium mb-1">Escola de destino</label>
        <select
          value={selectedSchool}
          onChange={handleSchoolChange}
          className="w-full border rounded p-2 text-sm mb-3"
          data-testid="dep-school-select"
          disabled={loading}
        >
          <option value="">{loading ? 'Carregando…' : '— Selecione —'}</option>
          {schools.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>

        <label className="block text-xs font-medium mb-1">Turma de destino</label>
        <select
          value={selectedClass}
          onChange={handleClassChange}
          className="w-full border rounded p-2 text-sm mb-1 disabled:bg-gray-50 disabled:text-gray-400"
          data-testid="dep-class-select"
          disabled={!selectedSchool}
        >
          <option value="">
            {!selectedSchool
              ? '— Selecione uma escola primeiro —'
              : filteredClasses.length === 0
                ? '— Sem turmas de anos finais nesta escola —'
                : '— Selecione —'}
          </option>
          {filteredClasses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}{c.shift ? ` · ${c.shift}` : ''}
            </option>
          ))}
        </select>
        {selectedSchool && filteredClasses.length > 0 && (
          <p className="text-[10px] text-gray-500 mb-3" data-testid="dep-class-hint">
            {filteredClasses.length} turma(s) dos anos finais nesta escola.
          </p>
        )}
        {selectedSchool && filteredClasses.length === 0 && (
          <p className="text-[10px] text-amber-700 mb-3" data-testid="dep-class-empty">
            Esta escola não possui turmas dos anos finais cadastradas.
          </p>
        )}

        {/* [Fev/2026] Seletor de Série da dependência — APENAS para turmas
            multisseriadas com 2+ séries. Para turmas regulares ou multi
            com series=[única] não aparece (sem ambiguidade). */}
        {isMultiGradeWithChoice && (
          <>
            <label className="block text-xs font-medium mb-1" data-testid="dep-series-label">
              Série da dependência
              <span className="ml-1 inline-block bg-amber-100 text-amber-800 text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wide">
                turma multisseriada
              </span>
            </label>
            <select
              value={selectedSeries}
              onChange={handleSeriesChange}
              className="w-full border rounded p-2 text-sm mb-1"
              data-testid="dep-series-select"
            >
              <option value="">— Selecione a série —</option>
              {classCurriculum.series.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <p className="text-[10px] text-amber-700 mb-3 italic" data-testid="dep-series-hint">
              Esta turma atende {classCurriculum.series.length} séries. A escolha
              filtra os componentes curriculares correspondentes àquela série.
            </p>
          </>
        )}

        <label className="block text-xs font-medium mb-1">Componente curricular</label>
        <select
          value={selectedCourse}
          onChange={(e) => setSelectedCourse(e.target.value)}
          className="w-full border rounded p-2 text-sm mb-1 disabled:bg-gray-50 disabled:text-gray-400"
          data-testid="dep-course-select"
          disabled={!selectedClass || loadingCurriculum
            || (isMultiGradeWithChoice && !selectedSeries)}
        >
          <option value="">
            {!selectedClass
              ? '— Selecione uma turma primeiro —'
              : (isMultiGradeWithChoice && !selectedSeries)
                ? '— Selecione a série primeiro —'
                : loadingCurriculum
                  ? 'Carregando matriz curricular…'
                  : filteredCourses.length === 0
                    ? '— Turma sem matriz curricular cadastrada —'
                  : '— Selecione —'}
          </option>
          {filteredCourses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        {selectedClass && !loadingCurriculum && filteredCourses.length > 0 && (
          <p className="text-[10px] text-gray-500 mb-3" data-testid="dep-course-hint">
            {filteredCourses.length} componente(s) {isMultiGradeWithChoice ? `da série ${selectedSeries} ` : ''}vinculado(s) a esta turma.
          </p>
        )}
        {selectedClass && !loadingCurriculum && filteredCourses.length === 0
          && !(isMultiGradeWithChoice && !selectedSeries) && (
          <p className="text-[10px] text-amber-700 mb-3" data-testid="dep-course-empty">
            {isMultiGradeWithChoice
              ? `Nenhum componente da série ${selectedSeries} vinculado a esta turma. Cadastre a matriz curricular antes de vincular dependência.`
              : 'A turma selecionada não tem componentes curriculares cadastrados (nem em matriz própria, nem via vínculo de professores). Cadastre a matriz curricular antes de vincular dependência.'}
          </p>
        )}

        <label className="block text-xs font-medium mb-1 text-gray-500">
          Ano de origem (em que reprovou)
        </label>
        <input
          type="number"
          value={originYear}
          onChange={(e) => setOriginYear(e.target.value)}
          className="w-full border rounded p-2 text-sm mb-1 bg-gray-50 text-gray-500 cursor-not-allowed"
          min="2000"
          max={academicYear}
          data-testid="dep-origin-year"
          disabled
        />
        <p className="text-[10px] text-gray-500 mb-4 italic" data-testid="dep-origin-year-hint">
          Preenchido automaticamente com o ano anterior. Histórico do componente reprovado
          é mantido apenas para registro — não interfere na busca do aluno.
        </p>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50"
            disabled={saving}
          >Cancelar</button>
          <button
            onClick={handleSave}
            disabled={saving || !selectedSchool || !selectedClass || !selectedCourse
              || (isMultiGradeWithChoice && !selectedSeries)}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50"
            data-testid="dep-save-btn"
          >{saving ? 'Salvando…' : 'Vincular'}</button>
        </div>
      </div>
    </div>
  );
}

export default StudentDependencySection;
