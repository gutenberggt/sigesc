import { useEffect, useMemo, useState } from 'react';
import { Shield } from 'lucide-react';

import { Modal } from '@/components/Modal';
import { useAuth } from '@/contexts/AuthContext';
import { usersAPI } from '@/services/api';
import { extractErrorMessage } from '@/utils/errorHandler';
import {
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
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [users, setUsers] = useState([]);
  const [targetUserId, setTargetUserId] = useState('');
  const [activeRole, setActiveRole] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState('');

  const eligibleUsers = useMemo(
    () => users.filter((item) => {
      const roles = new Set([item?.role, ...(item?.roles || [])]);
      return (
        item?.status === 'active'
        && item?.id !== user?.id
        && !roles.has('super_admin')
      );
    }),
    [users, user?.id],
  );

  const target = eligibleUsers.find((item) => item.id === targetUserId) || null;
  const targetRoles = target
    ? Array.from(new Set([target.role, ...(target.roles || [])])).filter((role) => role !== 'super_admin')
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

  const openDialog = async () => {
    setOpen(true);
    setError('');
    setPassword('');
    setTargetUserId('');
    setActiveRole('');
    setLoadingUsers(true);
    try {
      const data = await usersAPI.getAll();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível carregar os usuários.'));
    } finally {
      setLoadingUsers(false);
    }
  };

  const selectTarget = (id) => {
    setTargetUserId(id);
    const selected = eligibleUsers.find((item) => item.id === id);
    setActiveRole(selected?.role || '');
  };

  const startTest = async (event) => {
    event.preventDefault();
    if (!targetUserId || !activeRole || !password) {
      setError('Selecione o usuário, o perfil e confirme sua senha de Super Administrador.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await startImpersonationSession({ targetUserId, activeRole, password });
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
            Sessão temporária para testes. O usuário mantém sua senha original e as ações ficam atribuídas ao Super Administrador, com o usuário testado registrado na trilha de auditoria.
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">Usuário a testar *</label>
            <select
              value={targetUserId}
              onChange={(event) => selectTarget(event.target.value)}
              disabled={loadingUsers || submitting}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
              data-testid="impersonation-target-select"
            >
              <option value="">{loadingUsers ? 'Carregando...' : 'Selecione um usuário'}</option>
              {eligibleUsers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.full_name} — {roleLabel(item.role)} — {item.email}
                </option>
              ))}
            </select>
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
              disabled={submitting || loadingUsers}
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
