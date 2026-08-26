import { useEffect, useState } from 'react';
import { Search, Shield } from 'lucide-react';

import { Modal } from '@/components/Modal';
import { useAuth } from '@/contexts/AuthContext';
import { extractErrorMessage } from '@/utils/errorHandler';
import {
  searchImpersonationUsers,
  startImpersonationSession,
  stopImpersonationSession,
} from '@/services/impersonationSession';

const ROLE_LABELS = {
  gerente: 'Gerente',
  admin: 'Administrador',
  admin_teste: 'Administrador',
  secretario: 'Secretário(a)',
  diretor: 'Diretor(a)',
  coordenador: 'Coordenador(a)',
  apoio_pedagogico: 'Apoio Pedagógico',
  auxiliar_secretaria: 'Auxiliar de Secretaria',
  professor: 'Professor(a)',
  responsavel: 'Responsável(is)',
  ass_social: 'Ass. Social',
  ass_social_2: 'Ass. Social',
  agente_vacinas: 'Agente de Vacinas',
  semed: 'SEMED',
  semed1: 'Tutor',
  semed2: 'Analista',
  semed3: 'Administração',
};

const roleLabel = (role) => ROLE_LABELS[role] || role;

export const ImpersonationControl = () => {
  const { user } = useAuth();
  const impersonation = user?.impersonation?.active ? user.impersonation : null;
  const canStart = user?.role === 'super_admin' && !impersonation;

  const [open, setOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [target, setTarget] = useState(null);
  const [activeRole, setActiveRole] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState('');

  const targetRoles = target
    ? Array.from(new Set([target.role, ...(target.roles || [])]))
      .filter((role) => role && role !== 'super_admin')
    : [];

  const stopTest = async () => {
    if (!impersonation || stopping) return;
    setStopping(true);
    setError('');
    try {
      await stopImpersonationSession();
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível encerrar o modo de teste.'));
      setStopping(false);
    }
  };

  // O Layout canônico possui um botão Sair que revoga todas as sessões do
  // usuário efetivo. Durante impersonação interceptamos esse clique em capture
  // phase e transformamos "Sair" em "Encerrar teste", preservando as sessões
  // legítimas do usuário testado.
  useEffect(() => {
    if (!impersonation) return undefined;

    const captureLogout = (event) => {
      const targetElement = event.target instanceof Element ? event.target : null;
      const logoutButton = targetElement?.closest?.('[data-testid="logout-button"]');
      if (!logoutButton) return;
      event.preventDefault();
      event.stopPropagation();
      stopTest();
    };

    document.addEventListener('click', captureLogout, true);
    return () => document.removeEventListener('click', captureLogout, true);
  }, [impersonation, stopping]);

  // Busca server-side global. Não reutiliza GET /users, pois esse endpoint segue
  // o tenant ativo da gestão administrativa e pode omitir contas de outros escopos.
  useEffect(() => {
    if (!open || target) return undefined;

    const term = searchTerm.trim();
    if (term.length < 2) {
      setSearchResults([]);
      setSearching(false);
      return undefined;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setSearching(true);
      setError('');
      try {
        const results = await searchImpersonationUsers(term, 20);
        if (!cancelled) setSearchResults(Array.isArray(results) ? results : []);
      } catch (err) {
        if (!cancelled) {
          setSearchResults([]);
          setError(extractErrorMessage(err, 'Não foi possível pesquisar usuários.'));
        }
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, searchTerm, target]);

  const openDialog = () => {
    setOpen(true);
    setError('');
    setPassword('');
    setSearchTerm('');
    setSearchResults([]);
    setTarget(null);
    setActiveRole('');
    setSearching(false);
  };

  const changeSearchTerm = (value) => {
    setSearchTerm(value);
    setTarget(null);
    setActiveRole('');
    setSearchResults([]);
    setError('');
  };

  const selectTarget = (selected) => {
    const roles = Array.from(new Set([selected?.role, ...(selected?.roles || [])]))
      .filter((role) => role && role !== 'super_admin');
    setTarget(selected);
    setActiveRole(roles.includes(selected?.role) ? selected.role : (roles[0] || ''));
    setSearchTerm(selected?.full_name || selected?.email || '');
    setSearchResults([]);
    setError('');
  };

  const startTest = async (event) => {
    event.preventDefault();
    if (!target?.id || !activeRole || !password) {
      setError('Selecione o usuário, o perfil e confirme sua senha de Super Administrador.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await startImpersonationSession({
        targetUserId: target.id,
        activeRole,
        password,
      });
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível iniciar o modo de teste.'));
      setSubmitting(false);
    }
  };

  return (
    <>
      {canStart && (
        <button
          type="button"
          onClick={openDialog}
          className="fixed left-4 bottom-16 z-[65] inline-flex items-center gap-2 rounded-full bg-indigo-700 px-4 py-2.5 text-sm font-semibold text-white shadow-lg hover:bg-indigo-800"
          title="Entrar temporariamente como outro usuário para testar suas permissões"
          data-testid="open-impersonation-button"
        >
          <Shield size={18} />
          Testar como usuário
        </button>
      )}

      {impersonation && (
        <div
          className="fixed bottom-14 left-0 right-0 z-[70] border-y border-amber-300 bg-amber-100 px-4 py-2 shadow-lg"
          data-testid="impersonation-banner"
        >
          <div className="mx-auto flex max-w-7xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-amber-950">
              <strong>Modo de teste ativo:</strong>{' '}
              você está atuando como <strong>{impersonation.subject?.name || user?.full_name}</strong>
              {' '}({roleLabel(impersonation.subject?.role || user?.role)}). Todas as ações são auditadas com
              {' '}<strong>{impersonation.actor?.name || 'Super Administrador'}</strong> como ator real.
              {error && <span className="ml-2 font-medium text-red-700">{error}</span>}
            </div>
            <button
              type="button"
              onClick={stopTest}
              disabled={stopping}
              className="shrink-0 rounded-lg bg-amber-900 px-4 py-1.5 text-sm font-semibold text-white hover:bg-amber-950 disabled:bg-gray-500"
              data-testid="stop-impersonation-button"
            >
              {stopping ? 'Encerrando...' : 'Encerrar teste'}
            </button>
          </div>
        </div>
      )}

      <Modal
        isOpen={open}
        onClose={() => !submitting && setOpen(false)}
        title="Testar como usuário"
      >
        <form onSubmit={startTest} className="space-y-4">
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
            Sessão temporária para testes. Pesquise qualquer usuário ativo do SIGESC por nome ou e-mail. A senha original do usuário é preservada e as ações ficam atribuídas ao Super Administrador.
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">Usuário a testar *</label>
            <div className="relative">
              <Search
                size={18}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="search"
                value={searchTerm}
                onChange={(event) => changeSearchTerm(event.target.value)}
                disabled={submitting}
                placeholder="Digite o nome ou e-mail do usuário"
                autoComplete="off"
                className="w-full rounded-lg border border-gray-300 py-2 pl-10 pr-3"
                data-testid="impersonation-user-search"
              />
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Digite pelo menos 2 caracteres. A busca é global e não se limita a professores ou à mantenedora selecionada.
            </p>

            {!target && searchTerm.trim().length >= 2 && (
              <div
                className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-sm"
                data-testid="impersonation-search-results"
              >
                {searching && (
                  <div className="px-3 py-3 text-sm text-gray-500">Pesquisando...</div>
                )}
                {!searching && searchResults.length === 0 && (
                  <div className="px-3 py-3 text-sm text-gray-500">Nenhum usuário encontrado.</div>
                )}
                {!searching && searchResults.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => selectTarget(item)}
                    className="block w-full border-b border-gray-100 px-3 py-2.5 text-left last:border-b-0 hover:bg-indigo-50"
                    data-testid={`impersonation-result-${item.id}`}
                  >
                    <div className="font-medium text-gray-900">{item.full_name || item.email}</div>
                    <div className="mt-0.5 text-xs text-gray-500">
                      {item.email || 'Sem e-mail'} · {(item.roles || [item.role]).filter(Boolean).map(roleLabel).join(', ')}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {target && (
              <div className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3" data-testid="impersonation-selected-user">
                <div className="text-sm font-semibold text-emerald-950">{target.full_name || target.email}</div>
                <div className="mt-0.5 text-xs text-emerald-800">{target.email || 'Sem e-mail'}</div>
                <button
                  type="button"
                  onClick={() => changeSearchTerm('')}
                  disabled={submitting}
                  className="mt-2 text-xs font-medium text-emerald-900 underline"
                >
                  Escolher outro usuário
                </button>
              </div>
            )}
          </div>

          {target && (
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">Perfil ativo no teste *</label>
              <select
                value={activeRole}
                onChange={(event) => setActiveRole(event.target.value)}
                disabled={submitting}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
                data-testid="impersonation-role-select"
              >
                {targetRoles.map((role) => (
                  <option key={role} value={role}>{roleLabel(role)}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">
              Confirme sua senha de Super Administrador *
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
              data-testid="impersonation-superadmin-password"
            />
            <p className="mt-1 text-xs text-gray-500">A senha serve apenas para autorizar esta sessão e não é armazenada.</p>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" data-testid="impersonation-error">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={submitting}
              className="rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={submitting || !target}
              className="rounded-lg bg-indigo-700 px-4 py-2 font-medium text-white hover:bg-indigo-800 disabled:bg-gray-400"
              data-testid="start-impersonation-button"
            >
              {submitting ? 'Entrando...' : 'Iniciar teste'}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
};
