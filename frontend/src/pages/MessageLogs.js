import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/Modal';
import { useAuth } from '@/contexts/AuthContext';
import { messageLogsAPI, uploadAPI } from '@/services/api';
import { 
  Home, FileText, User, Search, Download, Trash2, MessageCircle,
  Calendar, Paperclip, ChevronRight, AlertTriangle, RefreshCw
} from 'lucide-react';

const MessageLogs = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [usersWithLogs, setUsersWithLogs] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [userLogs, setUserLogs] = useState(null);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [showConversation, setShowConversation] = useState(null);
  const [cleaning, setCleaning] = useState(false);
  const [alert, setAlert] = useState({ show: false, type: '', message: '' });

  const showAlertMessage = (type, message) => {
    setAlert({ show: true, type, message });
    setTimeout(() => setAlert({ show: false, type: '', message: '' }), 3000);
  };

  // Verificar se é admin
  useEffect(() => {
    if (user && user.role !== 'admin') {
      navigate('/dashboard');
    }
  }, [user, navigate]);

  // Carregar lista de usuários com logs
  const loadUsersWithLogs = async () => {
    setLoading(true);
    try {
      const data = await messageLogsAPI.listUsers();
      setUsersWithLogs(data);
    } catch (error) {
      console.error('Erro ao carregar usuários:', error);
      showAlertMessage('error', 'Erro ao carregar lista de usuários');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsersWithLogs();
  }, []);

  // Carregar logs de um usuário específico
  const loadUserLogs = async (userId) => {
    setLoadingLogs(true);
    try {
      const data = await messageLogsAPI.getUserLogs(userId);
      setUserLogs(data);
    } catch (error) {
      console.error('Erro ao carregar logs:', error);
      showAlertMessage('error', 'Erro ao carregar logs do usuário');
    } finally {
      setLoadingLogs(false);
    }
  };

  const handleSelectUser = (userItem) => {
    setSelectedUser(userItem);
    loadUserLogs(userItem.user_id);
  };

  const handleCleanupExpired = async () => {
    if (!confirm('Remover todos os logs expirados (mais de 30 dias após exclusão)?')) return;
    
    setCleaning(true);
    try {
      const result = await messageLogsAPI.cleanupExpired();
      showAlertMessage('success', result.message);
      loadUsersWithLogs();
      if (selectedUser) {
        loadUserLogs(selectedUser.user_id);
      }
    } catch (error) {
      console.error('Erro ao limpar logs:', error);
      showAlertMessage('error', 'Erro ao limpar logs expirados');
    } finally {
      setCleaning(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Filtrar usuários
  const filteredUsers = usersWithLogs.filter(u =>
    u.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    u.email?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Alert */}
        {alert.show && (
          <div className={`fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg ${
            alert.type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
          }`}>
            {alert.message}
          </div>
        )}

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <FileText className="text-blue-600" />
                Log de Conversas
              </h1>
              <p className="text-sm text-gray-600">
                Registro de todas as mensagens excluídas (retenção de 30 dias)
              </p>
            </div>
          </div>
          
          <Button
            onClick={handleCleanupExpired}
            disabled={cleaning}
            variant="outline"
            className="text-red-600 border-red-200 hover:bg-red-50"
          >
            {cleaning ? (
              <RefreshCw size={16} className="mr-2 animate-spin" />
            ) : (
              <Trash2 size={16} className="mr-2" />
            )}
            Limpar Expirados
          </Button>
        </div>

        {/* Aviso de Compliance */}
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-start gap-3">
            <AlertTriangle className="text-amber-500 mt-0.5" size={20} />
            <div>
              <p className="font-medium text-amber-800">Aviso de Compliance</p>
              <p className="text-sm text-amber-700 mt-1">
                Este log mantém registro de todas as mensagens e arquivos compartilhados entre usuários, 
                mesmo após exclusão. Os registros são mantidos por 30 dias após a data de exclusão 
                para fins de auditoria e compliance.
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-6">
          {/* Lista de Usuários */}
          <div className="col-span-4">
            <Card className="h-[calc(100vh-280px)]">
              <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  <User size={18} />
                  Usuários
                </CardTitle>
                {/* Busca */}
                <div className="relative mt-2">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={16} />
                  <input
                    type="text"
                    placeholder="Buscar usuário..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </CardHeader>
              <CardContent className="overflow-y-auto h-[calc(100%-120px)]">
                {loading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                    <p className="mt-2 text-sm text-gray-500">Carregando...</p>
                  </div>
                ) : filteredUsers.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <MessageCircle size={32} className="mx-auto mb-2 text-gray-300" />
                    <p className="text-sm">Nenhum log de mensagem encontrado</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {filteredUsers.map(u => (
                      <div
                        key={u.user_id}
                        onClick={() => handleSelectUser(u)}
                        className={`p-3 rounded-lg cursor-pointer transition-colors ${
                          selectedUser?.user_id === u.user_id
                            ? 'bg-blue-50 border border-blue-200'
                            : 'hover:bg-gray-50 border border-transparent'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-gray-900 truncate">{u.full_name}</p>
                            <p className="text-xs text-gray-500 truncate">{u.email}</p>
                          </div>
                          <ChevronRight size={16} className="text-gray-400" />
                        </div>
                        <div className="flex gap-4 mt-2 text-xs text-gray-500">
                          <span className="flex items-center gap-1">
                            <MessageCircle size={12} />
                            {u.total_messages} msgs
                          </span>
                          <span className="flex items-center gap-1">
                            <Paperclip size={12} />
                            {u.total_attachments} anexos
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Detalhes do Usuário */}
          <div className="col-span-8">
            <Card className="h-[calc(100vh-280px)]">
              <CardContent className="p-0 h-full overflow-y-auto">
                {!selectedUser ? (
                  <div className="flex items-center justify-center h-full text-gray-500">
                    <div className="text-center">
                      <User size={48} className="mx-auto mb-2 text-gray-300" />
                      <p>Selecione um usuário para ver os logs</p>
                    </div>
                  </div>
                ) : loadingLogs ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                      <p className="mt-2 text-sm text-gray-500">Carregando logs...</p>
                    </div>
                  </div>
                ) : userLogs ? (
                  <div className="p-4">
                    {/* Header do usuário */}
                    <div className="mb-4 pb-4 border-b">
                      <h3 className="font-bold text-lg text-gray-900">{userLogs.user_name}</h3>
                      <p className="text-sm text-gray-500">{userLogs.user_email}</p>
                      <div className="flex gap-6 mt-2 text-sm">
                        <span className="text-gray-600">
                          <strong>{userLogs.total_messages}</strong> mensagens registradas
                        </span>
                        <span className="text-gray-600">
                          <strong>{userLogs.total_attachments}</strong> anexos
                        </span>
                        {userLogs.date_range && (
                          <span className="text-gray-600">
                            <Calendar size={14} className="inline mr-1" />
                            {formatDate(userLogs.date_range.start)} - {formatDate(userLogs.date_range.end)}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Conversas */}
                    {userLogs.conversations?.length === 0 ? (
                      <div className="text-center py-8 text-gray-500">
                        <p>Nenhuma conversa registrada</p>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {userLogs.conversations?.map((conv, idx) => (
                          <div key={idx} className="border rounded-lg overflow-hidden">
                            {/* Header da conversa */}
                            <div 
                              className="bg-gray-50 p-3 flex items-center justify-between cursor-pointer hover:bg-gray-100"
                              onClick={() => setShowConversation(showConversation === idx ? null : idx)}
                            >
                              <div>
                                <p className="font-medium text-gray-900">
                                  Conversa com: {conv.other_user_name}
                                </p>
                                <p className="text-xs text-gray-500">{conv.other_user_email}</p>
                              </div>
                              <div className="flex items-center gap-4 text-sm text-gray-500">
                                <span>{conv.messages?.length || 0} mensagens</span>
                                <span>{conv.total_attachments || 0} anexos</span>
                                <ChevronRight 
                                  size={16} 
                                  className={`transition-transform ${showConversation === idx ? 'rotate-90' : ''}`}
                                />
                              </div>
                            </div>
                            
                            {/* Mensagens da conversa */}
                            {showConversation === idx && (
                              <div className="p-3 space-y-3 max-h-96 overflow-y-auto">
                                {conv.messages?.map((msg, msgIdx) => {
                                  const isFromSelectedUser = msg.sender_id === userLogs.user_id;
                                  return (
                                    <div key={msgIdx} className={`flex ${isFromSelectedUser ? 'justify-end' : 'justify-start'}`}>
                                      <div className={`max-w-[70%] rounded-lg p-3 ${
                                        isFromSelectedUser 
                                          ? 'bg-blue-50 border border-blue-100' 
                                          : 'bg-gray-50 border border-gray-100'
                                      }`}>
                                        <div className="flex items-center gap-2 mb-1">
                                          <span className="text-xs font-medium text-gray-700">
                                            {isFromSelectedUser ? msg.sender_name : msg.sender_name}
                                          </span>
                                          <span className="text-xs text-gray-400">
                                            {formatDate(msg.created_at)}
                                          </span>
                                        </div>
                                        
                                        {msg.content && (
                                          <p className="text-sm text-gray-800 whitespace-pre-wrap">{msg.content}</p>
                                        )}
                                        
                                        {msg.attachments?.length > 0 && (
                                          <div className="mt-2 space-y-1">
                                            {msg.attachments.map((att, attIdx) => (
                                              <a
                                                key={attIdx}
                                                href={uploadAPI.getUrl(att.url)}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="flex items-center gap-2 text-xs text-blue-600 hover:underline"
                                              >
                                                {att.type === 'image' ? (
                                                  <>
                                                    <img 
                                                      src={uploadAPI.getUrl(att.url)} 
                                                      alt={att.filename}
                                                      className="w-20 h-20 object-cover rounded"
                                                    />
                                                  </>
                                                ) : (
                                                  <>
                                                    <FileText size={14} />
                                                    {att.filename}
                                                  </>
                                                )}
                                              </a>
                                            ))}
                                          </div>
                                        )}
                                        
                                        {msg.deleted_at && (
                                          <p className="text-xs text-red-500 mt-1">
                                            Excluída em: {formatDate(msg.deleted_at)}
                                          </p>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default MessageLogs;
