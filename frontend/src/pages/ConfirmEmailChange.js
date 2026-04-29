import { useEffect, useState, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { CheckCircle, AlertCircle, RotateCw, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function ConfirmEmailChange() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') || '';
  const [status, setStatus] = useState('loading');
  const [message, setMessage] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [resending, setResending] = useState(false);

  const confirm = useCallback(async () => {
    if (!token) {
      setStatus('error');
      setMessage('Link inválido: token ausente.');
      return;
    }
    setStatus('loading');
    try {
      const res = await fetch(`${API_URL}/api/auth/confirm-email-change`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setStatus('success');
        setNewEmail(data.new_email || '');
        const synced = data.staff_synced ? ' Cadastro de servidor sincronizado.' : '';
        setMessage(`Seu e-mail foi atualizado para ${data.new_email}.${synced}`);
      } else {
        setStatus(res.status === 400 && /expirado/i.test(data.detail || '') ? 'expired' : 'error');
        setMessage(data.detail || 'Não foi possível confirmar a alteração.');
      }
    } catch {
      setStatus('error');
      setMessage('Erro de rede. Tente novamente.');
    }
  }, [token]);

  useEffect(() => { confirm(); }, [confirm]);

  const handleResend = async () => {
    setResending(true);
    try {
      const accessToken = localStorage.getItem('accessToken');
      if (!accessToken) {
        setMessage('Para reenviar, faça login com seu e-mail atual primeiro.');
        setResending(false);
        return;
      }
      const res = await fetch(`${API_URL}/api/auth/resend-email-change`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setStatus('resent');
        setMessage(`Novo link enviado para ${data.new_email}. Verifique sua caixa de entrada (válido por 30 min).`);
      } else {
        setMessage(data.detail || 'Não foi possível reenviar o e-mail.');
      }
    } catch {
      setMessage('Erro de rede ao reenviar.');
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-8" data-testid="confirm-email-card">
        <div className="text-center mb-6">
          <div className="text-2xl font-bold text-blue-700">SIGESC</div>
          <div className="text-xs text-gray-500">Sistema Integrado de Gestão Escolar</div>
        </div>

        {status === 'loading' && (
          <div className="text-center py-8">
            <div className="inline-block w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-gray-700">Confirmando alteração...</p>
          </div>
        )}

        {(status === 'success' || status === 'resent') && (
          <div className="text-center" data-testid="confirm-email-success">
            <CheckCircle size={56} className="text-emerald-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              {status === 'success' ? 'Email confirmado!' : 'Link reenviado'}
            </h2>
            <p className="text-gray-600 mb-6">{message}</p>
            <Button onClick={() => navigate('/login')} className="w-full" data-testid="btn-go-login">
              <ArrowLeft size={16} className="mr-2" />
              Ir para o login
            </Button>
          </div>
        )}

        {(status === 'error' || status === 'expired') && (
          <div className="text-center" data-testid="confirm-email-error">
            <AlertCircle size={56} className="text-amber-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              {status === 'expired' ? 'Link expirado' : 'Não foi possível confirmar'}
            </h2>
            <p className="text-gray-600 mb-6">{message}</p>
            <div className="space-y-2">
              {status === 'expired' && (
                <Button
                  onClick={handleResend}
                  disabled={resending}
                  className="w-full"
                  data-testid="btn-resend-email"
                >
                  <RotateCw size={16} className={`mr-2 ${resending ? 'animate-spin' : ''}`} />
                  {resending ? 'Reenviando...' : 'Reenviar link de confirmação'}
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => navigate('/login')}
                className="w-full"
                data-testid="btn-back-login"
              >
                Voltar ao login
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
