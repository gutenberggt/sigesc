import React, { useState, useEffect, useRef } from 'react';
import { Users, Target, Activity, BookOpen, Clock, Calendar, ChevronDown } from 'lucide-react';

const PUBLICO_ALVO_LABELS = {
  'deficiencia_fisica': 'Deficiência Física',
  'deficiencia_intelectual': 'Deficiência Intelectual',
  'deficiencia_visual': 'Deficiência Visual',
  'deficiencia_auditiva': 'Deficiência Auditiva',
  'surdocegueira': 'Surdocegueira',
  'transtorno_espectro_autista': 'Transtorno do Espectro Autista (TEA)',
  'altas_habilidades': 'Altas Habilidades/Superdotação',
  'deficiencia_multipla': 'Deficiência Múltipla'
};

const MODALIDADE_LABELS = {
  'individual': 'Individual',
  'pequeno_grupo': 'Pequeno Grupo',
  'coensino': 'Coensino',
  'mista': 'Mista'
};

const DIAS_SEMANA = {
  'segunda': 'Segunda',
  'terca': 'Terça',
  'quarta': 'Quarta',
  'quinta': 'Quinta',
  'sexta': 'Sexta'
};

const INITIAL_FORM = {
  student_id: '',
  publico_alvo: '',
  criterio_elegibilidade: '',
  turma_origem_id: '',
  turma_origem_nome: '',
  escola_origem_nome: '',
  professor_regente_id: '',
  professor_regente_nome: '',
  dias_atendimento: [],
  horario_inicio: '',
  horario_fim: '',
  modalidade: 'individual',
  carga_horaria_semanal: '',
  local_atendimento: 'Sala de Recursos Multifuncionais',
  barreiras: '',
  objetivos: '',
  recursos_acessibilidade: '',
  orientacoes_sala_comum: '',
  adequacoes_curriculares: '',
  data_inicio: '',
  data_revisao: '',
  status: 'rascunho',
  data_elaboracao: '',
  periodo_vigencia: '',
  linha_base_situacao_atual: '',
  linha_base_potencialidades: '',
  linha_base_dificuldades: '',
  linha_base_comunicacao: '',
  indicadores_progresso: '',
  frequencia_revisao: 'bimestral',
  criterios_ajuste: '',
  combinados_professor_regente: '',
  adaptacoes_por_componente: ''
};

