import { useEffect, useMemo, useState } from 'react';
import { UserCog, Calendar, Check, AlertTriangle, Plus, Minus, GraduationCap, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { teacherAssignmentAPI, classesAPI } from '@/services/api';
import { toast } from 'sonner';

/**
 * Seção "+ Adicionar Nova Substituição".
 *
 * Recebe do pai o professor substituto já selecionado (alocacaoForm.staff_id) e os dados de
 * referência (escolas, turmas, componentes, alocações existentes) para inferir o regente
 * automaticamente para cada combinação (turma × componente).
 *
 * [Fev/2026] Paridade com "Adicionar Nova Alocação": suporta MÚLTIPLAS turmas e MÚLTIPLOS
 * componentes por turma (cartesian product). Ao salvar, chama a API uma vez por combinação.
 *  - Escola: usa `professorSchools` (apenas lotações ativas). Sem lotação → alerta amarelo.
 *  - Turmas: multi-add com botão `+`. Filtradas pela escola + ano letivo.
 *  - Componentes: multi-add com botão `+` (habilitado após 1+ turma). Dedupe remove aqueles
 *    já alocados ao substituto em QUALQUER uma das turmas selecionadas.
 *  - CH semanal: auto-detectada por combinação a partir do regente; override manual aplica-se
 *    a todas as combinações.
 */
export const SubstituicaoSection = ({
  alocacaoForm,
  professorSchools,
  filteredClasses: _filteredClassesIgnored,
  courses,
  staffList,
  existingAlocacoes,
  schools: _schoolsIgnored,
  onSaved,
}) => {
  const [schoolId, setSchoolId] = useState('');

  // Multi-select: turmas e componentes escolhidos
  const [selectedTurmas, setSelectedTurmas] = useState([]);       // [{id, name, education_level}]
  const [selectedComponentes, setSelectedComponentes] = useState([]); // [{id, name, workload}]
  const [currentTurma, setCurrentTurma] = useState('');
  const [currentComponente, setCurrentComponente] = useState('');

  const [dataInicio, setDataInicio] = useState(new Date().toISOString().slice(0, 10));
  const [dataFim, setDataFim] = useState('');
  const [cargaHorariaOverride, setCargaHorariaOverride] = useState('');
  const [saving, setSaving] = useState(false);

  // Turmas da escola (fetch por escola)
  const [turmasDaEscola, setTurmasDaEscola] = useState([]);
  const [loadingTurmas, setLoadingTurmas] = useState(false);

  useEffect(() => {
    if (!schoolId) {
      setTurmasDaEscola([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingTurmas(true);
      try {
        const data = await classesAPI.list(schoolId);
        if (!cancelled) {
          const year = alocacaoForm.academic_year || new Date().getFullYear();
          const filtered = (Array.isArray(data) ? data : []).filter(c =>
            !c.academic_year || c.academic_year === year
          );
          setTurmasDaEscola(filtered);
        }
      } catch (e) {
        if (!cancelled) {
          setTurmasDaEscola([]);
          toast.error('Erro ao carregar turmas desta escola');
        }
      } finally {
        if (!cancelled) setLoadingTurmas(false);
      }
    })();
    return () => { cancelled = true; };
  }, [schoolId, alocacaoForm.academic_year]);

  // Reset seleções quando escola muda
  useEffect(() => {
    setSelectedTurmas([]);
    setSelectedComponentes([]);
    setCurrentTurma('');
    setCurrentComponente('');
  }, [schoolId]);

  // Nível de ensino comum das turmas selecionadas (se todas compartilham o mesmo)
  const nivelEnsinoComum = useMemo(() => {
    const niveis = new Set(
      selectedTurmas.map(t => t.education_level || t.nivel_ensino).filter(Boolean)
    );
    return niveis.size === 1 ? Array.from(niveis)[0] : null;
  }, [selectedTurmas]);

  // Componentes disponíveis: filtra por nível + dedupe (já alocados ao substituto em QUALQUER turma selecionada)
  const componentesDisponiveis = useMemo(() => {
    if (selectedTurmas.length === 0) return [];

    let lista = courses || [];
    if (nivelEnsinoComum) {
      lista = lista.filter(c => !c.nivel_ensino || c.nivel_ensino === nivelEnsinoComum);
    }
    // Dedupe: remove componentes já alocados ao substituto em qualquer uma das turmas escolhidas
    const turmasIds = new Set(selectedTurmas.map(t => t.id));
    const jaAlocadosIds = new Set(
      (existingAlocacoes || [])
        .filter(a =>
          a.staff_id === alocacaoForm.staff_id &&
          turmasIds.has(a.class_id) &&
          a.status === 'ativo'
        )
        .map(a => a.course_id)
    );
    return lista
      .filter(c => !jaAlocadosIds.has(c.id))
      .filter(c => !selectedComponentes.find(sc => sc.id === c.id));
  }, [selectedTurmas, courses, nivelEnsinoComum, existingAlocacoes, alocacaoForm.staff_id, selectedComponentes]);

  // Turmas disponíveis para adicionar (as que ainda não foram adicionadas)
  const turmasDisponiveis = useMemo(() => {
    const addedIds = new Set(selectedTurmas.map(t => t.id));
    return turmasDaEscola.filter(t => !addedIds.has(t.id));
  }, [turmasDaEscola, selectedTurmas]);

  // Monta combinações (turma × componente) com regente detectado e CH
  const combinacoes = useMemo(() => {
    const out = [];
    for (const t of selectedTurmas) {
      for (const c of selectedComponentes) {
        const regenteAssign = (existingAlocacoes || []).find(a =>
          a.class_id === t.id &&
          a.course_id === c.id &&
          a.status === 'ativo' &&
          !a.is_substituicao &&
          a.staff_id !== alocacaoForm.staff_id
        );
        const regenteStaff = regenteAssign
          ? (staffList || []).find(s => s.id === regenteAssign.staff_id)
          : null;
        out.push({
          turma: t,
          componente: c,
          regenteAssign,
          regenteLabel: regenteStaff
            ? `${regenteStaff.nome} (${regenteStaff.matricula})`
            : (regenteAssign ? 'Regente não identificado' : 'Sem regente ativo'),
          chAuto: regenteAssign?.carga_horaria_semanal || null,
        });
      }
    }
    return out;
  }, [selectedTurmas, selectedComponentes, existingAlocacoes, staffList, alocacaoForm.staff_id]);

  // CH total estimada (auto) vs override manual
  const chOverrideNum = cargaHorariaOverride !== '' ? parseInt(cargaHorariaOverride, 10) : null;
  const chTotalEstimada = useMemo(() => {
    if (chOverrideNum !== null && !Number.isNaN(chOverrideNum)) {
      return chOverrideNum * combinacoes.length;
    }
    return combinacoes.reduce((acc, k) => acc + (k.chAuto || 0), 0);
  }, [chOverrideNum, combinacoes]);

  const handleAddTurma = () => {
    if (!currentTurma) return;
    const turma = turmasDaEscola.find(t => t.id === currentTurma);
    if (!turma) return;
    setSelectedTurmas(prev => [...prev, turma]);
    setCurrentTurma('');
    // Reset de componentes se nível mudar
    const novoNivel = turma.education_level || turma.nivel_ensino;
    if (selectedComponentes.length > 0 && nivelEnsinoComum && novoNivel && nivelEnsinoComum !== novoNivel) {
      setSelectedComponentes([]);
      toast.info('Componentes resetados: turma de nível de ensino diferente.');
    }
  };

  const handleRemoveTurma = (turmaId) => {
    setSelectedTurmas(prev => prev.filter(t => t.id !== turmaId));
  };

  const handleAddComponente = () => {
    if (!currentComponente) return;
    if (currentComponente === 'TODOS') {
      setSelectedComponentes(prev => [...prev, ...componentesDisponiveis]);
      setCurrentComponente('');
      return;
    }
    const comp = componentesDisponiveis.find(c => c.id === currentComponente);
    if (!comp) return;
    setSelectedComponentes(prev => [...prev, comp]);
    setCurrentComponente('');
  };

  const handleRemoveComponente = (compId) => {
    setSelectedComponentes(prev => prev.filter(c => c.id !== compId));
  };

  const canSave = (
    alocacaoForm.staff_id &&
    schoolId &&
    selectedTurmas.length > 0 &&
    selectedComponentes.length > 0 &&
    dataInicio &&
    combinacoes.every(k => chOverrideNum !== null || k.chAuto)
  );

  const handleSave = async () => {
    if (!canSave) {
      toast.error('Preencha escola, turma(s), componente(s), data de início e carga horária.');
      return;
    }
    setSaving(true);
    try {
      let ok = 0, fail = 0;
      for (const k of combinacoes) {
        const ch = chOverrideNum !== null ? chOverrideNum : (k.chAuto || 0);
        try {
          await teacherAssignmentAPI.createSubstitution({
            staff_id: alocacaoForm.staff_id,
            school_id: schoolId,
            class_id: k.turma.id,
            course_id: k.componente.id,
            academic_year: alocacaoForm.academic_year || new Date().getFullYear(),
            carga_horaria_semanal: ch,
            data_inicio_substituicao: dataInicio,
            data_fim_substituicao: dataFim || null,
            substituted_staff_id: k.regenteAssign?.staff_id || null,
            status: 'ativo',
          });
          ok += 1;
        } catch (e) {
          fail += 1;
          console.error('Falha em substituição:', k.turma.name, k.componente.name, e);
        }
      }
      if (ok > 0 && fail === 0) {
        toast.success(`${ok} substituição(ões) cadastrada(s) e enviada(s) à folha de pagamento.`);
      } else if (ok > 0 && fail > 0) {
        toast.warning(`${ok} cadastrada(s), ${fail} falharam. Verifique o console.`);
      } else {
        toast.error('Nenhuma substituição foi cadastrada.');
      }
      // Reset
      setSelectedTurmas([]);
      setSelectedComponentes([]);
      setCurrentTurma(''); setCurrentComponente('');
      setDataInicio(new Date().toISOString().slice(0, 10));
      setDataFim(''); setCargaHorariaOverride('');
      if (onSaved) onSaved();
    } finally {
      setSaving(false);
    }
  };

  if (!alocacaoForm.staff_id) return null;

  // Aviso sem lotação (mesma UX da Alocação)
  if (!professorSchools || professorSchools.length === 0) {
    return (
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg mt-4" data-testid="substituicao-no-lotacao">
        <div className="flex items-center gap-2 mb-2">
          <UserCog size={16} className="text-yellow-700" />
          <h4 className="font-medium text-yellow-900">+ Adicionar Nova Substituição</h4>
        </div>
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="text-yellow-600" size={20} />
          <p className="text-sm font-medium text-yellow-800">
            Atenção: este professor não possui lotação ativa em nenhuma escola.
          </p>
        </div>
        <p className="text-sm text-yellow-700 ml-7">
          Para cadastrar substituição, primeiro adicione uma lotação na aba <strong>Lotações</strong> da página principal.
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 bg-amber-50 rounded-lg border border-amber-300 mt-4" data-testid="substituicao-section">
      <h4 className="font-medium text-amber-900 mb-3 flex items-center gap-2">
        <UserCog size={16} /> + Adicionar Nova Substituição
      </h4>
      <p className="text-xs text-amber-700 mb-3">
        O professor selecionado acima atuará como substituto. Informe a(s) turma(s) e componente(s) do(s) regente(s) a serem substituídos.
      </p>

      {/* Escola */}
      <div className="mb-3">
        <label className="block text-sm font-medium text-gray-700 mb-1">Escola *</label>
        <select
          value={schoolId}
          onChange={(e) => setSchoolId(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-amber-500 bg-white"
          data-testid="subst-school-select"
        >
          <option value="">Selecione a escola</option>
          {(professorSchools || []).map(s => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>

      {/* Turmas (multi-add) */}
      <div className="mb-3">
        <label className="block text-sm font-medium text-gray-700 mb-1">Série/Ano (Turma) *</label>
        <div className="flex gap-2">
          <select
            value={currentTurma}
            onChange={(e) => setCurrentTurma(e.target.value)}
            disabled={!schoolId || loadingTurmas}
            className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-amber-500 bg-white disabled:bg-gray-100"
            data-testid="subst-class-select"
          >
            <option value="">
              {!schoolId
                ? 'Selecione a escola primeiro'
                : loadingTurmas
                  ? 'Carregando...'
                  : turmasDisponiveis.length === 0
                    ? (turmasDaEscola.length === 0 ? 'Nenhuma turma encontrada' : 'Todas já adicionadas')
                    : 'Selecione a turma'}
            </option>
            {turmasDisponiveis.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <Button
            type="button"
            onClick={handleAddTurma}
            disabled={!currentTurma}
            data-testid="subst-add-turma-btn"
          >
            <Plus size={16} />
          </Button>
        </div>

        {selectedTurmas.length > 0 && (
          <div className="mt-2 space-y-1">
            {selectedTurmas.map(t => (
              <div
                key={t.id}
                className="flex items-center gap-2 bg-amber-100 px-3 py-2 rounded border border-amber-300"
                data-testid={`subst-turma-chip-${t.id}`}
              >
                <GraduationCap size={16} className="text-amber-700" />
                <span className="flex-1 text-sm font-medium">{t.name}</span>
                <button
                  type="button"
                  onClick={() => handleRemoveTurma(t.id)}
                  className="text-red-500 hover:text-red-700"
                  aria-label={`Remover ${t.name}`}
                >
                  <Minus size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Componentes (multi-add) */}
      <div className="mb-3">
        <label className="block text-sm font-medium text-gray-700 mb-1">Componentes Curriculares *</label>
        <div className="flex gap-2">
          <select
            value={currentComponente}
            onChange={(e) => setCurrentComponente(e.target.value)}
            disabled={selectedTurmas.length === 0}
            className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-amber-500 bg-white disabled:bg-gray-100"
            data-testid="subst-course-select"
          >
            <option value="">
              {selectedTurmas.length === 0
                ? 'Adicione uma turma primeiro'
                : componentesDisponiveis.length === 0
                  ? 'Nenhum componente disponível'
                  : 'Selecione o componente'}
            </option>
            {selectedTurmas.length > 0 && componentesDisponiveis.length > 0 && (
              <option value="TODOS" className="font-bold">TODOS ({componentesDisponiveis.length} componentes)</option>
            )}
            {componentesDisponiveis.map(c => (
              <option key={c.id} value={c.id}>
                {c.name} {c.workload ? `(${c.workload}h)` : ''}
              </option>
            ))}
          </select>
          <Button
            type="button"
            onClick={handleAddComponente}
            disabled={!currentComponente || selectedTurmas.length === 0}
            data-testid="subst-add-comp-btn"
          >
            <Plus size={16} />
          </Button>
        </div>

        {selectedTurmas.length > 0 && componentesDisponiveis.length === 0 && selectedComponentes.length === 0 && (
          <p className="text-[11px] text-amber-700 mt-1">
            O substituto já está alocado em todos os componentes das turmas selecionadas.
          </p>
        )}

        {selectedComponentes.length > 0 && (
          <div className="mt-2 space-y-1">
            {selectedComponentes.map(comp => (
              <div
                key={comp.id}
                className="flex items-center gap-2 bg-purple-100 px-3 py-2 rounded border border-purple-300"
                data-testid={`subst-comp-chip-${comp.id}`}
              >
                <BookOpen size={16} className="text-purple-600" />
                <span className="flex-1 text-sm font-medium">
                  {comp.name}
                  {comp.workload && (
                    <span className="text-gray-500 ml-1">({comp.workload}h)</span>
                  )}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemoveComponente(comp.id)}
                  className="text-red-500 hover:text-red-700"
                  aria-label={`Remover ${comp.name}`}
                >
                  <Minus size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Preview de combinações + regentes */}
      {combinacoes.length > 0 && (
        <div className="mb-3 p-3 bg-white border border-amber-200 rounded-lg">
          <p className="text-xs font-medium text-amber-800 mb-2">
            {combinacoes.length} substituição(ões) serão criadas:
          </p>
          <ul className="text-xs space-y-1 max-h-40 overflow-y-auto" data-testid="subst-preview-list">
            {combinacoes.map((k, i) => (
              <li key={`${k.turma.id}-${k.componente.id}`} className="flex justify-between gap-2 text-gray-700">
                <span>
                  <strong>{k.turma.name}</strong> · {k.componente.name}
                </span>
                <span className="text-gray-500 whitespace-nowrap">
                  Regente: {k.regenteLabel}
                  {k.chAuto ? ` · ${k.chAuto}h/sem` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Data início + Data fim + CH override */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1 flex items-center gap-1">
            <Calendar size={12}/> Data Início *
          </label>
          <input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500"
            data-testid="subst-data-inicio"/>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1 flex items-center gap-1">
            <Calendar size={12}/> Data Fim (opcional)
          </label>
          <input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500"
            data-testid="subst-data-fim"/>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">CH Semanal por combinação</label>
          <input
            type="number" min="0" max="60"
            value={cargaHorariaOverride}
            onChange={(e) => setCargaHorariaOverride(e.target.value)}
            placeholder="auto (regente)"
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500"
            data-testid="subst-ch-input"/>
        </div>
      </div>

      {combinacoes.length > 0 && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg mb-3">
          <div className="flex justify-between items-center">
            <span className="text-sm font-medium text-green-800">
              CH total das substituições:
            </span>
            <span className="text-lg font-bold text-green-700">{chTotalEstimada}h/sem</span>
          </div>
          {chOverrideNum === null && combinacoes.some(k => !k.chAuto) && (
            <p className="text-[11px] text-red-600 mt-1">
              Combinações sem regente detectado precisam de CH manual (preencha o campo acima).
            </p>
          )}
        </div>
      )}

      <Button
        onClick={handleSave}
        disabled={saving || !canSave}
        className="bg-amber-600 hover:bg-amber-700 text-white"
        data-testid="subst-save-btn"
      >
        {saving
          ? 'Salvando...'
          : (combinacoes.length > 1
              ? (<><Check size={16} className="mr-1"/> Adicionar {combinacoes.length} Substituições</>)
              : (<><Check size={16} className="mr-1"/> Adicionar Substituição</>))}
      </Button>
    </div>
  );
};

export default SubstituicaoSection;
