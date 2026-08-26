import { useMemo, useState } from 'react';
import { Shield } from 'lucide-react';

import { Modal } from '@/components/Modal';
import { useAuth } from '@/contexts/AuthContext';
import { usersAPI } from '@/services/api';
import { extractErrorMessage } from '@/utils/errorHandler';
import { startImpersonationSession } from '@/services/impersonationSession';
import { Users as LegacyUsers } from './UsersLegacy';

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
  aluno: 'Estudante',
  responsavel: 'Responsável(is)',
  ass_social: 'Ass. Social',
  ass_social_2: 'Ass. Social',
  agente_vacinas: 'Agente de Vacinas',
  semed: 'SEMED',
  semed1: 'Tutor',
  semed2: 'Analista',
  semed3: 'Administração',
};

export const Users = () => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [users, setUsers] = useState([]);
  const [targetUserId, setTargetUserId] = useState('');
  const [activeRole, setActiveRole] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const canImpersonate = user?.role === 'super_admin' && !user?.impersonation?.active;

  const eligibleUsers = useMemo(
    () => users.filter((item) => {
      const roles = new Set([item.role, ...(item.roles || [])]);
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

  const openImpersonation = async () => {
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

  const handleTargetChange = (id) => {
    setTargetUserId(id);
    const selected = eligibleUsers.find((item) => item.id === id);
    setActiveRole(selected?.role || '');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!targetUserId || !password || !activeRole) {
      setError('Selecione o usuário, o perfil e confirme sua senha de Super Administrador.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await startImpersonationSession({
        targetUserId,
        password,
        activeRole,
      });
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível iniciar o modo de teste.'));
      setSubmitting(false);
    }
  };

  return (
    <>
      <LegacyUsers />

      {canImpersonate && (
        <button
          type="button"
          onClick={openImpersonation}
          className="fixed left-4 bottom-16 z-40 inline-flex items-center gap-2 rounded-full bg-indigo-700 px-4 py-2.5 text-sm font-semibold text-white shadow-lg hover:bg-indigo-800"
          title="Entrar temporariamente como outro usuário para testar seu perfil"
          data-testid="open-impersonation-button"
        >
          <Shield size={18} />
          Testar como usuário
        </button>
      )}

      <Modal
        isOpen={open}
        onClose={() => !submitting && setOpen(false)}
        title="Testar como usuário"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
            Esta é uma sessão temporária de teste. O usuário mantém sua senha original e todas as ações serão registradas com o Super Administrador como ator real.
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">Usuário a testar *</label>
            <select
              value={targetUserId}
              onChange={(event) => handleTargetChange(event.target.value)}
              disabled={loadingUsers || submitting}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
              data-testid="impersonation-target-select"
            >
              <option value="">{loadingUsers ? 'Carregando...' : 'Selecione um usuário'}</option>
              {eligibleUsers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.full_name} — {ROLE_LABELS[item.role] || item.role} — {item.email}
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
                  <option key={role} value={role}>{ROLE_LABELS[role] || role}</option>
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
            <p className="mt-1 text-xs text-gray-500">A senha é usada apenas para autorizar esta sessão e não é armazenada.</p>
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
