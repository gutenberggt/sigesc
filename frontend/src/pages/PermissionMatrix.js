/**
 * Permission Matrix Page (super_admin only)
 *
 * Exibe a matriz: itens de menu × papéis × ✅/❌
 * A coluna "Visível?" usa as MESMAS funções `visible(c)` declaradas no
 * `Dashboard.js` (compartilhadas via DASHBOARD_MENU_GROUPS), simulando um
 * contexto de permissão por papel. Isso garante que a tabela é sempre o
 * espelho fiel do que cada papel realmente vê no menu.
 */
import { useState, useMemo } from 'react';
import { Link, Navigate } from 'react-router-dom';
import {
  ArrowLeft, Check, X, Search, Shield,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { DASHBOARD_MENU_GROUPS } from './Dashboard';

// Papéis observáveis (linhas vivas em produção)
const ROLES = [
  { key: 'super_admin', label: 'Super Admin' },
  { key: 'admin', label: 'Administrador' },
  { key: 'gerente', label: 'Gerente' },
  { key: 'admin_teste', label: 'Admin Teste' },
  { key: 'secretario', label: 'Secretário' },
  { key: 'diretor', label: 'Diretor' },
  { key: 'coordenador', label: 'Coordenador' },
  { key: 'apoio_pedagogico', label: 'Apoio Pedag.' },
  { key: 'auxiliar_secretaria', label: 'Aux. Secretaria' },
  { key: 'professor', label: 'Professor' },
  { key: 'ass_social', label: 'Ass. Social' },
  { key: 'aluno', label: 'Aluno' },
  { key: 'responsavel', label: 'Responsável' },
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

const Cell = ({ visible }) => (
  visible ? (
    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-emerald-50 text-emerald-700">
      <Check size={16} strokeWidth={3} />
    </span>
  ) : (
    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-gray-50 text-gray-300">
      <X size={14} />
    </span>
  )
);

export default function PermissionMatrix() {
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const [hideEmpty, setHideEmpty] = useState(false);

  // Memoiza contextos por papel para evitar recriar a cada render
  const contexts = useMemo(
    () => Object.fromEntries(ROLES.map(r => [r.key, makePermissionContext(r.key)])),
    []
  );

  // Achata todas as categorias × itens em uma única lista anotada
  const rows = useMemo(() => {
    const out = [];
    DASHBOARD_MENU_GROUPS.forEach(group => {
      group.items.forEach(item => {
        const visibilityByRole = {};
        let count = 0;
        ROLES.forEach(r => {
          let v = false;
          try { v = !!item.visible(contexts[r.key]); } catch { v = false; }
          visibilityByRole[r.key] = v;
          if (v) count++;
        });
        out.push({
          category: group.title,
          label: item.label,
          route: item.route,
          testId: item.testId,
          visibilityByRole,
          visibleCount: count,
        });
      });
    });
    return out;
  }, [contexts]);

  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter(r => {
      if (term && !r.label.toLowerCase().includes(term) && !r.category.toLowerCase().includes(term)) return false;
      if (hideEmpty && r.visibleCount === 0) return false;
      return true;
    });
  }, [rows, search, hideEmpty]);

  if (user?.role !== 'super_admin') {
    return <Navigate to="/admin/dashboard" replace />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-6">
      <div className="max-w-[1400px] mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Link to="/admin/dashboard">
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
        </div>

        {/* Tabela */}
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
                    <th key={r.key} className="px-2 py-2 text-center" title={r.key}>
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
                    {ROLES.map(r => (
                      <td key={r.key} className="px-2 py-2 text-center">
                        <Cell visible={row.visibilityByRole[r.key]} />
                      </td>
                    ))}
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
          Para alterar visibilidade, edite o callback <code>visible</code> do item correspondente.
          Restrições de backend são aplicadas separadamente em <code>routers/*.py</code>.
        </p>
      </div>
    </div>
  );
}
