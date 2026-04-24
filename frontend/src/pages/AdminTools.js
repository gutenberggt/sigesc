import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Home, Wrench, Type, CheckCircle2, AlertCircle, Loader2, Calendar, Trash2, Clock, UserX, UserPlus } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const AdminTools = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(false);
  const [loadingType, setLoadingType] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [confirmExecute, setConfirmExecute] = useState(false);
  const [bulkStudentPlan, setBulkStudentPlan] = useState(null);
  const [bulkStudentResult, setBulkStudentResult] = useState(null);
  const [confirmBulkStudent, setConfirmBulkStudent] = useState(false);

  const runBulkStudentUsers = async (apply) => {
    setLoading(true);
    setLoadingType('bulk-student-users');
    setResult(null);
    setError(null);
    if (!apply) {
      setBulkStudentPlan(null);
      setBulkStudentResult(null);
    }
    try {
      const response = await fetch(`${API_URL}/api/admin/student-users/bulk-create`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ apply }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Erro ao executar a criação em massa');
      }
      const data = await response.json();
      if (apply) {
        setBulkStudentResult(data);
        setConfirmBulkStudent(false);
      } else {
        setBulkStudentPlan(data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingType(null);
    }
  };

  const runMigration = async (type) => {
    setLoading(true);
    setLoadingType(type);
    setResult(null);
    setError(null);
    
    try {
      let endpoint = '';
      
      switch (type) {
        case 'uppercase':
          endpoint = '/api/admin/migrate-uppercase';
          break;
        case 'history-dates':
          endpoint = '/api/admin/migrate-history-dates';
          break;
        case 'payroll-hours':
          endpoint = '/api/admin/migrate-payroll-hours';
          break;
        case 'ch-to-lotacao':
          endpoint = '/api/admin/migrate-staff-ch-to-lotacao';
          break;
        case 'cleanup-anexa':
          endpoint = '/api/admin/cleanup-anexa-payroll';
          break;
        default:
          throw new Error('Tipo de migração inválido');
      }
      
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Erro ao executar migração');
      }
      
      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingType(null);
    }
  };

  const runCancelledCleanup = async (dryRun = true) => {
    setLoading(true);
    setLoadingType('cancelled-cleanup');
    setResult(null);
    setError(null);
    if (!dryRun) setPreviewData(null);
    
    try {
      const response = await fetch(`${API_URL}/api/maintenance/cleanup-cancelled-enrollments?dry_run=${dryRun}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Erro ao executar limpeza');
      }
      
      const data = await response.json();
      
      if (dryRun) {
        setPreviewData(data);
      } else {
        setResult(data);
        setConfirmExecute(false);
        setPreviewData(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingType(null);
    }
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <button 
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 text-gray-500 hover:text-blue-600 transition-colors"
          >
            <Home size={20} />
            <span>Início</span>
          </button>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Wrench className="text-amber-600" />
            Ferramentas de Administração
          </h1>
        </div>
        <p className="text-gray-500">Ferramentas de manutenção e migração de dados</p>
      </div>
      
      {/* Alertas */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
          <AlertCircle className="text-red-600" size={24} />
          <div>
            <p className="font-medium text-red-800">Erro</p>
            <p className="text-red-600">{error}</p>
          </div>
        </div>
      )}
      
      {result && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-center gap-3 mb-3">
            <CheckCircle2 className="text-green-600" size={24} />
            <p className="font-medium text-green-800">{result.message}</p>
          </div>
          {result.details && (
            <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
              {typeof result.details.total === 'number' ? (
                <>
                  <div className="bg-white rounded p-2 text-sm">
                    <p className="font-medium text-gray-700">Total</p>
                    <p className="text-gray-500">{result.details.total}</p>
                  </div>
                  <div className="bg-white rounded p-2 text-sm">
                    <p className="font-medium text-gray-700">Atualizados</p>
                    <p className="text-gray-500">{result.details.updated}</p>
                  </div>
                  {result.details.skipped !== undefined && (
                    <div className="bg-white rounded p-2 text-sm">
                      <p className="font-medium text-gray-700">Sem alteração</p>
                      <p className="text-gray-500">{result.details.skipped}</p>
                    </div>
                  )}
                </>
              ) : (
                Object.entries(result.details).map(([key, value]) => (
                  <div key={key} className="bg-white rounded p-2 text-sm">
                    <p className="font-medium text-gray-700 capitalize">{key}</p>
                    <p className="text-gray-500">
                      {value.updated} / {value.total} atualizados
                    </p>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Ferramentas */}
      <div className="bg-white border rounded-lg p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Migrações de Dados</h2>
        
        <div className="space-y-4">
          {/* Migração para Caixa Alta */}
          <div className="border rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-amber-100 rounded-lg">
                  <Type className="text-amber-600" size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Converter para CAIXA ALTA</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Converte todos os nomes e campos de texto para letras maiúsculas no banco de dados.
                  </p>
                  <p className="text-xs text-gray-400 mt-2">
                    Afeta: Alunos, Servidores, Escolas, Turmas, Componentes Curriculares
                  </p>
                </div>
              </div>
              <button
                onClick={() => runMigration('uppercase')}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <>
                    <Loader2 className="animate-spin" size={18} />
                    Executando...
                  </>
                ) : (
                  <>
                    <Type size={18} />
                    Executar
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Migração de Datas do Histórico */}
          <div className="border rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <Calendar className="text-blue-600" size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Migrar Datas do Histórico</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Define a data de matrícula como 15/01/2026 para todos os registros de matrícula no histórico.
                  </p>
                </div>
              </div>
              <button
                onClick={() => runMigration('history-dates')}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {loading && loadingType === 'history-dates' ? (
                  <>
                    <Loader2 className="animate-spin" size={18} />
                    Executando...
                  </>
                ) : (
                  <>
                    <Calendar size={18} />
                    Executar
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Migração de Carga Horária da Folha */}
          <div className="border rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-green-100 rounded-lg">
                  <Clock className="text-green-600" size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Recalcular Carga Horária Mensal (Folha)</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Atualiza as horas previstas e trabalhadas de todos os itens da folha de pagamento.
                    Aplica a fórmula correta: Carga Semanal × 5.
                  </p>
                  <p className="text-xs text-gray-400 mt-2">
                    Afeta: Itens da Folha de Pagamento (payroll_items)
                  </p>
                </div>
              </div>
              <button
                onClick={() => runMigration('payroll-hours')}
                disabled={loading}
                data-testid="btn-migrate-payroll-hours"
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {loading && loadingType === 'payroll-hours' ? (
                  <>
                    <Loader2 className="animate-spin" size={18} />
                    Executando...
                  </>
                ) : (
                  <>
                    <Clock size={18} />
                    Executar
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Migrar CH do Servidor para Lotações */}
          <div className="border rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-indigo-100 rounded-lg">
                  <Clock className="text-indigo-600" size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Migrar Carga Horária Semanal → Lotações</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Copia <code className="text-xs bg-gray-100 px-1">staff.carga_horaria_semanal</code> para cada
                    lotação ativa do servidor (school_assignments). Servidores com múltiplas lotações recebem
                    a mesma CH em cada escola (podem ser ajustadas depois em Gerenciar Lotações).
                  </p>
                  <p className="text-xs text-gray-400 mt-2">
                    Idempotente — lotações com CH já preenchida não são sobrescritas. Afeta: school_assignments.
                  </p>
                </div>
              </div>
              <button
                onClick={() => runMigration('ch-to-lotacao')}
                disabled={loading}
                data-testid="btn-migrate-ch-to-lotacao"
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {loading && loadingType === 'ch-to-lotacao' ? (
                  <>
                    <Loader2 className="animate-spin" size={18} />
                    Executando...
                  </>
                ) : (
                  <>
                    <Clock size={18} />
                    Executar
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Limpeza de Servidores Anexos na Folha */}
          <div className="border rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-purple-100 rounded-lg">
                  <UserX className="text-purple-600" size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Limpar Servidores Anexos da Folha</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Remove itens da folha de pagamento vinculados a lotações do tipo "anexa".
                    Servidores lotados como Secretário(a), Diretor(a) ou Coordenador(a) em escolas anexas
                    não devem aparecer na folha dessas escolas.
                  </p>
                  <p className="text-xs text-gray-400 mt-2">
                    Afeta: Itens da Folha de Pagamento de escolas anexas
                  </p>
                </div>
              </div>
              <button
                onClick={() => runMigration('cleanup-anexa')}
                disabled={loading}
                data-testid="btn-cleanup-anexa-payroll"
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {loading && loadingType === 'cleanup-anexa' ? (
                  <>
                    <Loader2 className="animate-spin" size={18} />
                    Executando...
                  </>
                ) : (
                  <>
                    <UserX size={18} />
                    Executar
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Criar Usuários de Alunos em Massa */}
          <div className="border rounded-lg p-4" data-testid="tool-bulk-student-users">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3 flex-1">
                <div className="p-2 bg-emerald-100 rounded-lg">
                  <UserPlus className="text-emerald-600" size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Criar Usuários dos Alunos (em lote)</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Gera contas de acesso (role=aluno) para todos os alunos <strong>ativos</strong> que ainda não têm usuário.
                    É <strong>idempotente</strong> — pode rodar novamente a qualquer momento para atualizar com novos alunos.
                  </p>
                  <div className="text-xs text-gray-500 mt-2 bg-gray-50 rounded p-2 space-y-0.5">
                    <p>• <strong>E-mail</strong>: primeironome + últimosobrenome + mês de nascimento (MM) @sigesc.com</p>
                    <p>• <strong>Senha</strong>: data de nascimento no formato DDMMAAAA</p>
                    <p>• Senha deve ser trocada no 1º acesso</p>
                  </div>
                </div>
              </div>
              <div className="flex flex-col gap-2 shrink-0">
                <button
                  onClick={() => runBulkStudentUsers(false)}
                  disabled={loading}
                  data-testid="btn-preview-bulk-students"
                  className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 whitespace-nowrap"
                >
                  {loading && loadingType === 'bulk-student-users' && !confirmBulkStudent ? (
                    <><Loader2 className="animate-spin" size={18} />Analisando...</>
                  ) : (
                    <><UserPlus size={18} />Ver Prévia</>
                  )}
                </button>
              </div>
            </div>

            {bulkStudentPlan && (
              <div className="mt-4 border-t pt-4" data-testid="bulk-students-preview">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
                  <div className="bg-gray-50 rounded p-2 text-sm text-center">
                    <p className="font-bold text-gray-800">{bulkStudentPlan.totals.scanned}</p>
                    <p className="text-gray-600 text-xs">Alunos avaliados</p>
                  </div>
                  <div className="bg-emerald-50 rounded p-2 text-sm text-center">
                    <p className="font-bold text-emerald-700">{bulkStudentPlan.totals.to_create}</p>
                    <p className="text-emerald-600 text-xs">Serão criados</p>
                  </div>
                  <div className="bg-blue-50 rounded p-2 text-sm text-center">
                    <p className="font-bold text-blue-700">{bulkStudentPlan.totals.already_has_user}</p>
                    <p className="text-blue-600 text-xs">Já possuem user</p>
                  </div>
                  <div className="bg-amber-50 rounded p-2 text-sm text-center">
                    <p className="font-bold text-amber-700">{bulkStudentPlan.totals.skipped}</p>
                    <p className="text-amber-600 text-xs">Ignorados</p>
                  </div>
                </div>

                {bulkStudentPlan.preview_to_create && bulkStudentPlan.preview_to_create.length > 0 && (
                  <div className="max-h-64 overflow-y-auto border rounded mb-3">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-100 sticky top-0">
                        <tr>
                          <th className="text-left p-2">Aluno</th>
                          <th className="text-left p-2">E-mail</th>
                          <th className="text-left p-2">Senha (DDMMAAAA)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bulkStudentPlan.preview_to_create.map((r) => (
                          <tr key={r.student_id} className="border-t">
                            <td className="p-2">{r.full_name}</td>
                            <td className="p-2 font-mono text-[11px]">{r.email}</td>
                            <td className="p-2 font-mono">{r.password}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {bulkStudentPlan.totals.to_create > bulkStudentPlan.preview_to_create.length && (
                      <p className="p-2 text-[11px] text-gray-500 bg-gray-50">
                        Mostrando {bulkStudentPlan.preview_to_create.length} de {bulkStudentPlan.totals.to_create} novos usuários.
                      </p>
                    )}
                  </div>
                )}

                {bulkStudentPlan.skipped && bulkStudentPlan.skipped.length > 0 && (
                  <details className="mb-3">
                    <summary className="text-xs text-amber-700 cursor-pointer font-medium">
                      Ver {bulkStudentPlan.skipped.length} aluno(s) ignorado(s)
                    </summary>
                    <div className="max-h-40 overflow-y-auto mt-2 border rounded bg-amber-50/50">
                      <table className="w-full text-xs">
                        <thead className="bg-amber-100 sticky top-0">
                          <tr>
                            <th className="text-left p-2">Aluno</th>
                            <th className="text-left p-2">Motivo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {bulkStudentPlan.skipped.map((s) => (
                            <tr key={s.student_id} className="border-t border-amber-200">
                              <td className="p-2">{s.full_name || '(sem nome)'}</td>
                              <td className="p-2 text-amber-800">{s.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}

                {bulkStudentPlan.totals.to_create > 0 && !bulkStudentResult && (
                  !confirmBulkStudent ? (
                    <button
                      onClick={() => setConfirmBulkStudent(true)}
                      className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
                      data-testid="btn-confirm-bulk-students"
                    >
                      Criar {bulkStudentPlan.totals.to_create} usuário(s)
                    </button>
                  ) : (
                    <div className="flex items-center gap-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                      <p className="text-emerald-900 font-medium text-sm flex-1">
                        Confirma a criação de {bulkStudentPlan.totals.to_create} usuário(s)?
                      </p>
                      <button
                        onClick={() => runBulkStudentUsers(true)}
                        disabled={loading}
                        className="px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 disabled:opacity-50 whitespace-nowrap"
                        data-testid="btn-execute-bulk-students"
                      >
                        {loading && loadingType === 'bulk-student-users' ? (
                          <span className="flex items-center gap-2"><Loader2 className="animate-spin" size={16} />Criando...</span>
                        ) : 'Confirmar Criação'}
                      </button>
                      <button
                        onClick={() => setConfirmBulkStudent(false)}
                        className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
                      >
                        Cancelar
                      </button>
                    </div>
                  )
                )}

                {bulkStudentPlan.totals.to_create === 0 && !bulkStudentResult && (
                  <p className="text-sm text-blue-700 bg-blue-50 p-2 rounded">
                    ✅ Todos os alunos ativos já possuem usuário.
                  </p>
                )}

                {bulkStudentResult && (
                  <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="text-green-600" size={20} />
                      <p className="font-medium text-green-900">
                        {bulkStudentResult.applied?.inserted ?? 0} usuário(s) criado(s).
                      </p>
                    </div>
                    {bulkStudentResult.applied?.errors?.length > 0 && (
                      <p className="text-xs text-red-600">
                        {bulkStudentResult.applied.errors.length} erro(s) — verifique logs do servidor.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Limpeza de Matrículas Canceladas */}
          <div className="border rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-red-100 rounded-lg">
                  <Trash2 className="text-red-600" size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Limpar Matrículas Canceladas</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Remove dados de alunos com matrícula cancelada: frequências, notas e matrículas.
                    Define o status como inativo e limpa escola/turma.
                  </p>
                  <p className="text-xs text-gray-400 mt-2">
                    Afeta: Matrículas canceladas, registros de frequência, notas
                  </p>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => runCancelledCleanup(true)}
                  disabled={loading}
                  data-testid="btn-preview-cancelled-cleanup"
                  className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  {loading && loadingType === 'cancelled-cleanup' && !confirmExecute ? (
                    <>
                      <Loader2 className="animate-spin" size={18} />
                      Verificando...
                    </>
                  ) : (
                    <>
                      <Trash2 size={18} />
                      Ver Prévia
                    </>
                  )}
                </button>
              </div>
            </div>
            
            {/* Prévia dos dados */}
            {previewData && (
              <div className="mt-4 border-t pt-4">
                <p className="font-medium text-gray-800 mb-2">{previewData.message}</p>
                {previewData.affected && previewData.affected.length > 0 ? (
                  <>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
                      <div className="bg-red-50 rounded p-2 text-sm text-center">
                        <p className="font-bold text-red-700">{previewData.totals.students}</p>
                        <p className="text-red-600 text-xs">Alunos</p>
                      </div>
                      <div className="bg-red-50 rounded p-2 text-sm text-center">
                        <p className="font-bold text-red-700">{previewData.totals.enrollments}</p>
                        <p className="text-red-600 text-xs">Matrículas</p>
                      </div>
                      <div className="bg-red-50 rounded p-2 text-sm text-center">
                        <p className="font-bold text-red-700">{previewData.totals.attendance}</p>
                        <p className="text-red-600 text-xs">Frequências</p>
                      </div>
                      <div className="bg-red-50 rounded p-2 text-sm text-center">
                        <p className="font-bold text-red-700">{previewData.totals.grades}</p>
                        <p className="text-red-600 text-xs">Notas</p>
                      </div>
                    </div>
                    <div className="max-h-40 overflow-y-auto border rounded mb-3">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50 sticky top-0">
                          <tr>
                            <th className="text-left p-2">Aluno</th>
                            <th className="text-center p-2">Matrículas</th>
                            <th className="text-center p-2">Frequências</th>
                            <th className="text-center p-2">Notas</th>
                          </tr>
                        </thead>
                        <tbody>
                          {previewData.affected.map((a, i) => (
                            <tr key={i} className="border-t">
                              <td className="p-2">{a.name}</td>
                              <td className="text-center p-2">{a.enrollments}</td>
                              <td className="text-center p-2">{a.attendance}</td>
                              <td className="text-center p-2">{a.grades}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!confirmExecute ? (
                      <button
                        onClick={() => setConfirmExecute(true)}
                        className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                        data-testid="btn-confirm-cancelled-cleanup"
                      >
                        Executar Limpeza
                      </button>
                    ) : (
                      <div className="flex items-center gap-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                        <p className="text-red-800 font-medium text-sm">Tem certeza? Esta ação não pode ser desfeita.</p>
                        <button
                          onClick={() => runCancelledCleanup(false)}
                          disabled={loading}
                          className="px-4 py-2 bg-red-700 text-white rounded-lg hover:bg-red-800 disabled:opacity-50 whitespace-nowrap"
                          data-testid="btn-execute-cancelled-cleanup"
                        >
                          {loading && loadingType === 'cancelled-cleanup' ? (
                            <span className="flex items-center gap-2"><Loader2 className="animate-spin" size={16} /> Executando...</span>
                          ) : 'Confirmar Execução'}
                        </button>
                        <button
                          onClick={() => setConfirmExecute(false)}
                          className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
                        >
                          Cancelar
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-green-600 text-sm">Nenhum aluno cancelado encontrado.</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Aviso */}
      <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <p className="text-sm text-yellow-800">
          <strong>Atenção:</strong> Essas operações afetam diretamente o banco de dados. 
          Execute apenas quando necessário e certifique-se de que não há outros usuários utilizando o sistema.
        </p>
      </div>
    </div>
  );
};

export default AdminTools;
