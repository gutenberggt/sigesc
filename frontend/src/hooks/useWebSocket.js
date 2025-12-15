import { useState, useEffect, useCallback, useRef } from 'react';
import { getWebSocketUrl } from '@/services/api';

export const useWebSocket = (onMessage, onConnectionChange) => {
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 3000;

  const connect = useCallback(() => {
    try {
      const wsUrl = getWebSocketUrl();
      if (!wsUrl || wsUrl.includes('null')) {
        console.log('WebSocket: Token não disponível');
        return;
      }

      console.log('WebSocket: Conectando...');
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket: Conectado!');
        setIsConnected(true);
        setReconnectAttempts(0);
        onConnectionChange?.(true);

        // Iniciar ping para manter conexão viva
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        if (event.data === 'pong') {
          // Resposta do ping, ignorar
          return;
        }

        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket: Mensagem recebida', data.type);
          onMessage?.(data);
        } catch (error) {
          console.error('WebSocket: Erro ao parsear mensagem', error);
        }
      };

      ws.onclose = (event) => {
        console.log('WebSocket: Desconectado', event.code);
        setIsConnected(false);
        onConnectionChange?.(false);
        wsRef.current = null;

        // Limpar ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Tentar reconectar se não foi fechamento intencional
        if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
          console.log(`WebSocket: Reconectando em ${reconnectDelay}ms... (tentativa ${reconnectAttempts + 1})`);
          reconnectTimeoutRef.current = setTimeout(() => {
            setReconnectAttempts(prev => prev + 1);
            connect();
          }, reconnectDelay);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket: Erro', error);
      };
    } catch (error) {
      console.error('WebSocket: Erro ao conectar', error);
    }
  }, [onMessage, onConnectionChange, reconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000);
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  const sendMessage = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, []);

  return {
    isConnected,
    sendMessage,
    reconnect: connect,
    disconnect
  };
};

export default useWebSocket;