function StudentDropdown({ value, onChange, estudantes, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const getName = (est) => est.student_name || est.full_name || '';
  const selected = estudantes.find(e => e.student_id === value);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => !disabled && setOpen(!open)}
        className={`force-visible-text w-full border rounded-lg px-3 py-2 text-left flex items-center justify-between ${disabled ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:border-gray-400'}`}
      >
        <span className={selected ? 'force-visible-text' : 'force-visible-text-muted'}>{selected ? getName(selected) : 'Selecione o aluno'}</span>
        <ChevronDown size={16} className="force-visible-text-muted" />
      </button>
      {open && (
        <div className="force-visible-text absolute z-50 mt-1 w-full rounded-lg shadow-lg max-h-60 overflow-y-auto" style={{ border: '1px solid #d1d5db' }}>
          <div
            className="force-visible-text-muted px-3 py-2 cursor-pointer hover:bg-gray-100"
            onClick={() => { onChange(''); setOpen(false); }}
          >Selecione o aluno</div>
          {estudantes.map(est => (
            <div
              key={est.student_id}
              className={`force-visible-text px-3 py-2 cursor-pointer hover:bg-blue-50 ${est.student_id === value ? 'bg-blue-100 font-medium' : ''}`}
              onClick={() => { onChange(est.student_id); setOpen(false); }}
            >{getName(est)}</div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PlanoAEEModal({ show, onClose, onSave, editingPlano, estudantes, canEdit }) {
  const [form, setForm] = useState({ ...INITIAL_FORM });

  useEffect(() => {
    if (!show) return;
    if (editingPlano) {
      setForm({
        ...INITIAL_FORM,
        ...editingPlano,
        barreiras: Array.isArray(editingPlano.barreiras) ? editingPlano.barreiras.join('\n') : (editingPlano.barreiras || ''),
        objetivos: Array.isArray(editingPlano.objetivos) ? editingPlano.objetivos.join('\n') : (editingPlano.objetivos || ''),
        recursos_acessibilidade: Array.isArray(editingPlano.recursos_acessibilidade) ? editingPlano.recursos_acessibilidade.join('\n') : (editingPlano.recursos_acessibilidade || ''),
      });
    } else {
      setForm({ ...INITIAL_FORM });
    }
  }, [show, editingPlano]);

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const handleStudentChange = (studentId) => {
    const est = estudantes.find(e => e.student_id === studentId);
    setForm(prev => ({
      ...prev,
      student_id: studentId,
      turma_origem_id: est?.class_id || '',
      turma_origem_nome: est?.turma_origem || '',
      escola_origem_nome: est?.escola_origem || '',
      professor_regente_nome: est?.professor_regente || ''
    }));
  };

  const getStudentName = (est) => est.student_name || est.full_name || '';

  const handleDiaToggle = (dia) => {
    setForm(prev => {
      const dias = prev.dias_atendimento.includes(dia)
        ? prev.dias_atendimento.filter(d => d !== dia)
        : [...prev.dias_atendimento, dia];
      return { ...prev, dias_atendimento: dias };
    });
  };

  const handleSave = () => {
    const linesOf = (v) => (typeof v === 'string' ? v.split('\n').map(s => s.trim()).filter(Boolean) : []);
    const toBarreiras = (v) => {
      if (Array.isArray(v) && v.length && typeof v[0] === 'object') return v;
      return linesOf(v).map(descricao => ({ tipo: 'outra', descricao, estrategias: [] }));
    };
    const toObjetivos = (v) => {
      if (Array.isArray(v) && v.length && typeof v[0] === 'object') return v;
      return linesOf(v).map(descricao => ({
        descricao, prazo: 'medio', indicadores: [], status: 'nao_iniciado'
      }));
    };
    const toRecursos = (v) => {
      if (Array.isArray(v) && v.length && typeof v[0] === 'object') return v;
      return linesOf(v).map(descricao => ({ tipo: 'outro', descricao, disponivel: true }));
    };

    // Feb 2026: backend agora aceita carga_horaria_semanal como string livre.
    // Mantemos o valor digitado pelo usuário ('Ex: 4 horas', '240 min', etc).
    const payload = {
      ...form,
      carga_horaria_semanal: form.carga_horaria_semanal || null,
      barreiras: toBarreiras(form.barreiras),
      objetivos: toObjetivos(form.objetivos),
      recursos_acessibilidade: toRecursos(form.recursos_acessibilidade),
    };
    onSave(payload);
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center z-10">
          <h2 className="text-xl font-semibold text-gray-900">
            {editingPlano ? 'Editar Plano de AEE' : 'Novo Plano de AEE'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>

        <div className="p-6 space-y-6">
          {/* Identificação do Estudante */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Users size={18} /> Identificação do Estudante
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Aluno *</label>
                <StudentDropdown
                  value={form.student_id}
                  onChange={handleStudentChange}
                  estudantes={estudantes}
                  disabled={!!editingPlano}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Público-alvo *</label>
                <select value={form.publico_alvo} onChange={(e) => handleChange('publico_alvo', e.target.value)} className="w-full border rounded-lg px-3 py-2">
                  <option value="">Selecione</option>
                  {Object.entries(PUBLICO_ALVO_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turma do Aluno na Sala Regular</label>
                <input type="text" value={form.turma_origem_nome} readOnly className="w-full border rounded-lg px-3 py-2 bg-gray-50" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Professor Regente</label>
                <input type="text" value={form.professor_regente_nome} readOnly className="w-full border rounded-lg px-3 py-2 bg-gray-50" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Escola de Origem</label>
                <input type="text" value={form.escola_origem_nome} readOnly className="w-full border rounded-lg px-3 py-2 bg-gray-50" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Critério de Elegibilidade</label>
                <input type="text" value={form.criterio_elegibilidade} onChange={(e) => handleChange('criterio_elegibilidade', e.target.value)} className="w-full border rounded-lg px-3 py-2" placeholder="Laudo médico, avaliação pedagógica..." />
              </div>
            </div>
          </div>

          {/* Datas e Vigência */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Calendar size={18} /> Datas e Vigência
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Elaboração</label>
                <input type="date" value={form.data_elaboracao} onChange={(e) => handleChange('data_elaboracao', e.target.value)} className="w-full border rounded-lg px-3 py-2" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Período de Vigência</label>
                <input type="text" value={form.periodo_vigencia} onChange={(e) => handleChange('periodo_vigencia', e.target.value)} className="w-full border rounded-lg px-3 py-2" placeholder="Ex: 1º Semestre 2026" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Revisão</label>
                <input type="date" value={form.data_revisao} onChange={(e) => handleChange('data_revisao', e.target.value)} className="w-full border rounded-lg px-3 py-2" />
              </div>
            </div>
          </div>

          {/* Linha de Base */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Activity size={18} /> Linha de Base / Perfil do Estudante
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Situação Atual</label>
                <textarea value={form.linha_base_situacao_atual} onChange={(e) => handleChange('linha_base_situacao_atual', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={3} placeholder="Descreva a situação atual do estudante..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Potencialidades</label>
                <textarea value={form.linha_base_potencialidades} onChange={(e) => handleChange('linha_base_potencialidades', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Pontos fortes e habilidades..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dificuldades Observadas</label>
                <textarea value={form.linha_base_dificuldades} onChange={(e) => handleChange('linha_base_dificuldades', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Desafios e áreas que necessitam de apoio..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Formas de Comunicação e Participação</label>
                <textarea value={form.linha_base_comunicacao} onChange={(e) => handleChange('linha_base_comunicacao', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Como o estudante se comunica e participa..." />
              </div>
            </div>
          </div>

          {/* Barreiras e Objetivos */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Target size={18} /> Barreiras, Objetivos e Recursos
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Barreiras Identificadas</label>
                <textarea value={form.barreiras} onChange={(e) => handleChange('barreiras', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={3} placeholder="Uma barreira por linha (ex: Comunicação, Mobilidade, Aprendizagem...)" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Objetivos do Plano</label>
                <textarea value={form.objetivos} onChange={(e) => handleChange('objetivos', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={3} placeholder="Um objetivo por linha" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Recursos de Acessibilidade</label>
                <textarea value={form.recursos_acessibilidade} onChange={(e) => handleChange('recursos_acessibilidade', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={3} placeholder="Um recurso por linha (ex: Software de leitura, Prancha de comunicação...)" />
              </div>
            </div>
          </div>

          {/* Organização do Atendimento */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Clock size={18} /> Organização do Atendimento
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Dias de Atendimento</label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(DIAS_SEMANA).map(([key, label]) => (
                    <button key={key} type="button"
                      onClick={() => handleDiaToggle(key)}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                        form.dias_atendimento.includes(key) ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >{label}</button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Modalidade</label>
                  <select value={form.modalidade} onChange={(e) => handleChange('modalidade', e.target.value)} className="w-full border rounded-lg px-3 py-2">
                    {Object.entries(MODALIDADE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Horário Início</label>
                  <input type="time" value={form.horario_inicio} onChange={(e) => handleChange('horario_inicio', e.target.value)} className="w-full border rounded-lg px-3 py-2" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Horário Fim</label>
                  <input type="time" value={form.horario_fim} onChange={(e) => handleChange('horario_fim', e.target.value)} className="w-full border rounded-lg px-3 py-2" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Carga Horária Semanal</label>
                  <input type="text" value={form.carga_horaria_semanal} onChange={(e) => handleChange('carga_horaria_semanal', e.target.value)} className="w-full border rounded-lg px-3 py-2" placeholder="Ex: 4 horas" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Local de Atendimento</label>
                  <input type="text" value={form.local_atendimento} onChange={(e) => handleChange('local_atendimento', e.target.value)} className="w-full border rounded-lg px-3 py-2" />
                </div>
              </div>
            </div>
          </div>

          {/* Avaliação e Monitoramento */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <BookOpen size={18} /> Avaliação e Monitoramento
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Indicadores de Progresso</label>
                <textarea value={form.indicadores_progresso} onChange={(e) => handleChange('indicadores_progresso', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Indicadores para avaliar o progresso do estudante..." />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Frequência de Revisão</label>
                  <select value={form.frequencia_revisao} onChange={(e) => handleChange('frequencia_revisao', e.target.value)} className="w-full border rounded-lg px-3 py-2">
                    <option value="mensal">Mensal</option>
                    <option value="bimestral">Bimestral</option>
                    <option value="trimestral">Trimestral</option>
                    <option value="semestral">Semestral</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Critérios para Ajuste</label>
                  <input type="text" value={form.criterios_ajuste} onChange={(e) => handleChange('criterios_ajuste', e.target.value)} className="w-full border rounded-lg px-3 py-2" placeholder="Quando e como ajustar o plano..." />
                </div>
              </div>
            </div>
          </div>

          {/* Articulação com Sala Comum */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <BookOpen size={18} /> Articulação com a Sala Comum
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Orientações para Sala Comum</label>
                <textarea value={form.orientacoes_sala_comum} onChange={(e) => handleChange('orientacoes_sala_comum', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={3} placeholder="Orientações e estratégias para o professor da sala regular..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Combinados com o Professor Regente</label>
                <textarea value={form.combinados_professor_regente} onChange={(e) => handleChange('combinados_professor_regente', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Acordos e combinados com o professor da sala regular..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Adequações Curriculares</label>
                <textarea value={form.adequacoes_curriculares} onChange={(e) => handleChange('adequacoes_curriculares', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Adaptações curriculares necessárias por componente..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Adaptações por Componente Curricular</label>
                <textarea value={form.adaptacoes_por_componente} onChange={(e) => handleChange('adaptacoes_por_componente', e.target.value)} className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Adaptações específicas para cada componente curricular..." />
              </div>
            </div>
          </div>

          {/* Status */}
          <div className="border rounded-lg p-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Status do Plano</label>
            <select value={form.status} onChange={(e) => handleChange('status', e.target.value)} className="w-full border rounded-lg px-3 py-2">
              <option value="rascunho">Rascunho</option>
              <option value="ativo">Ativo</option>
              <option value="revisao">Em Revisão</option>
              <option value="encerrado">Encerrado</option>
            </select>
          </div>
        </div>

        <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-4 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 border rounded-lg hover:bg-gray-100">Cancelar</button>
          <button onClick={handleSave} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            {editingPlano ? 'Atualizar' : 'Salvar'}
          </button>
        </div>
      </div>
    </div>
  );
}
