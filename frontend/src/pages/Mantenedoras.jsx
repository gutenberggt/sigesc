/**
 * Página de gestão de Mantenedoras (multi-tenant).
 * Acesso: super_admin apenas.
 *
 * Permite:
 *  - Criar/editar/excluir mantenedoras
 *  - Designar gerente para cada mantenedora (pool global de usuários)
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Plus, Edit2, Trash2, Shield, Users, X, Check, Building2 } from 'lucide-react';
import { Layout } from '../components/Layout';
import { useAuth } from '../contexts/AuthContext';

const API = process.env.REACT_APP_BACKEND_URL;

const emptyForm = { nome: '', cnpj: '', municipio: '', estado: '', logotipo_url: '', ativo: true };

export default function Mantenedoras() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [gerenteModalOpen, setGerenteModalOpen] = useState(false);
  const [targetMantenedora, setTargetMantenedora] = useState(null);
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState('');

  const isSuperAdmin = user?.role === 'super_admin' || (user?.roles || []).includes('super_admin');

  useEffect(() => {
    if (!isSuperAdmin) {
      toast.error('Acesso restrito a super administradores');
      navigate('/admin');
      return;
    }
    load();
    // eslint-disable-next-line
  }, [isSuperAdmin]);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/api/mantenedoras`);
      setList(data || []);
    } catch (e) {
      toast.error('Erro ao carregar mantenedoras');
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => { setEditingId(null); setForm(emptyForm); setModalOpen(true); };
  const openEdit = (m) => {
    setEditingId(m.id);
    setForm({
      nome: m.nome || m.name || '', cnpj: m.cnpj || '', municipio: m.municipio || m.cidade || '',
      estado: m.estado || '', logotipo_url: m.logotipo_url || m.logo_url || '', ativo: m.ativo !== false,
    });
    setModalOpen(true);
  };
  const save = async () => {
    if (!form.nome) { toast.error('Informe o nome da mantenedora'); return; }
    try {
      if (editingId) {
        await axios.put(`${API}/api/mantenedoras/${editingId}`, form);
        toast.success('Mantenedora atualizada');
      } else {
        await axios.post(`${API}/api/mantenedoras`, form);
        toast.success('Mantenedora criada');
      }
      setModalOpen(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao salvar');
    }
  };
  const remove = async (m) => {
    if (!window.confirm(`Excluir "${m.nome || m.name}"? Só é permitido se não houver escolas vinculadas.`)) return;
    try {
      await axios.delete(`${API}/api/mantenedoras/${m.id}`);
      toast.success('Mantenedora excluída');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao excluir');
    }
  };

  const openGerente = async (m) => {
    setTargetMantenedora(m);
    setSelectedUserId('');
    try {
      const { data } = await axios.get(`${API}/api/users`);
      setUsers((data || []).filter(u => ['admin', 'gerente'].includes(u.role) || (u.roles || []).some(r => ['admin', 'gerente'].includes(r))));
    } catch (e) { setUsers([]); }
    setGerenteModalOpen(true);
  };
  const saveGerente = async () => {
    if (!selectedUserId) { toast.error('Selecione um usuário'); return; }
    try {
      await axios.post(`${API}/api/mantenedoras/${targetMantenedora.id}/gerente`, { user_id: selectedUserId });
      toast.success('Gerente designado com sucesso');
      setGerenteModalOpen(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao designar gerente');
    }
  };

  return (
    <Layout>
      <div className="p-6 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Building2 className="text-indigo-600" /> Mantenedoras
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Gestão multi-tenant. Cada mantenedora tem suas próprias escolas, servidores e dados isolados.
            </p>
          </div>
          <button onClick={openCreate} data-testid="btn-nova-mantenedora"
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
            <Plus size={18}/> Nova Mantenedora
          </button>
        </div>

        {loading ? (
          <div className="text-center py-10 text-gray-500">Carregando...</div>
        ) : list.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-10 text-center text-gray-500">
            Nenhuma mantenedora cadastrada.
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="text-left px-4 py-2">Nome</th>
                  <th className="text-left px-4 py-2">CNPJ</th>
                  <th className="text-left px-4 py-2">Cidade/UF</th>
                  <th className="text-center px-4 py-2">Status</th>
                  <th className="text-right px-4 py-2">Ações</th>
                </tr>
              </thead>
              <tbody>
                {list.map(m => (
                  <tr key={m.id} className="border-t hover:bg-gray-50" data-testid={`mantenedora-row-${m.id}`}>
                    <td className="px-4 py-3 font-medium text-gray-900">{m.nome || m.name}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">{m.cnpj || '—'}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">{[m.municipio || m.cidade, m.estado].filter(Boolean).join('/') || '—'}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${m.ativo !== false ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600'}`}>
                        {m.ativo !== false ? 'Ativa' : 'Inativa'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => openGerente(m)} title="Designar gerente"
                          className="p-1.5 text-blue-600 hover:bg-blue-50 rounded" data-testid={`btn-gerente-${m.id}`}>
                          <Users size={16}/>
                        </button>
                        <button onClick={() => openEdit(m)} title="Editar"
                          className="p-1.5 text-gray-600 hover:bg-gray-100 rounded">
                          <Edit2 size={16}/>
                        </button>
                        <button onClick={() => remove(m)} title="Excluir"
                          className="p-1.5 text-red-600 hover:bg-red-50 rounded">
                          <Trash2 size={16}/>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Modal criar/editar */}
        {modalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6 mx-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-lg">
                  {editingId ? 'Editar Mantenedora' : 'Nova Mantenedora'}
                </h3>
                <button onClick={() => setModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <X size={20}/>
                </button>
              </div>
              <div className="space-y-3">
                <label className="block text-sm">
                  <span className="text-gray-700 font-medium">Nome *</span>
                  <input type="text" value={form.nome} onChange={(e) => setForm({...form, nome: e.target.value})}
                    className="mt-1 w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500" data-testid="input-mantenedora-nome"/>
                </label>
                <label className="block text-sm">
                  <span className="text-gray-700 font-medium">CNPJ</span>
                  <input type="text" value={form.cnpj} onChange={(e) => setForm({...form, cnpj: e.target.value})}
                    className="mt-1 w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"/>
                </label>
                <div className="grid grid-cols-3 gap-3">
                  <label className="block text-sm col-span-2">
                    <span className="text-gray-700 font-medium">Município</span>
                    <input type="text" value={form.municipio} onChange={(e) => setForm({...form, municipio: e.target.value})}
                      className="mt-1 w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"/>
                  </label>
                  <label className="block text-sm">
                    <span className="text-gray-700 font-medium">UF</span>
                    <input type="text" maxLength="2" value={form.estado} onChange={(e) => setForm({...form, estado: e.target.value.toUpperCase()})}
                      className="mt-1 w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"/>
                  </label>
                </div>
                <label className="block text-sm">
                  <span className="text-gray-700 font-medium">URL do Logotipo</span>
                  <input type="text" value={form.logotipo_url} onChange={(e) => setForm({...form, logotipo_url: e.target.value})}
                    className="mt-1 w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"/>
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({...form, ativo: e.target.checked})}/>
                  <span>Mantenedora ativa</span>
                </label>
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button onClick={() => setModalOpen(false)} className="px-4 py-2 border rounded-lg">Cancelar</button>
                <button onClick={save} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700" data-testid="btn-salvar-mantenedora">
                  Salvar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal designar gerente */}
        {gerenteModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6 mx-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold flex items-center gap-2">
                  <Shield size={18}/> Designar Gerente — {targetMantenedora?.nome || targetMantenedora?.name}
                </h3>
                <button onClick={() => setGerenteModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <X size={20}/>
                </button>
              </div>
              <p className="text-xs text-gray-500 mb-3">
                O usuário selecionado será promovido a <strong>gerente</strong> desta mantenedora — terá poderes de admin
                restritos aos dados dela.
              </p>
              <label className="block text-sm mb-3">
                <span className="text-gray-700 font-medium">Usuário</span>
                <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500" data-testid="select-gerente-user">
                  <option value="">Selecione...</option>
                  {users.map(u => (
                    <option key={u.id} value={u.id}>
                      {u.full_name} — {u.email} ({u.role})
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex justify-end gap-2">
                <button onClick={() => setGerenteModalOpen(false)} className="px-4 py-2 border rounded-lg">Cancelar</button>
                <button onClick={saveGerente} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center gap-1" data-testid="btn-designar-gerente">
                  <Check size={16}/> Designar
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
