import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Home, Wrench, Type, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const AdminTools = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const runMigration = async (type) => {
    setLoading(true);
    setResult(null);
    setError(null);
    
    try {
      let endpoint = '';
      
      switch (type) {
        case 'uppercase':
          endpoint = '/api/admin/migrate-uppercase';
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
