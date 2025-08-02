import React, { useState, useEffect } from 'react';
import { auth, db } from '../firebase/config';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { doc, setDoc, getDocs, collection, query, updateDoc, deleteDoc, where, getDoc, orderBy } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';
import { getFunctions, httpsCallable } from 'firebase/functions';

function UserManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const functions = getFunctions();

  const toggleUserAccountStatusCallable = httpsCallable(functions, 'toggleUserAccountStatus');
  const adminResetUserPasswordCallable = httpsCallable(functions, 'adminResetUserPassword');
  const adminDeleteUserCallable = httpsCallable(functions, 'adminDeleteUser');

  const [users, setUsers] = useState([]);
  const [editingUser, setEditingUser] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  // ======================= INÍCIO DAS ADIÇÕES =======================
  // ADIÇÃO: Estados para as sugestões de PESSOAS que vêm da busca principal
  const [personSearchSuggestions, setPersonSearchSuggestions] = useState([]);
  // ADIÇÃO: Estado para guardar o ID da pessoa selecionada para vincular ao novo usuário
  const [selectedPersonId, setSelectedPersonId] = useState(null);
  // ======================== FIM DAS ADIÇÕES =========================

  // --- ESTADOS DOS CAMPOS DO FORMULÁRIO (Originais Mantidos) ---
  const [nomeCompleto, setNomeCompleto] = useState('');
  const [email, setEmail] = useState('');
  const [cpf, setCpf] = useState('');
  const [celular, setCelular] = useState('');
  const [senha, setSenha] = useState('');
  const [confirmarSenha, setConfirmarSenha] = useState('');
  const [funcao, setFuncao] = useState('aluno');
  const [status, setStatus] = useState('ativo');
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [userPermissions, setUserPermissions] = useState([]);
  const [currentPermission, setCurrentPermission] = useState('aluno');
  const [currentSchoolId, setCurrentSchoolId] = useState('');
  const [availableSchools, setAvailableSchools] = useState([]);
  const [searchPersonName, setSearchPersonName] = useState('');
  const [permissionPersonSuggestions, setPermissionPersonSuggestions] = useState([]);
  const [selectedPermissionPersonId, setSelectedPermissionPersonId] = useState('');

  const resetForm = () => {
    setNomeCompleto('');
    setEmail('');
    setCpf('');
    setCelular('');
    setSenha('');
    setConfirmarSenha('');
    setFuncao('aluno');
    setStatus('ativo');
    setUserPermissions([]);
    setCurrentPermission('aluno');
    setCurrentSchoolId('');
    setSearchPersonName('');
    setPermissionPersonSuggestions([]);
    setSelectedPermissionPersonId('');
    setErrorMessage('');
    setSuccessMessage('');
    setEditingUser(null);
    // ADIÇÃO: Limpar estados da busca principal
    setSelectedPersonId(null);
    setSearchTerm('');
    setPersonSearchSuggestions([]);
  };

  const formatCPF = (value) => { value = value.replace(/\D/g, ''); value = value.replace(/(\d{3})(\d)/, '$1.$2'); value = value.replace(/(\d{3})(\d)/, '$1.$2'); value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2'); return value.substring(0, 14); };
  const formatCelular = (value) => { value = value.replace(/\D/g, ''); if (value.length > 11) value = value.substring(0, 11); value = value.replace(/^(\d{2})(\d)/g, '($1) $2'); value = value.replace(/(\d)(\d{4})$/, '$1-$2'); return value; };
  const validateCPF = (rawCpf) => { let cpfCleaned = rawCpf.replace(/\D/g, ''); if (cpfCleaned.length !== 11) return false; if (/^(\d)\1{10}$/.test(cpfCleaned)) return false; let sum = 0; let remainder; for (let i = 1; i <= 9; i++) { sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (11 - i); } remainder = (sum * 10) % 11; if ((remainder === 10) || (remainder === 11)) remainder = 0; if (remainder !== parseInt(cpfCleaned.substring(9, 10))) return false; sum = 0; for (let i = 1; i <= 10; i++) { sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (12 - i); } remainder = (sum * 10) % 11; if ((remainder === 10) || (remainder === 11)) remainder = 0; if (remainder !== parseInt(cpfCleaned.substring(10, 11))) return false; return true; };

  const filteredUsers = users.filter(user => (user.nomeCompleto && user.nomeCompleto.toLowerCase().includes(searchTerm.toLowerCase())) || (user.cpf && user.cpf.includes(searchTerm)) || (user.email && user.email.toLowerCase().includes(searchTerm.toLowerCase())));

  useEffect(() => {
    if (!loading) {
      if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
        navigate('/dashboard');
        return;
      }
      const fetchUsersAndSchools = async () => {
        try {
          const usersCol = collection(db, 'users');
          const userSnapshot = await getDocs(usersCol);
          const userList = userSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
          setUsers(userList);
          const schoolsCol = collection(db, 'schools');
          const schoolsSnapshot = await getDocs(schoolsCol);
          let schoolsList = schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
          if (userData.funcao.toLowerCase() === 'secretario') {
            const userSchoolsIds = userData.escolasIds || (userData.escolaId ? [userData.escolaId] : []);
            schoolsList = schoolsList.filter(school => userSchoolsIds.includes(school.id));
          }
          setAvailableSchools(schoolsList);
        } catch (error) {
          console.error("Erro ao buscar usuários ou escolas:", error);
          setErrorMessage("Erro ao carregar lista de usuários ou escolas.");
        }
      };
      fetchUsersAndSchools();
    }
  }, [loading, userData, navigate]);

  const handleAddPermission = () => { /* ... (código original mantido) ... */ };
  const handleRemovePermission = (index) => { /* ... (código original mantido) ... */ };
  useEffect(() => { /* ... (useEffect para busca de permissões mantido) ... */ }, [searchPersonName, currentPermission]);

  // ======================= INÍCIO DAS ADIÇÕES =======================
  // EFEITO PARA A BUSCA PRINCIPAL SUGERIR PESSOAS
  useEffect(() => {
    if (searchTerm.length >= 3 && !editingUser) { // Só busca sugestões se não estiver em modo de edição
      const fetchPersonSuggestions = async () => {
        try {
          const searchLower = searchTerm.toLowerCase();
          const q = query(
            collection(db, 'pessoas'),
            where('nomeCompleto', '>=', searchLower.toUpperCase()),
            where('nomeCompleto', '<=', searchLower.toUpperCase() + '\uf8ff'),
            orderBy('nomeCompleto')
          );
          const querySnapshot = await getDocs(q);
          const suggestions = querySnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
          setPersonSearchSuggestions(suggestions);
        } catch (error) {
          console.error("Erro ao buscar sugestões de pessoas:", error);
        }
      };
      const handler = setTimeout(() => fetchPersonSuggestions(), 300);
      return () => clearTimeout(handler);
    } else {
      setPersonSearchSuggestions([]);
    }
  }, [searchTerm, editingUser]);

  // FUNÇÃO PARA PREENCHER O FORMULÁRIO AO SELECIONAR UMA SUGESTÃO
  const handleSelectSuggestion = (person) => {
    setSelectedPersonId(person.id);
    setSearchTerm(''); // Limpa a busca para a tabela e sugestões voltarem ao normal
    setPersonSearchSuggestions([]);
    setNomeCompleto(person.nomeCompleto || '');
    setCpf(person.cpf || '');
    setEmail(person.emailContato || '');
    setCelular(person.celular || '');
  };
  // ======================== FIM DAS ADIÇÕES =========================

  const handleSubmit = async (e) => {
    e.preventDefault();
    // ... (lógica de validação original mantida) ...

    try {
      if (editingUser) {
        const userDocRef = doc(db, 'users', editingUser.id);
        const updateData = {
          nomeCompleto: nomeCompleto.toUpperCase(), email, cpf: cpf.replace(/\D/g, ''), telefone: celular.replace(/\D/g, ''), funcao, ativo: status === 'ativo', permissoes: userPermissions,
          pessoaId: selectedPersonId, // ADIÇÃO
          ultimaAtualizacao: new Date(),
        };
        await updateDoc(userDocRef, updateData);
        setSuccessMessage('Usuário atualizado com sucesso!');
        setUsers(users.map(u => (u.id === editingUser.id ? { ...u, ...updateData } : u)));
      } else {
        const userCredential = await createUserWithEmailAndPassword(auth, email, senha);
        const userAuthId = userCredential.user.uid;
        const newUser = {
          nomeCompleto: nomeCompleto.toUpperCase(), email, cpf: cpf.replace(/\D/g, ''), telefone: celular.replace(/\D/g, ''), funcao, ativo: status === 'ativo', permissoes: userPermissions,
          pessoaId: selectedPersonId, // ADIÇÃO
          criadoEm: new Date(), ultimaAtualizacao: new Date(),
          escolaId: userPermissions.length > 0 && userPermissions[0].escolaId ? userPermissions[0].escolaId : null,
          escolasIds: userPermissions.filter(p => p.escolaId).map(p => p.escolaId),
          turmasIds: userPermissions.filter(p => (p.permissao === 'aluno' || p.permissao === 'professor') && p.pessoaId).map(p => p.pessoaId)
        };
        await setDoc(doc(db, 'users', userAuthId), newUser);
        setSuccessMessage('Usuário cadastrado com sucesso!');
        setUsers([...users, { id: userAuthId, ...newUser }]);
      }
      resetForm();
    } catch (error) {
      // ... (lógica de erro original mantida) ...
    }
  };

  const handleEdit = (userToEdit) => {
    setEditingUser(userToEdit);
    setNomeCompleto(userToEdit.nomeCompleto || '');
    setEmail(userToEdit.email || '');
    setCpf(formatCPF(userToEdit.cpf || ''));
    setCelular(formatCelular(userToEdit.telefone || ''));
    setFuncao(userToEdit.funcao || 'aluno');
    setStatus(userToEdit.ativo ? 'ativo' : 'inativo');
    setUserPermissions(userToEdit.permissoes || []);
    setSenha('');
    setConfirmarSenha('');
    setErrorMessage('');
    setSuccessMessage('');
    setSelectedPersonId(userToEdit.pessoaId || null);
    setSearchTerm(userToEdit.nomeCompleto || '');
  };

  const handleDelete = async (userId) => { /* ... (código original mantido) ... */ };
  if (loading) { /* ... */ }
  if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) { /* ... */ }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingUser ? 'Editar Usuário' : 'Novo Usuário Interno'}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}
        
        <div className="relative mb-6">
          <input
            type="text"
            placeholder="Buscar usuário por nome, CPF ou e-mail..."
            className="w-full p-2 border border-gray-300 rounded-md"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            autoComplete="off"
          />
          {searchTerm.length >= 3 && personSearchSuggestions.length > 0 && (
              <ul className="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto mt-1">
                  <div className="p-2 text-xs font-semibold text-gray-500 bg-gray-100">Sugestões de Pessoas para vincular:</div>
                  {personSearchSuggestions.map(person => (
                      <li
                          key={person.id}
                          className="p-2 cursor-pointer hover:bg-gray-200 flex justify-between"
                          onClick={() => handleSelectSuggestion(person)}
                      >
                          <span>{person.nomeCompleto}</span>
                          <span className="text-xs text-gray-500">{formatCPF(person.cpf)}</span>
                      </li>
                  ))}
              </ul>
          )}
        </div>
        
        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2">
            <label htmlFor="nomeCompleto" className="block text-sm font-medium text-gray-700">Nome Completo <span className="text-red-500">*</span></label>
            <input type="text" id="nomeCompleto" placeholder="Nome Completo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeCompleto} onChange={(e) => setNomeCompleto(e.target.value.toUpperCase())} required autoComplete="off"/>
          </div>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">E-mail <span className="text-red-500">*</span></label>
            <input type="email" id="email" placeholder="email@exemplo.com" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={!!editingUser} autoComplete="off" />
          </div>
          <div>
            <label htmlFor="cpf" className="block text-sm font-medium text-gray-700">CPF <span className="text-red-500">*</span></label>
            <input type="text" id="cpf" placeholder="000.000.000-00" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCPF(cpf)} onChange={(e) => setCpf(e.target.value)} maxLength="14" required autoComplete="off" />
          </div>
          <div className="md:col-span-2 flex flex-col md:flex-row gap-4">
            <div className="w-full md:w-1/3">
              <label htmlFor="celular" className="block text-sm font-medium text-gray-700">Celular <span className="text-red-500">*</span></label>
              <input type="tel" id="celular" placeholder="(00)90000-0000" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCelular(celular)} onChange={(e) => setCelular(e.target.value)} maxLength="15" required autoComplete="off" />
            </div>
            <div className="w-full md:w-1/3">
                <label htmlFor="funcao" className="block text-sm font-medium text-gray-700">Função Primária <span className="text-red-500">*</span></label>
                <select id="funcao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={funcao} onChange={(e) => setFuncao(e.target.value)} required autoComplete="off">
                <option value="aluno">Aluno</option>
                <option value="professor">Professor</option>
                <option value="secretario">Secretário</option>
                <option value="coordenador">Coordenador</option>
                <option value="diretor">Diretor</option>
                </select>
            </div>
            <div className="w-full md:w-1/3">
              <label htmlFor="status" className="block text-sm font-medium text-gray-700">Status <span className="text-red-500">*</span></label>
              <select id="status" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={status} onChange={(e) => setStatus(e.target.value)} required autoComplete="off">
                <option value="ativo">Ativo</option>
                <option value="inativo">Inativo</option>
              </select>
            </div>
          </div>
          {!editingUser && (
            <>
              <div>
                <label htmlFor="senha" className="block text-sm font-medium text-gray-700">Senha <span className="text-red-500">*</span></label>
                <input type="password" id="senha" placeholder="********" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={senha} onChange={(e) => setSenha(e.target.value)} required={!editingUser} autoComplete="new-password" />
              </div>
              <div>
                <label htmlFor="confirmarSenha" className="block text-sm font-medium text-gray-700">Confirme a Senha <span className="text-red-500">*</span></label>
                <input type="password" id="confirmarSenha" placeholder="********" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={confirmarSenha} onChange={(e) => setConfirmarSenha(e.target.value)} required={!editingUser} autoComplete="new-password" />
              </div>
            </>
          )}
          {editingUser && (
            <div className="md:col-span-2 text-sm text-gray-600 mt-2">
              <p>Para alterar a senha do usuário, preencha os campos abaixo. Isso utilizará uma Cloud Function.</p>
              <div className="flex gap-4 mt-2">
                <div className="w-1/2">
                  <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">Nova Senha</label>
                  <input type="password" id="newPassword" placeholder="Nova senha" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="new-password" />
                </div>
                <div className="w-1/2">
                  <label htmlFor="confirmNewPassword" className="block text-sm font-medium text-gray-700">Confirme Nova Senha</label>
                  <input type="password" id="confirmNewPassword" placeholder="Confirme nova senha" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={confirmarSenha} onChange={(e) => setConfirmarSenha(e.target.value)} autoComplete="new-password" />
                </div>
              </div>
            </div>
          )}
          <div className="md:col-span-2 border p-4 rounded-lg bg-gray-50 mt-4">
            <h3 className="text-lg font-semibold text-gray-700 mb-4">Permissões de Acesso por Unidade</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end mb-4">
              <div>
                <label htmlFor="currentPermission" className="block text-sm font-medium text-gray-700">Permissão</label>
                <select id="currentPermission" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={currentPermission} onChange={(e) => { setCurrentPermission(e.target.value); setSearchPersonName(''); setPermissionPersonSuggestions([]); setSelectedPermissionPersonId(''); }} autoComplete="off">
                  <option value="aluno">Aluno</option>
                  <option value="professor">Professor</option>
                  <option value="secretario">Secretário</option>
                  <option value="coordenador">Coordenador</option>
                  <option value="diretor">Diretor</option>
                </select>
              </div>
              <div>
                <label htmlFor="currentSchoolId" className="block text-sm font-medium text-gray-700">Unidade (Escola)</label>
                <select id="currentSchoolId" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={currentSchoolId} onChange={(e) => setCurrentSchoolId(e.target.value)} autoComplete="off">
                  <option value="">Selecione uma Escola</option>
                  {availableSchools.map(school => (<option key={school.id} value={school.id}>{school.nomeEscola}</option>))}
                </select>
              </div>
              <button type="button" onClick={handleAddPermission} className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition h-10 flex items-center justify-center">Adicionar Permissão</button>
            </div>
            {(currentPermission === 'aluno' || currentPermission === 'professor') && (
              <div className="mb-4 relative">
                <label htmlFor="searchPersonName" className="block text-sm font-medium text-gray-700">{currentPermission === 'aluno' ? 'Buscar Aluno' : 'Buscar Professor'}</label>
                <input type="text" id="searchPersonName" placeholder={`Digite o nome do ${currentPermission} (mín. 3 letras)`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={searchPersonName} onChange={(e) => { setSearchPersonName(e.target.value); setSelectedPermissionPersonId(''); }} autoComplete="off" />
                {searchPersonName.length >= 3 && permissionPersonSuggestions.length > 0 && (
                  <ul className="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto mt-1">
                    {permissionPersonSuggestions.map(person => (
                      <li key={person.id} className="p-2 cursor-pointer hover:bg-gray-200" onClick={() => { setSearchPersonName(person.nome); setSelectedPermissionPersonId(person.id); setPermissionPersonSuggestions([]); }}>
                        {person.nome}
                      </li>
                    ))}
                  </ul>
                )}
                {searchPersonName.length >= 3 && permissionPersonSuggestions.length === 0 && (<p className="text-sm text-gray-500 mt-1">Nenhuma sugestão encontrada.</p>)}
                {selectedPermissionPersonId && (<p className="text-sm text-gray-600 mt-1">Pessoa selecionada: {searchPersonName}</p>)}
              </div>
            )}
            {userPermissions.length > 0 && (
              <div className="mt-4 border-t pt-4">
                <h4 className="text-md font-semibold text-gray-700 mb-2">Permissões Atribuídas:</h4>
                <ul className="space-y-2">
                  {userPermissions.map((perm, index) => (
                    <li key={index} className="flex justify-between items-center bg-white p-3 rounded-md shadow-sm border border-gray-200">
                      <span><span className="font-medium text-blue-700">{perm.permissao.charAt(0).toUpperCase() + perm.permissao.slice(1)}</span>{perm.escolaId && ` em ${availableSchools.find(s => s.id === perm.escolaId)?.nomeEscola || 'Escola Desconhecida'}`}{(perm.pessoaNome && (perm.permissao === 'aluno' || perm.permissao === 'professor')) && ` (${perm.pessoaNome})`}</span>
                      <button type="button" onClick={() => handleRemovePermission(index)} className="text-red-500 hover:text-red-700 p-1 rounded-full" title="Remover Permissão">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {editingUser && status === 'inativo' && (
            <div className="md:col-span-2 text-red-500 text-xs mt-1">
              Desativar um usuário aqui afeta apenas o status no Firestore. Para desativar a conta de autenticação no Firebase (impedir login), é necessária uma Cloud Function.
            </div>
          )}
          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingUser && (
              <button type="button" onClick={resetForm} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded">Cancelar Edição</button>
            )}
            <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
              {editingUser ? 'Salvar Alterações' : 'Cadastrar Usuário'}
            </button>
          </div>
        </form>
        <hr className="my-8" />
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Lista de Usuários</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border border-gray-300 rounded-md">
            <thead>
              <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                <th className="py-3 px-6 text-left">Nome Completo</th>
                <th className="py-3 px-6 text-left">E-mail</th>
                <th className="py-3 px-6 text-left">Função</th>
                <th className="py-3 px-6 text-left">Status</th>
                <th className="py-3 px-6 text-center">Ações</th>
              </tr>
            </thead>
            <tbody className="text-gray-600 text-sm font-light">
              {filteredUsers.map((user) => (
                <tr key={user.id} className="border-b border-gray-200 hover:bg-gray-100">
                  <td className="py-3 px-6 text-left whitespace-nowrap">{user.nomeCompleto}</td>
                  <td className="py-3 px-6 text-left">{user.email}</td>
                  <td className="py-3 px-6 text-left">{user.funcao}</td>
                  <td className="py-3 px-6 text-left"><span className={`py-1 px-3 rounded-full text-xs ${user.ativo ? 'bg-green-200 text-green-600' : 'bg-red-200 text-red-600'}`}>{user.ativo ? 'Ativo' : 'Inativo'}</span></td>
                  <td className="py-3 px-6 text-center">
                    <div className="flex item-center justify-center space-x-2">
                      <button onClick={() => handleEdit(user)} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-full text-xs">Editar</button>
                      <button onClick={() => handleDelete(user.id)} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full text-xs">Excluir</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default UserManagementPage;