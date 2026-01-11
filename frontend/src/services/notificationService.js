/**
 * Serviço de Notificações Push para o SIGESC
 * 
 * Gerencia notificações do navegador para alertar o usuário sobre:
 * - Sincronização concluída
 * - Erros de sincronização
 * - Mudanças de status de conexão
 */

class NotificationService {
  constructor() {
    this.permission = 'default';
    this.isSupported = 'Notification' in window;
  }

  /**
   * Verifica se notificações são suportadas
   */
  checkSupport() {
    if (!this.isSupported) {
      console.warn('[Notifications] Notificações não são suportadas neste navegador');
      return false;
    }
    return true;
  }

  /**
   * Solicita permissão para enviar notificações
   */
  async requestPermission() {
    if (!this.checkSupport()) return false;

    try {
      const permission = await Notification.requestPermission();
      this.permission = permission;
      
      if (permission === 'granted') {
        console.log('[Notifications] Permissão concedida');
        return true;
      } else if (permission === 'denied') {
        console.log('[Notifications] Permissão negada');
        return false;
      }
      
      return false;
    } catch (error) {
      console.error('[Notifications] Erro ao solicitar permissão:', error);
      return false;
    }
  }

  /**
   * Verifica se tem permissão para notificar
   */
  hasPermission() {
    return this.isSupported && Notification.permission === 'granted';
  }

  /**
   * Envia uma notificação
   */
  async send(title, options = {}) {
    if (!this.hasPermission()) {
      console.log('[Notifications] Sem permissão para notificar');
      return null;
    }

    const defaultOptions = {
      icon: '/icons/icon-192x192.png',
      badge: '/icons/icon-72x72.png',
      vibrate: [200, 100, 200],
      requireInteraction: false,
      ...options
    };

    try {
      // Se tiver Service Worker, usa ele para a notificação
      if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        const registration = await navigator.serviceWorker.ready;
        await registration.showNotification(title, defaultOptions);
        return true;
      } else {
        // Fallback para notificação direta
        const notification = new Notification(title, defaultOptions);
        
        notification.onclick = () => {
          window.focus();
          notification.close();
          if (options.onClick) options.onClick();
        };
        
        // Auto-fecha após 5 segundos
        if (!options.requireInteraction) {
          setTimeout(() => notification.close(), 5000);
        }
        
        return notification;
      }
    } catch (error) {
      console.error('[Notifications] Erro ao enviar notificação:', error);
      return null;
    }
  }

  // ========== Notificações Específicas do SIGESC ==========

  /**
   * Notifica que a sincronização foi concluída com sucesso
   */
  async notifySyncComplete(itemCount = 0) {
    const body = itemCount > 0 
      ? `${itemCount} item(ns) sincronizado(s) com sucesso!`
      : 'Todos os dados foram sincronizados com o servidor.';

    return this.send('SIGESC - Sincronização Concluída', {
      body,
      tag: 'sync-complete',
      data: { type: 'sync_complete' }
    });
  }

  /**
   * Notifica que houve erro na sincronização
   */
  async notifySyncError(errorCount = 1) {
    return this.send('SIGESC - Erro na Sincronização', {
      body: `${errorCount} item(ns) não puderam ser sincronizados. Verifique sua conexão.`,
      tag: 'sync-error',
      requireInteraction: true,
      data: { type: 'sync_error' }
    });
  }

  /**
   * Notifica que a conexão foi restaurada
   */
  async notifyOnline() {
    return this.send('SIGESC - Conexão Restaurada', {
      body: 'Você está online novamente. Seus dados serão sincronizados automaticamente.',
      tag: 'connection-online',
      data: { type: 'online' }
    });
  }

  /**
   * Notifica que a conexão foi perdida
   */
  async notifyOffline() {
    return this.send('SIGESC - Sem Conexão', {
      body: 'Você está offline. Seus dados serão salvos localmente.',
      tag: 'connection-offline',
      data: { type: 'offline' }
    });
  }

  /**
   * Notifica que há itens pendentes de sincronização
   */
  async notifyPendingSync(count) {
    if (count <= 0) return null;
    
    return this.send('SIGESC - Itens Pendentes', {
      body: `Você tem ${count} item(ns) aguardando sincronização.`,
      tag: 'pending-sync',
      data: { type: 'pending_sync', count }
    });
  }
}

// Instância singleton
export const notificationService = new NotificationService();

export default notificationService;
