/**
 * Permission Matrix Page (super_admin only)
 *
 * Exibe a matriz: itens de menu × papéis × ✅/❌
 * A coluna "Visível?" usa as MESMAS funções `visible(c)` declaradas no
 * `Dashboard.js` (compartilhadas via DASHBOARD_MENU_GROUPS), simulando um
 * contexto de permissão por papel. Isso garante que a tabela é sempre o
 * espelho fiel do que cada papel realmente vê no menu.
 */
import { useState, useMemo, useEffect, useCallback } from 'react';
import { Link, Navigate } from 'react-router-dom';
import {
  ArrowLeft, Check, X, Search, Shield, RotateCcw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { permissionOverridesAPI } from '@/services/api';
import { DASHBOARD_MENU_GROUPS } from './Dashboard';

// Papéis observáveis (linhas vivas em produção)
const ROLES = [
  { key: 'super_admin', label: 'S. Adm.', fullLabel: 'Super Admin' },
  { key: 'admin', label: 'Adm.', fullLabel: 'Administrador' },
  { key: 'gerente', label: 'Ger.', fullLabel: 'Gerente' },
  { key: 'admin_teste', label: 'Adm. T', fullLabel: 'Admin Teste' },
  { key: 'secretario', label: 'Sec.', fullLabel: 'Secretário' },
  { key: 'diretor', label: 'Dir.', fullLabel: 'Diretor' },
  { key: 'coordenador', label: 'Coord.', fullLabel: 'Coordenador' },
  { key: 'apoio_pedagogico', label: 'Ap. Pd.', fullLabel: 'Apoio Pedagógico' },
  { key: 'auxiliar_secretaria', label: 'A. Sec.', fullLabel: 'Aux. Secretaria' },
  { key: 'professor', label: 'Prof.', fullLabel: 'Professor' },
  { key: 'ass_social', label: 'A. Soc.', fullLabel: 'Assistente Social' },
  { key: 'aluno', label: 'Alu.', fullLabel: 'Aluno' },
  { key: 'responsavel', label: 'Resp.', fullLabel: 'Responsável' },
];

// Simula o objeto retornado por `usePermissions()` para um dado papel
function makePermissionContext(role) {
  const isSuperAdmin = role === 'super_admin';
  const isGerente = role === 'gerente';
  const isAdmin = role === 'admin' || role === 'admin_teste' || isSuperAdmin || isGerente;
  const isSecretario = role === 'secretario';
  const isDiretor = role === 'diretor';
  const isCoordenador = role === 'coordenador' || role === 'apoio_pedagogico' || role === 'auxiliar_secretaria';
  const isProfessor = role === 'professor';
  const isSemed = ['semed', 'semed1', 'semed2', 'semed3'].includes(role);
  const isSemedFull = role === 'semed3';
  const isAssistenteSocial = role === 'ass_social';
  const isSchoolStaff = isSecretario || isDiretor || isCoordenador;
  const isGlobal = isAdmin || isSemed;
  const isAdminOrSecretary = isAdmin || isSecretario;

  const hasRole = (...roles) => roles.flat().includes(role);

  return {
    role, isSuperAdmin, isGerente, isAdmin, isSecretario, isDiretor,
    isCoordenador, isProfessor, isSemed, isSemedFull, isAssistenteSocial,
    isSchoolStaff, isGlobal, isAdminOrSecretary, hasRole,
  };
}

/** Célula clicável: aplica/remover override.
 *  - default visível + nenhum override → ✅ neutro (cinza/verde claro)
 *  - default oculto + override visible=true → ✅ azul (override permite)
 *  - default visível + override visible=false → ❌ rosa (override bloqueia)
 *  - default oculto + nenhum override → ❌ neutro
 *  Clique alterna o estado. Botão de reset aparece quando há override.
 */
const Cell = ({ defaultVisible, override, onClick, onReset, saving }) => {
  const hasOverride = override !== undefined;
  const effective = hasOverride ? override : defaultVisible;
  let bg = effective ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-50 text-gray-300';
  if (hasOverride) {
    bg = effective
      ? 'bg-blue-100 text-blue-700 ring-2 ring-blue-400'
      : 'bg-rose-100 text-rose-700 ring-2 ring-rose-400';
  }
  return (
    <div className="inline-flex items-center gap-1">
      <button
        type="button"
        disabled={saving}
        onClick={onClick}
        title={
          hasOverride
            ? `Override: ${effective ? 'visível' : 'oculto'} (clique para inverter)`
            : `Default: ${effective ? 'visível' : 'oculto'} (clique para sobrescrever)`
        }
        className={`inline-flex items-center justify-center w-7 h-7 rounded-full transition-all ${bg} ${saving ? 'opacity-50 cursor-wait' : 'hover:scale-110 cursor-pointer'}`}
      >
        {effective ? <Check size={16} strokeWidth={3} /> : <X size={14} />}
      </button>
      {hasOverride && (
        <button
          type="button"
          disabled={saving}
          onClick={onReset}
          title="Reverter ao default (remover override)"
          className="text-gray-300 hover:text-gray-700 transition-colors"
        >
          <RotateCcw size={11} />
        </button>
      )}
    </div>
  );
};

export default function PermissionMatrix() {
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const [hideEmpty, setHideEmpty] = useState(false);
  const [overrides, setOverrides] = useState({}); // chave: `${item_key}|${role}`
  const [savingCell, setSavingCell] = useState(null); // chave da célula em salvamento
  const [toast, setToast] = useState(null);

  // Memoiza contextos por papel para evitar recriar a cada render
  const contexts = useMemo(
    () => Object.fromEntries(ROLES.map(r => [r.key, makePermissionContext(r.key)])),
    []
  );

  const loadOverrides = useCallback(async () => {
    try {
      const data = await permissionOverridesAPI.list();
      const map = {};
      (data?.items || []).forEach(o => {
        map[`${o.item_key}|${o.role}`] = o.visible;
      });
      setOverrides(map);
    } catch (e) {
      // silencioso
    }
  }, []);

  useEffect(() => { loadOverrides(); }, [loadOverrides]);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 2200);
  };

  const handleToggle = async (itemKey, role, defaultVisible, currentOverride) => {
    const cellKey = `${itemKey}|${role}`;
    setSavingCell(cellKey);
    try {
      // Determina o NOVO valor desejado
      // - Se já há override, inverte
      // - Se não há, vira o oposto do default
      const nextVisible = currentOverride !== undefined ? !currentOverride : !defaultVisible;
      await permissionOverridesAPI.set(itemKey, role, nextVisible);
      setOverrides(prev => ({ ...prev, [cellKey]: nextVisible }));
      showToast(`Override aplicado: ${role} → ${nextVisible ? 'visível' : 'oculto'}`);
    } catch (e) {
      showToast('Falha ao salvar override', 'error');
    } finally {
      setSavingCell(null);
    }
  };

  const handleReset = async (itemKey, role) => {
    const cellKey = `${itemKey}|${role}`;
    setSavingCell(cellKey);
    try {
      await permissionOverridesAPI.remove(itemKey, role);
      setOverrides(prev => {
        const next = { ...prev };
        delete next[cellKey];
        return next;
      });
      showToast('Override removido (volta ao default)');
    } catch (e) {
      showToast('Falha ao remover override', 'error');
    } finally {
      setSavingCell(null);
    }
  };

  // Achata todas as categorias × itens em uma única lista anotada
  const rows = useMemo(() => {
    const out = [];
    DASHBOARD_MENU_GROUPS.forEach(group => {
      group.items.forEach(item => {
        const visibilityByRole = {};
        const defaultByRole = {};
        const overrideByRole = {};
        let count = 0;
        ROLES.forEach(r => {
          let defVisible = false;
          try { defVisible = !!item.visible(contexts[r.key]); } catch { defVisible = false; }
          defaultByRole[r.key] = defVisible;
          const ov = overrides[`${item.testId}|${r.key}`];
          overrideByRole[r.key] = ov;
          const effective = ov !== undefined ? ov : defVisible;
          visibilityByRole[r.key] = effective;
          if (effective) count++;
        });
        out.push({
          category: group.title,
          label: item.label,
          route: item.route,
          testId: item.testId,
          itemKey: item.testId,
          visibilityByRole,
          defaultByRole,
          overrideByRole,
          visibleCount: count,
        });
      });
    });
    return out;
  }, [contexts, overrides]);

  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter(r => {
      if (term && !r.label.toLowerCase().includes(term) && !r.category.toLowerCase().includes(term)) return false;
      if (hideEmpty && r.visibleCount === 0) return false;
      return true;
    });
  }, [rows, search, hideEmpty]);

  if (user?.role !== 'super_admin') {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-6">
      <div className="max-w-[1400px] mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Link to="/dashboard">
              <Button variant="ghost" size="sm" data-testid="btn-back-dashboard">
                <ArrowLeft size={16} className="mr-1" /> Voltar
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2" data-testid="permission-matrix-title">
                <Shield size={22} className="text-blue-600" />
                Matriz de Permissões
              </h1>
              <p className="text-sm text-gray-500">
                Visibilidade de cada item de menu por papel — espelho fiel do estado vivo do sistema.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-2.5 text-gray-400" />
              <input
                type="text"
                placeholder="Filtrar por item ou categoria..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                data-testid="permission-matrix-search"
                className="pl-9 pr-3 py-2 border rounded-lg text-sm w-72 focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <label className="text-xs text-gray-600 flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={hideEmpty}
                onChange={e => setHideEmpty(e.target.checked)}
                data-testid="permission-matrix-hide-empty"
              />
              Ocultar itens sem ninguém
            </label>
          </div>
        </div>

        {/* Resumo */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card><CardContent className="py-3 text-center">
            <div className="text-xs text-gray-500">Itens de menu</div>
            <div className="text-2xl font-bold text-gray-900" data-testid="kpi-total-items">{rows.length}</div>
          </CardContent></Card>
          <Card><CardContent className="py-3 text-center">
            <div className="text-xs text-gray-500">Papéis</div>
            <div className="text-2xl font-bold text-gray-900">{ROLES.length}</div>
          </CardContent></Card>
          <Card><CardContent className="py-3 text-center">
            <div className="text-xs text-gray-500">Itens só Super Admin</div>
            <div className="text-2xl font-bold text-rose-700" data-testid="kpi-only-super">
              {rows.filter(r => r.visibleCount === 1 && r.visibilityByRole.super_admin).length}
            </div>
          </CardContent></Card>
          <Card><CardContent className="py-3 text-center">
            <div className="text-xs text-gray-500">Itens visíveis a todos</div>
            <div className="text-2xl font-bold text-emerald-700" data-testid="kpi-all-roles">
              {rows.filter(r => r.visibleCount === ROLES.length).length}
            </div>
          </CardContent></Card>
          <Card><CardContent className="py-3 text-center">
            <div className="text-xs text-gray-500">Overrides ativos</div>
            <div className="text-2xl font-bold text-blue-700" data-testid="kpi-overrides-count">
              {Object.keys(overrides).length}
            </div>
          </CardContent></Card>
        </div>

        {/* Legenda */}
        <div className="flex flex-wrap items-center gap-4 text-xs text-gray-600 px-1">
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-50 text-emerald-700"><Check size={12} strokeWidth={3} /></span>
            <span>Default visível</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-gray-50 text-gray-300"><X size={11} /></span>
            <span>Default oculto</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 text-blue-700 ring-2 ring-blue-400"><Check size={12} strokeWidth={3} /></span>
            <span>Override → visível</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-rose-100 text-rose-700 ring-2 ring-rose-400"><X size={11} /></span>
            <span>Override → oculto</span>
          </div>
          <div className="flex items-center gap-1.5">
            <RotateCcw size={11} className="text-gray-400" />
            <span>Reverter ao default</span>
          </div>
        </div>
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="text-base">
              {filteredRows.length} {filteredRows.length === 1 ? 'item' : 'itens'} listados
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm" data-testid="permission-matrix-table">
              <thead className="sticky top-0 bg-white border-b z-10">
                <tr>
                  <th className="text-left font-semibold text-gray-700 px-3 py-2 w-56 sticky left-0 bg-white">Item</th>
                  <th className="text-left font-semibold text-gray-500 px-3 py-2 w-40">Categoria</th>
                  {ROLES.map(r => (
                    <th key={r.key} className="px-2 py-2 text-center" title={`${r.fullLabel} (${r.key})`}>
                      <div className="text-[10px] uppercase tracking-wide text-gray-500 font-semibold whitespace-nowrap">
                        {r.label}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row, idx) => (
                  <tr
                    key={`${row.category}-${row.label}-${idx}`}
                    className="border-b hover:bg-blue-50/40 transition-colors"
                    data-testid={`row-${row.testId || row.label.toLowerCase().replace(/\s+/g, '-')}`}
                  >
                    <td className="px-3 py-2 font-medium text-gray-900 sticky left-0 bg-white whitespace-nowrap">
                      {row.label}
                      <div className="text-[10px] text-gray-400 font-normal">{row.route}</div>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">{row.category}</td>
                    {ROLES.map(r => {
                      const cellKey = `${row.itemKey}|${r.key}`;
                      const isSuperAdmin = r.key === 'super_admin';
                      return (
                        <td key={r.key} className="px-2 py-2 text-center">
                          {isSuperAdmin ? (
                            <span
                              title="Super Admin sempre tem acesso (bloqueio aqui é ignorado pelo backend por segurança)"
                              className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-emerald-50 text-emerald-700 ring-1 ring-emerald-300"
                              data-testid={`cell-${row.itemKey}-super_admin`}
                            >
                              <Check size={16} strokeWidth={3} />
                            </span>
                          ) : (
                            <Cell
                              defaultVisible={row.defaultByRole[r.key]}
                              override={row.overrideByRole[r.key]}
                              saving={savingCell === cellKey}
                              onClick={() => handleToggle(row.itemKey, r.key, row.defaultByRole[r.key], row.overrideByRole[r.key])}
                              onReset={() => handleReset(row.itemKey, r.key)}
                            />
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {filteredRows.length === 0 && (
                  <tr><td colSpan={ROLES.length + 2} className="text-center py-12 text-gray-400 text-sm">
                    Nenhum item corresponde ao filtro.
                  </td></tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <p className="text-xs text-gray-500 text-center pb-4">
          Esta tabela é gerada dinamicamente a partir do menu em <code>Dashboard.js</code>.
          Para alterar visibilidade, clique em qualquer célula. Os overrides são persistidos
          em <code>permission_overrides</code> e aplicados sobre o default sem precisar editar código.
          <br />
          ✅ A partir de Apr/2026, o <strong>backend também respeita</strong> estes overrides
          (camada dinâmica via <code>AuthMiddleware.require_permission</code>). Bloquear uma célula
          também nega a API correspondente para aquele papel.
          <br />
          🔒 <strong>Super Admin</strong> sempre tem acesso — o backend ignora bloqueios desta coluna
          para evitar lock-out acidental.
        </p>

        {/* Toast */}
        {toast && (
          <div
            className={`fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg text-sm font-medium z-50 transition-opacity ${
              toast.type === 'error' ? 'bg-rose-600 text-white' : 'bg-emerald-600 text-white'
            }`}
            data-testid="permission-matrix-toast"
          >
            {toast.message}
          </div>
        )}
      </div>
    </div>
  );
}
