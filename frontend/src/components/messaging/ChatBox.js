import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Send, Paperclip, Image, FileText, User, Trash2, MoreVertical } from 'lucide-react';
import { messagesAPI, uploadAPI, getWebSocketUrl } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';

export const ChatBox = ({ connection, onClose, onMessageReceived }) => {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [deletingMessage, setDeletingMessage] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const wsRef = useRef(null);
  const menuRef = useRef(null);
  const isMountedRef = useRef(true);
  const reconnectTimeoutRef = useRef(null);
  
  // Refs para evitar closure issues - sempre terão os valores atuais
  const connectionRef = useRef(connection);
  const userRef = useRef(user);
  const onMessageReceivedRef = useRef(onMessageReceived);
  
  // Atualizar refs quando os valores mudarem
  useEffect(() => {
    connectionRef.current = connection;
  }, [connection]);
  
  useEffect(() => {
    userRef.current = user;
  }, [user]);
  
  useEffect(() => {
    onMessageReceivedRef.current = onMessageReceived;
  }, [onMessageReceived]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadMessages = async () => {
    try {
      const data = await messagesAPI.getMessages(connection.id);
      setMessages(data);
    } catch (error) {
      console.error('Erro ao carregar mensagens:', error);
    } finally {
      setLoading(false);
    }
  };

  // WebSocket setup
  useEffect(() => {
    isMountedRef.current = true;
    let ws = null;
    let pingInterval = null;
    
    const connect = () => {
      if (!isMountedRef.current) return;
      
      const wsUrl = getWebSocketUrl();
      if (!wsUrl || wsUrl.includes('null')) {
        console.log('ChatBox WebSocket: URL inválida');
        return;
      }

      console.log('ChatBox WebSocket: Conectando...');
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) {
          ws.close();
          return;
        }
        console.log('ChatBox WebSocket: Conectado!');
        setWsConnected(true);
        
        // Iniciar ping para manter conexão viva
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        if (event.data === 'pong') return;

        try {
          const data = JSON.parse(event.data);
          console.log('ChatBox WebSocket: Mensagem recebida:', data.type);
          
          if (data.type === 'new_message' && data.message) {
            const msg = data.message;
            // USAR REFS para obter valores ATUAIS (evita closure issue)
            const currentConnection = connectionRef.current;
            const currentUser = userRef.current;
            
            // Verificar se a mensagem é do outro usuário para mim
            const isFromOtherUser = msg.sender_id === currentConnection?.user_id;
            const isToMe = msg.receiver_id === currentUser?.id;
            
            console.log('ChatBox WebSocket: sender_id:', msg.sender_id);
            console.log('ChatBox WebSocket: connection.user_id:', currentConnection?.user_id);
            console.log('ChatBox WebSocket: receiver_id:', msg.receiver_id);
            console.log('ChatBox WebSocket: user.id:', currentUser?.id);
            console.log('ChatBox WebSocket: isFromOtherUser:', isFromOtherUser, 'isToMe:', isToMe);
            
            if (isFromOtherUser && isToMe) {
              console.log('ChatBox WebSocket: ✓ Adicionando mensagem ao chat!');
              // Verificar se a mensagem já existe para evitar duplicatas
              setMessages(prev => {
                const exists = prev.some(m => m.id === msg.id);
                if (exists) {
                  console.log('ChatBox WebSocket: Mensagem já existe, ignorando duplicata');
                  return prev;
                }
                return [...prev, msg];
              });
              onMessageReceivedRef.current?.(msg);
            } else {
              console.log('ChatBox WebSocket: ✗ Mensagem filtrada (não é para este chat)');
            }
          } else if (data.type === 'message_deleted') {
            setMessages(prev => prev.filter(m => m.id !== data.message_id));
          } else if (data.type === 'conversation_deleted') {
            const currentConnection = connectionRef.current;
            if (data.connection_id === currentConnection?.id) {
              setMessages([]);
            }
          }
        } catch (error) {
          console.error('ChatBox WebSocket: Erro ao parsear', error);
        }
      };

      ws.onclose = (event) => {
        console.log('ChatBox WebSocket: Desconectado, código:', event.code);
        setWsConnected(false);
        wsRef.current = null;
        
        if (pingInterval) {
          clearInterval(pingInterval);
          pingInterval = null;
        }
        
        // Reconectar apenas se o componente ainda está montado e não foi fechamento intencional
        if (isMountedRef.current && event.code !== 1000) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('ChatBox WebSocket: Reconectando...');
            connect();
          }, 3000);
        }
      };

      ws.onerror = (error) => {
        console.error('ChatBox WebSocket: Erro', error);
      };
    };

    // Carregar mensagens e conectar WebSocket
    loadMessages();
    connect();

    // Cleanup quando o componente desmonta
    return () => {
      console.log('ChatBox: Desmontando componente');
      isMountedRef.current = false;
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      
      if (pingInterval) {
        clearInterval(pingInterval);
      }
      
      if (wsRef.current) {
        wsRef.current.close(1000); // Fechamento normal
        wsRef.current = null;
      }
    };
  }, [connection.id]); // Só reconectar se mudar de conversa (connection.id)

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fechar menu ao clicar fora
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSend = async () => {
    if (!newMessage.trim()) return;

    setSending(true);
    try {
      const message = await messagesAPI.send(connection.user_id, newMessage.trim());
      // Verificar se a mensagem já existe para evitar duplicatas
      setMessages(prev => {
        const exists = prev.some(m => m.id === message.id);
        if (exists) return prev;
        return [...prev, message];
      });
      setNewMessage('');
    } catch (error) {
      console.error('Erro ao enviar mensagem:', error);
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const isImage = file.type.startsWith('image/');
    const isPDF = file.type === 'application/pdf';

    if (!isImage && !isPDF) {
      alert('Apenas imagens e PDFs são permitidos');
      return;
    }

    setUploading(true);
    try {
      // Determina o tipo de arquivo para o upload (imagem vai para /user, documento para /doc)
      const fileType = isImage ? 'profile' : 'document';
      const uploadResult = await uploadAPI.upload(file, fileType);
      
      const attachment = {
        type: isImage ? 'image' : 'pdf',
        url: uploadResult.url,
        filename: file.name,
        size: file.size
      };

      const message = await messagesAPI.send(
        connection.user_id,
        isImage ? '' : `📎 ${file.name}`,
        [attachment]
      );
      
      // Verificar se a mensagem já existe para evitar duplicatas
      setMessages(prev => {
        const exists = prev.some(m => m.id === message.id);
        if (exists) return prev;
        return [...prev, message];
      });
    } catch (error) {
      console.error('Erro ao enviar arquivo:', error);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDeleteMessage = async (messageId) => {
    if (!confirm('Excluir esta mensagem?')) return;
    
    setDeletingMessage(messageId);
    try {
      await messagesAPI.deleteMessage(messageId);
      setMessages(prev => prev.filter(m => m.id !== messageId));
    } catch (error) {
      console.error('Erro ao excluir mensagem:', error);
      alert('Erro ao excluir mensagem');
    } finally {
      setDeletingMessage(null);
    }
  };

  const handleDeleteConversation = async () => {
    if (!confirm('Excluir toda a conversa? Esta ação não pode ser desfeita.')) return;
    
    try {
      await messagesAPI.deleteConversation(connection.id);
      setMessages([]);
      setShowMenu(false);
    } catch (error) {
      console.error('Erro ao excluir conversa:', error);
      alert('Erro ao excluir conversa');
    }
  };

  const formatTime = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Hoje';
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Ontem';
    } else {
      return date.toLocaleDateString('pt-BR');
    }
  };

  // Agrupar mensagens por data
  const groupedMessages = messages.reduce((groups, message) => {
    const date = formatDate(message.created_at);
    if (!groups[date]) {
      groups[date] = [];
    }
    groups[date].push(message);
    return groups;
  }, {});

  return (
    <div className="fixed bottom-4 right-4 w-80 h-[450px] bg-white rounded-lg shadow-2xl border flex flex-col z-50">
      {/* Header */}
      <div className="flex items-center gap-3 p-3 border-b bg-blue-600 text-white rounded-t-lg">
        <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center overflow-hidden">
          {connection.foto_url ? (
            <img
              src={uploadAPI.getUrl(connection.foto_url)}
              alt={connection.full_name}
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={16} className="text-white" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate">{connection.full_name}</p>
          <p className="text-xs text-blue-100 truncate flex items-center gap-1">
            {connection.headline || ''}
            {wsConnected && <span className="w-2 h-2 bg-green-400 rounded-full" title="Online"></span>}
          </p>
        </div>
        
        {/* Menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="p-1 hover:bg-white/20 rounded transition-colors"
          >
            <MoreVertical size={18} />
          </button>
          
          {showMenu && (
            <div className="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border py-1 min-w-[150px] z-10">
              <button
                onClick={handleDeleteConversation}
                className="w-full px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
              >
                <Trash2 size={14} />
                Excluir conversa
              </button>
            </div>
          )}
        </div>
        
        <button
          onClick={onClose}
          className="p-1 hover:bg-white/20 rounded transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 bg-gray-50">
        {loading ? (
          <div className="text-center text-gray-500 py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto"></div>
          </div>
        ) : messages.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            <p className="text-sm">Nenhuma mensagem ainda</p>
            <p className="text-xs mt-1">Envie a primeira mensagem!</p>
          </div>
        ) : (
          Object.entries(groupedMessages).map(([date, msgs]) => (
            <div key={date}>
              <div className="flex items-center justify-center mb-3">
                <span className="text-xs text-gray-500 bg-white px-2 py-1 rounded-full shadow-sm">
                  {date}
                </span>
              </div>
              <div className="space-y-2">
                {msgs.map(msg => {
                  const isMe = msg.sender_id === user?.id;
                  return (
                    <div
                      key={msg.id}
                      className={`flex ${isMe ? 'justify-end' : 'justify-start'} group`}
                    >
                      <div className="relative">
                        <div
                          className={`max-w-[200px] rounded-lg px-3 py-2 ${
                            isMe
                              ? 'bg-blue-600 text-white rounded-br-none'
                              : 'bg-white text-gray-800 rounded-bl-none shadow-sm'
                          }`}
                        >
                          {/* Anexos */}
                          {msg.attachments?.length > 0 && (
                            <div className="mb-1">
                              {msg.attachments.map((att, idx) => (
                                <div key={idx}>
                                  {att.type === 'image' ? (
                                    <img
                                      src={uploadAPI.getUrl(att.url)}
                                      alt={att.filename}
                                      className="max-w-full rounded cursor-pointer hover:opacity-90"
                                      onClick={() => window.open(uploadAPI.getUrl(att.url), '_blank')}
                                    />
                                  ) : (
                                    <a
                                      href={uploadAPI.getUrl(att.url)}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className={`flex items-center gap-2 p-2 rounded ${
                                        isMe ? 'bg-blue-500 hover:bg-blue-400' : 'bg-gray-100 hover:bg-gray-200'
                                      }`}
                                    >
                                      <FileText size={16} />
                                      <span className="text-xs truncate">{att.filename}</span>
                                    </a>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                          {/* Texto */}
                          {msg.content && (
                            <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
                          )}
                          <p className={`text-xs mt-1 ${isMe ? 'text-blue-100' : 'text-gray-400'}`}>
                            {formatTime(msg.created_at)}
                          </p>
                        </div>
                        
                        {/* Botão de excluir */}
                        {isMe && (
                          <button
                            onClick={() => handleDeleteMessage(msg.id)}
                            disabled={deletingMessage === msg.id}
                            className="absolute -left-6 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Excluir mensagem"
                          >
                            {deletingMessage === msg.id ? (
                              <div className="w-4 h-4 border-2 border-gray-300 border-t-red-500 rounded-full animate-spin"></div>
                            ) : (
                              <Trash2 size={14} />
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t bg-white rounded-b-lg">
        <div className="flex items-end gap-2">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept="image/*,.pdf"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
            title="Anexar arquivo"
          >
            {uploading ? (
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
            ) : (
              <Paperclip size={20} />
            )}
          </button>
          <textarea
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Digite sua mensagem..."
            className="flex-1 resize-none border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 max-h-20"
            rows={1}
          />
          <Button
            onClick={handleSend}
            disabled={!newMessage.trim() || sending}
            size="sm"
            className="bg-blue-600 hover:bg-blue-700"
          >
            <Send size={16} />
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ChatBox;
