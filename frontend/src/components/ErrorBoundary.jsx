import React from 'react';

/**
 * ErrorBoundary global — captura erros de renderização do React.
 *
 * Em produção (build minificado) o React mostra apenas códigos numéricos
 * como "Minified React error #310". Este boundary:
 *  1. Captura o erro real + a component stack ANTES da minificação.
 *  2. Loga tudo no console (utilizável via DevTools mesmo em produção).
 *  3. Persiste o último erro em sessionStorage para inspeção posterior.
 *  4. Mostra UI amigável com botão para recarregar.
 *
 * O usuário pode pedir para ver detalhes — eles vão pro console + UI.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Log estruturado — sobrevive ao bundle minificado
    const payload = {
      message: error?.message || String(error),
      stack: error?.stack || null,
      componentStack: errorInfo?.componentStack || null,
      url: typeof window !== 'undefined' ? window.location.pathname : null,
      ts: new Date().toISOString(),
    };

    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] React renderização falhou:', payload);

    // Persiste para inspeção posterior (DevTools > Application > sessionStorage)
    try {
      sessionStorage.setItem('lastReactError', JSON.stringify(payload));
    } catch (e) {
      // Ignora se sessionStorage não estiver disponível
    }

    this.setState({ errorInfo });
  }

  handleReload = () => {
    window.location.reload();
  };

  handleHome = () => {
    window.location.href = '/';
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const { error, errorInfo } = this.state;
    const componentStack = errorInfo?.componentStack || '';
    const errorMessage = error?.message || String(error);

    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#f8fafc',
          padding: 24,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}
      >
        <div
          style={{
            background: '#fff',
            borderRadius: 12,
            padding: 32,
            maxWidth: 720,
            width: '100%',
            boxShadow: '0 10px 40px rgba(0,0,0,0.08)',
            border: '1px solid #e2e8f0',
          }}
        >
          <h1 style={{ margin: 0, fontSize: 22, color: '#0f172a' }}>
            Algo deu errado nesta tela
          </h1>
          <p style={{ color: '#475569', lineHeight: 1.6, marginTop: 8 }}>
            Tivemos um erro inesperado de renderização. Você pode tentar recarregar a página
            ou voltar ao início. Se o problema persistir, copie os detalhes abaixo e envie
            ao suporte.
          </p>

          <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
            <button
              data-testid="error-reload-btn"
              onClick={this.handleReload}
              style={{
                background: '#1e3a8a',
                color: '#fff',
                border: 'none',
                padding: '10px 20px',
                borderRadius: 8,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Recarregar página
            </button>
            <button
              data-testid="error-home-btn"
              onClick={this.handleHome}
              style={{
                background: '#fff',
                color: '#0f172a',
                border: '1px solid #cbd5e1',
                padding: '10px 20px',
                borderRadius: 8,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Ir ao início
            </button>
          </div>

          <details style={{ marginTop: 24 }}>
            <summary style={{ cursor: 'pointer', color: '#475569', fontSize: 13 }}>
              Detalhes técnicos (clique para expandir)
            </summary>
            <pre
              data-testid="error-details"
              style={{
                marginTop: 12,
                background: '#0f172a',
                color: '#e2e8f0',
                padding: 16,
                borderRadius: 8,
                fontSize: 12,
                lineHeight: 1.5,
                overflowX: 'auto',
                maxHeight: 320,
              }}
            >
              {`Erro: ${errorMessage}\nURL: ${typeof window !== 'undefined' ? window.location.pathname : ''}\n\nComponent Stack:${componentStack}`}
            </pre>
          </details>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
