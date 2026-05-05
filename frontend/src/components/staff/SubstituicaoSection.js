import { useEffect, useMemo, useState } from 'react';
import { UserCog, Calendar, Check, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { teacherAssignmentAPI, classesAPI } from '@/services/api';
import { toast } from 'sonner';

/**
 * Seção "+ Adicionar Nova Substituição".
 *
 * Recebe do pai o **professor substituto já selecionado** (alocacaoForm.staff_id) e os dados
 * de referência (escolas, turmas, componentes, alocações existentes) para inferir o regente
 * automaticamente a partir de escola+turma+componente.
 *
 * [Mai/2026] Regras alinhadas com "Adicionar Nova Alocação":
 *  - Escola: usa `professorSchools` (apenas escolas onde o substituto tem lotação ativa).
 *    Se professor sem lotação → exibe aviso e bloqueia formulário (mesma UX da Alocação).
 *  - Turma: filtrada pela escola selecionada, respeitando ano letivo.
 *  - Componente: mostra carga horária no option e filtra componentes já alocados ao
 *    substituto na mesma turma (dedupe).
 */
export const SubstituicaoSection = ({
  alocacaoForm,            // contém staff_id do substituto e academic_year
  professorSchools,        // escolas do substituto (precisa ter lotação OU será criada auto)
  filteredClasses,         // turmas disponíveis (não usado aqui — fetch local por escola)
  courses,                 // todos componentes
  staffList,               // para exibir nome do regente
  existingAlocacoes,       // teacher_assignments do ano (todos) — para descobrir o regente e dedupe
  schools: _schoolsIgnored,  // não usado: substituição opera nas escolas do próprio professor
  onSaved,                 // callback após salvar
}) => {
  const [schoolId, setSchoolId] = useState('');
  const [classId, setClassId] = useState('');
  const [courseId, setCourseId] = useState('');
  const [dataInicio, setDataInicio] = useState(new Date().toISOString().slice(0, 10));
  const [dataFim, setDataFim] = useState('');
  const [cargaHoraria, setCargaHoraria] = useState('');
  const [saving, setSaving] = useState(false);

  // Busca ativa de turmas da escola — respeita as permissões do usuário no backend
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
          // Filtrar por ano letivo quando conhecido (consistente com o Livro de Promoção)
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

  // Componentes: baseado no nível da turma + dedupe das já alocadas ao substituto na mesma turma
  const componentesDisponiveis = useMemo(() => {
    if (!classId) return [];
    const turma = turmasDaEscola.find(c => c.id === classId);
    const nivel = turma?.education_level || turma?.nivel_ensino;

    let lista = courses || [];
    if (nivel) {
      lista = lista.filter(c => !c.nivel_ensino || c.nivel_ensino === nivel);
    }
    // Dedupe: remove componentes já alocados ao SUBSTITUTO na mesma turma (mesmo padrão da Alocação)
    const jaAlocadosIds = new Set(
      (existingAlocacoes || [])
        .filter(a =>
          a.staff_id === alocacaoForm.staff_id &&
          a.class_id === classId &&
          a.status === 'ativo'
        )
        .map(a => a.course_id)
    );
    return lista.filter(c => !jaAlocadosIds.has(c.id));
  }, [classId, courses, turmasDaEscola, existingAlocacoes, alocacaoForm.staff_id]);

  // Alocação do titular naquela combinação (regente)
  const regenteAlocacao = useMemo(() => {
    if (!classId || !courseId) return null;
    return (existingAlocacoes || []).find(a =>
      a.class_id === classId &&
      a.course_id === courseId &&
      a.status === 'ativo' &&
      !a.is_substituicao &&
      a.staff_id !== alocacaoForm.staff_id
    ) || null;
  }, [classId, courseId, existingAlocacoes, alocacaoForm.staff_id]);

  const regenteNome = useMemo(() => {
    if (!regenteAlocacao) return '';
    const s = (staffList || []).find(x => x.id === regenteAlocacao.staff_id);
    return s ? `${s.nome} (${s.matricula})` : 'Regente não identificado';
  }, [regenteAlocacao, staffList]);

  // Auto-preencher CH quando o regente é encontrado
  const chAutoFromRegente = regenteAlocacao?.carga_horaria_semanal;
  const effectiveCH = cargaHoraria !== '' ? cargaHoraria : (chAutoFromRegente ? String(chAutoFromRegente) : '');

  const canSave = (
    alocacaoForm.staff_id &&
    schoolId && classId && courseId && dataInicio && effectiveCH
  );

  const handleSave = async () => {
    if (!canSave) {
      toast.error('Preencha escola, turma, componente, data de início e carga horária.');
      return;
    }
    setSaving(true);
    try {
      await teacherAssignmentAPI.createSubstitution({
        staff_id: alocacaoForm.staff_id,
        school_id: schoolId,
        class_id: classId,
        course_id: courseId,
        academic_year: alocacaoForm.academic_year || new Date().getFullYear(),
        carga_horaria_semanal: parseInt(effectiveCH, 10),
        data_inicio_substituicao: dataInicio,
        data_fim_substituicao: dataFim || null,
        substituted_staff_id: regenteAlocacao?.staff_id || null,
        status: 'ativo',
      });
      toast.success('Substituição cadastrada e enviada à folha de pagamento.');
      setSchoolId(''); setClassId(''); setCourseId('');
      setDataInicio(new Date().toISOString().slice(0, 10));
      setDataFim(''); setCargaHoraria('');
      if (onSaved) onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao cadastrar substituição.');
    } finally {
      setSaving(false);
    }
  };

  if (!alocacaoForm.staff_id) return null;

  // Aviso quando o professor substituto não tem lotação ativa em nenhuma escola
  // (mesma UX da Alocação — exige criar lotação na aba Lotações primeiro).
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
        O professor selecionado acima atuará como substituto. Informe a turma/componente do regente a ser substituído.
      </p>

      {/* Escola + Turma + Componente */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Escola *</label>
          <select value={schoolId} onChange={(e) => { setSchoolId(e.target.value); setClassId(''); setCourseId(''); }}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500 bg-white"
            data-testid="subst-school-select">
            <option value="">Selecione</option>
            {(professorSchools || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Turma *</label>
          <select value={classId} onChange={(e) => { setClassId(e.target.value); setCourseId(''); }}
            disabled={!schoolId || loadingTurmas}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500 bg-white disabled:bg-gray-100"
            data-testid="subst-class-select">
            <option value="">
              {!schoolId
                ? 'Selecione a escola'
                : loadingTurmas
                  ? 'Carregando...'
                  : turmasDaEscola.length === 0
                    ? 'Nenhuma turma encontrada'
                    : 'Selecione'}
            </option>
            {turmasDaEscola.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Componente *</label>
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)}
            disabled={!classId}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500 bg-white disabled:bg-gray-100"
            data-testid="subst-course-select">
            <option value="">
              {!classId
                ? 'Selecione a turma primeiro'
                : componentesDisponiveis.length === 0
                  ? 'Nenhum componente disponível'
                  : 'Selecione'}
            </option>
            {componentesDisponiveis.map(c => (
              <option key={c.id} value={c.id}>
                {c.name} {c.workload ? `(${c.workload}h)` : ''}
              </option>
            ))}
          </select>
          {classId && componentesDisponiveis.length === 0 && (
            <p className="text-[11px] text-amber-700 mt-1">
              O substituto já está alocado em todos os componentes desta turma.
            </p>
          )}
        </div>
      </div>

      {/* Regente (autofill) */}
      <div className="mb-3">
        <label className="block text-xs font-medium text-gray-700 mb-1">Professor(a) Regente (preenchido automaticamente)</label>
        <input type="text" value={regenteNome || (classId && courseId ? 'Nenhum regente ativo encontrado' : '—')} readOnly
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded bg-gray-50 text-gray-700"
          data-testid="subst-regente-display"/>
      </div>

      {/* Data início + Data fim + CH */}
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
          <label className="block text-xs font-medium text-gray-700 mb-1">CH Semanal *</label>
          <input type="number" min="0" max="60" value={effectiveCH}
            onChange={(e) => setCargaHoraria(e.target.value)}
            placeholder={chAutoFromRegente ? `auto: ${chAutoFromRegente}h` : 'Ex: 10'}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500"
            data-testid="subst-ch-input"/>
        </div>
      </div>

      <Button onClick={handleSave} disabled={saving || !canSave} className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="subst-save-btn">
        {saving ? 'Salvando...' : (<><Check size={16} className="mr-1"/> Adicionar Substituição</>)}
      </Button>
    </div>
  );
};

export default SubstituicaoSection;
