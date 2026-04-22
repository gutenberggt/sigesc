import { useMemo, useState } from 'react';
import { UserCog, Calendar, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { teacherAssignmentAPI } from '@/services/api';
import { toast } from 'sonner';

/**
 * Seção "+ Adicionar Nova Substituição".
 *
 * Recebe do pai o **professor substituto já selecionado** (alocacaoForm.staff_id) e os dados
 * de referência (escolas, turmas, componentes, alocações existentes) para inferir o regente
 * automaticamente a partir de escola+turma+componente.
 *
 * Ao salvar, chama `teacherAssignmentAPI.createSubstitution` — o backend cria o registro da
 * substituição e gera lotação temporária na escola se necessário, garantindo que a
 * substituição apareça automaticamente na Folha de Pagamento.
 */
export const SubstituicaoSection = ({
  alocacaoForm,            // contém staff_id do substituto e academic_year
  professorSchools,        // escolas do substituto (precisa ter lotação OU será criada auto)
  filteredClasses,         // turmas disponíveis
  courses,                 // todos componentes
  staffList,               // para exibir nome do regente
  existingAlocacoes,       // teacher_assignments do ano (todos) — para descobrir o regente
  schools,                 // todas escolas
  onSaved,                 // callback após salvar
}) => {
  const [schoolId, setSchoolId] = useState('');
  const [classId, setClassId] = useState('');
  const [courseId, setCourseId] = useState('');
  const [dataInicio, setDataInicio] = useState(new Date().toISOString().slice(0, 10));
  const [dataFim, setDataFim] = useState('');
  const [cargaHoraria, setCargaHoraria] = useState('');
  const [saving, setSaving] = useState(false);

  // Turmas da escola selecionada
  const turmasDaEscola = useMemo(() => {
    if (!schoolId) return [];
    return (filteredClasses || []).filter(c => c.school_id === schoolId);
  }, [schoolId, filteredClasses]);

  // Componentes: baseado no nível da turma quando possível
  const componentesDaTurma = useMemo(() => {
    if (!classId) return courses || [];
    const turma = (filteredClasses || []).find(c => c.id === classId);
    if (!turma) return courses || [];
    const nivel = turma.education_level || turma.nivel_ensino;
    if (!nivel) return courses || [];
    return (courses || []).filter(c => !c.nivel_ensino || c.nivel_ensino === nivel);
  }, [classId, courses, filteredClasses]);

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
            {(schools || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Turma *</label>
          <select value={classId} onChange={(e) => { setClassId(e.target.value); setCourseId(''); }}
            disabled={!schoolId}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500 bg-white disabled:bg-gray-100"
            data-testid="subst-class-select">
            <option value="">Selecione</option>
            {turmasDaEscola.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Componente *</label>
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)}
            disabled={!classId}
            className="w-full px-2 py-1.5 text-sm border rounded focus:ring-2 focus:ring-amber-500 bg-white disabled:bg-gray-100"
            data-testid="subst-course-select">
            <option value="">Selecione</option>
            {componentesDaTurma.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
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
