import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Home, Wrench, Type, CheckCircle2, AlertCircle, Loader2, Calendar, Trash2 } from 'lucide-react';
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
              {Object.entries(result.details).map(([key, value]) => (
                <div key={key} className="bg-white rounded p-2 text-sm">
                  <p className="font-medium text-gray-700 capitalize">{key}</p>
                  <p className="text-gray-500">
                    {value.updated} / {value.total} atualizados
                  </p>
                </div>
              ))}
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
                    Define datas retroativas nos registros de histórico de alunos que não possuem data personalizada.
                  </p>
                  <p className="text-xs text-gray-400 mt-2">
                    Matrículas: 15/jan | Transferências: 10/mar | Cancelamentos: 18/jan
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
