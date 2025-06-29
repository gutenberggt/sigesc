import React, { useState, useEffect } from 'react';
import { auth, db } from '../firebase/config';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { doc, setDoc, getDocs, collection, query, updateDoc, deleteDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';
import { getFunctions, httpsCallable } from 'firebase/functions';
import Footer from '../components/Footer'; // NOVO: Importe o componente Footer

function UserManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const functions = getFunctions();

  const toggleUserAccountStatusCallable = httpsCallable(functions, 'toggleUserAccountStatus');
  const adminResetUserPasswordCallable = httpsCallable(functions, 'adminResetUserPassword');
  const adminDeleteUserCallable = httpsCallable(functions, 'adminDeleteUser');


  const [users, setUsers] = useState([]);
  const [editingUser, setEditingUser] = useState(null);

  const [name, setName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [cpf, setCpf] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [userRole, setUserRole] = useState('aluno');
  const [status, setStatus] = useState('ativo');
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const resetForm = () => {
    setName('');
    setLastName('');
    setEmail('');
    setUsername('');
    setCpf('');
    setPhoneNumber('');
    setPassword('');
    setConfirmPassword('');
    setUserRole('aluno');
    setStatus('ativo');
    setErrorMessage('');
    setSuccessMessage('');
    setEditingUser(null);
  };

  const formatCPF = (value) => {
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    return value;
  };

  const formatTelefone = (value) => {
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, '($1) $2');
    value = value.replace(/(\d)(\d{4})$/, '$1-$2');
    return value;
  };

  const validateCPF = (rawCpf) => {
    let cpfCleaned = rawCpf.replace(/\D/g, '');
    if (cpfCleaned.length !== 11) return false;
    if (/^(\d)\1{10}$/.test(cpfCleaned)) return false;
    let sum = 0;
    let remainder;
    for (let i = 1; i <= 9; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (11 - i);
    }
    remainder = (sum * 10) % 11;
    if ((remainder === 10) || (remainder === 11)) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(9, 10))) return false;
    sum = 0;
    for (let i = 1; i <= 10; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (12 - i);
    }
    remainder = (sum * 10) % 11;
    if ((remainder === 10) || (remainder === 11)) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(10, 11))) return false;
    return true;
  };

  useEffect(() => {
    if (!loading) {
      if (!userData || (userData.funcao && userData.funcao.toLowerCase() !== 'administrador')) {
        console.log('Acesso negado: Redirecionando para /dashboard. UserData:', userData);
        navigate('/dashboard');
        return;
      }

      const fetchUsers = async () => {
        try {
          const usersCol = collection(db, 'users');
          const userSnapshot = await getDocs(usersCol);
          const userList = userSnapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data()
          }));
          setUsers(userList);
        } catch (error) {
          console.error("Erro ao buscar usuários:", error);
          setErrorMessage("Erro ao carregar lista de usuários.");
        }
      };
      fetchUsers();
    }
  }, [loading, userData, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    if (!name || !email || !userRole || !status) { 
        if (!editingUser && (!password || !confirmPassword)) { 
            setErrorMessage('Senha e Confirma Senha são obrigatórios para novos usuários.');
            return;
        }
        if (editingUser && password && !confirmPassword) { 
            setErrorMessage('Confirme a nova senha.');
            return;
        }
        if (editingUser && !password && confirmPassword) { 
            setErrorMessage('Nova Senha é obrigatória se Confirmar Nova Senha for preenchida.');
            return;
        }
        if (!name || !email || !userRole || !status) {
            setErrorMessage('Nome, E-mail, Função e Status são obrigatórios.');
            return;
        }
    }
    
    if (password && password !== confirmPassword) {
      setErrorMessage('As senhas não coincidem.');
      return;
    }
    
    const cpfCleaned = cpf.replace(/\D/g, '');
    if (cpfCleaned && !validateCPF(cpfCleaned)) {
        setErrorMessage('CPF inválido.');
        return;
    }

    try {
      if (editingUser) {
        // MODO EDIÇÃO
        const userDocRef = doc(db, 'users', editingUser.id);
        const updateData = {
          nome: name.toUpperCase(),
          sobrenome: lastName.toUpperCase(),
          email: email, 
          username: username,
          cpf: cpfCleaned,
          telefone: phoneNumber,
          funcao: userRole,
          ativo: status === 'ativo',
        };
        await updateDoc(userDocRef, updateData);

        if (password) {
            const result = await adminResetUserPasswordCallable({ uid: editingUser.id, newPassword: password });
            console.log(result.data.message);
            setSuccessMessage('Usuário atualizado com sucesso e senha redefinida (via Cloud Function)!');
        } else {
            setSuccessMessage('Usuário atualizado com sucesso!');
        }
        
        setUsers(users.map(u => u.id === editingUser.id ? { ...u, ...updateData } : u));


      } else {
        // MODO CADASTRO DE NOVO USUÁRIO
        const userCredential = await createUserWithEmailAndPassword(auth, email, password);
        const newUserAuth = userCredential.user;

        await setDoc(doc(db, 'users', newUserAuth.uid), {
          nome: name.toUpperCase(),
          sobrenome: lastName.toUpperCase(),
          email: email,
          username: username,
          cpf: cpfCleaned,
          telefone: phoneNumber,
          funcao: userRole,
          ativo: status === 'ativo',
          criadoEm: new Date(),
        });
        setSuccessMessage('Usuário cadastrado com sucesso! Uma verificação de e-mail pode ser necessária.');

        setUsers([...users, { id: newUserAuth.uid, nome: name.toUpperCase(), sobrenome: lastName.toUpperCase(), email, funcao: userRole, ativo: status === 'ativo' }]);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar usuário:", error);
      if (error.code === 'auth/email-already-in-use') {
        setErrorMessage('Este e-mail já está cadastrado.');
      } else if (error.code === 'auth/weak-password') {
        setErrorMessage('A senha é muito fraca. Deve ter pelo menos 6 caracteres.');
      } else {
        setErrorMessage('Erro ao salvar usuário: ' + error.message);
      }
    }
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    setName(user.nome || '');
    setLastName(user.sobrenome || '');
    setEmail(user.email || '');
    setUsername(user.username || '');
    setCpf(user.cpf || '');
    setPhoneNumber(user.telefone || '');
    setUserRole(user.funcao || 'aluno');
    setStatus(user.ativo ? 'ativo' : 'inativo');
    setPassword('');
    setConfirmPassword('');
    setErrorMessage('');
    setSuccessMessage('');
  };

  const handleDelete = async (userId) => {
    if (window.confirm('Tem certeza que deseja excluir este usuário permanentemente? Esta ação não pode ser desfeita e removerá também a conta de autenticação!')) {
      try {
        const result = await adminDeleteUserCallable({ uid: userId });
        console.log(result.data.message);
        setSuccessMessage('Usuário excluído com sucesso (via Cloud Function)!');
        setUsers(users.filter(user => user.id !== userId));
        resetForm(); // Limpa o formulário após excluir
      } catch (error) {
        console.error("Erro ao excluir usuário:", error);
        setErrorMessage("Erro ao excluir usuário: " + error.message);
      }
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        Carregando permissões...
      </div>
    );
  }

  if (!userData || (userData.funcao && userData.funcao.toLowerCase() !== 'administrador')) {
    return (
      <div className="flex justify-center items-center h-screen text-red-600 font-bold">
        Acesso Negado: Você não tem permissão para acessar esta página.
      </div>
    );
  }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingUser ? 'Editar Usuário' : 'Novo Usuário Interno'}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Nome completo e Sobrenome na mesma linha (md:col-span-2 para ocupar a largura total no mobile) */}
          <div className="md:col-span-1"> {/* Nome */}
            <label htmlFor="name" className="block text-sm font-medium text-gray-700">Nome <span className="text-red-500">*</span></label>
            <input
              type="text"
              id="name"
              placeholder="NOME"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
              value={name}
              onChange={(e) => setName(e.target.value.toUpperCase())}
              required
            />
          </div>
          <div className="md:col-span-1"> {/* Sobrenome */}
            <label htmlFor="lastName" className="block text-sm font-medium text-gray-700">Sobrenome</label>
            <input
              type="text"
              id="lastName"
              placeholder="SOBRENOME"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
              value={lastName}
              onChange={(e) => setLastName(e.target.value.toUpperCase())}
            />
          </div>
          {/* E-mail */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">E-mail <span className="text-red-500">*</span></label>
            <input
              type="email"
              id="email"
              placeholder="email@exemplo.com"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={!!editingUser}
            />
          </div>
          {/* Nome de Usuário */}
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700">Nome de Usuário</label>
            <input
              type="text"
              id="username"
              placeholder="nome.de.usuario"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          {/* CPF */}
          <div>
            <label htmlFor="cpf" className="block text-sm font-medium text-gray-700">CPF</label>
            <input
              type="text"
              id="cpf"
              placeholder="000.000.000-00"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={formatCPF(cpf)}
              onChange={(e) => setCpf(e.target.value)}
              maxLength="14"
            />
          </div>
          {/* Celular */}
          <div>
            <label htmlFor="phoneNumber" className="block text-sm font-medium text-gray-700">Celular</label>
            <input
              type="tel"
              id="phoneNumber"
              placeholder="(00)90000-0000"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={formatTelefone(phoneNumber)}
              onChange={(e) => setPhoneNumber(e.target.value)}
              maxLength="15"
            />
          </div>
          
          {!editingUser && (
            <>
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700">Senha <span className="text-red-500">*</span></label>
                <input
                  type="password"
                  id="password"
                  placeholder="********"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">Confirme a Senha <span className="text-red-500">*</span></label>
                <input
                  type="password"
                  id="confirmPassword"
                  placeholder="********"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
              </div>
            </>
          )}
          {editingUser && (
            <div className="md:col-span-2 text-sm text-gray-600 mt-2">
              <p>Para alterar a senha de um usuário existente, preencha os campos abaixo. Isso utilizará uma Cloud Function.</p>
              <div className="flex gap-4 mt-2">
                <div className="w-1/2">
                    <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">Nova Senha (Administrador)</label>
                    <input
                      type="password"
                      id="newPassword"
                      placeholder="Nova senha"
                      className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                </div>
                <div className="w-1/2">
                    <label htmlFor="confirmNewPassword" className="block text-sm font-medium text-gray-700">Confirme Nova Senha</label>
                    <input
                      type="password"
                      id="confirmNewPassword"
                      placeholder="Confirme nova senha"
                      className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                    />
                </div>
              </div>
            </div>
          )}
          <div>
            <label htmlFor="userRole" className="block text-sm font-medium text-gray-700">Função <span className="text-red-500">*</span></label>
            <select
              id="userRole"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={userRole}
              onChange={(e) => setUserRole(e.target.value)}
              required
            >
              <option value="aluno">Aluno</option>
              <option value="professor">Professor</option>
              <option value="secretario">Secretário</option>
              <option value="coordenador">Coordenador</option>
              <option value="diretor">Diretor</option>
              <option value="administrador">Administrador</option>
            </select>
          </div>
          <div>
            <label htmlFor="status" className="block text-sm font-medium text-gray-700">Status <span className="text-red-500">*</span></label>
            <select
              id="status"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              required
            >
              <option value="ativo">Ativo</option>
              <option value="inativo">Inativo</option>
            </select>
          </div>
          {editingUser && status === 'inativo' && (
            <div className="md:col-span-2 text-red-500 text-xs mt-1">
              Desativar um usuário aqui afeta apenas o status no Firestore. Para desativar a conta de autenticação no Firebase (impedir login), é necessária uma Cloud Function.
            </div>
          )}

          {/* Botões de Ação */}
          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingUser && (
              <button
                type="button"
                onClick={resetForm}
                className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded"
              >
                Cancelar Edição
              </button>
            )}
            {/* NOVO BOTÃO: Excluir Usuário */}
            {editingUser && (
              <button
                type="button"
                onClick={() => handleDelete(editingUser.id)}
                className="bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-4 rounded"
              >
                Excluir Usuário
              </button>
            )}
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
            >
              {editingUser ? 'Salvar Alterações' : 'Cadastrar Usuário'}
            </button>
          </div>
        </form>

        <hr className="my-8" />

        {/* Tabela de Usuários Existentes */}
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Lista de Usuários</h3>
        {users.length === 0 ? (
          <p className="text-center text-gray-600">Nenhum usuário cadastrado ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-300 rounded-md">
              <thead>
                <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                  <th className="py-3 px-6 text-left">Nome</th>
                  <th className="py-3 px-6 text-left">E-mail</th>
                  <th className="py-3 px-6 text-left">Função</th>
                  <th className="py-3 px-6 text-left">Status</th>
                  <th className="py-3 px-6 text-center">Ações</th>
                </tr>
              </thead>
              <tbody className="text-gray-600 text-sm font-light">
                {users.map((user) => (
                  <tr key={user.id} className="border-b border-gray-200 hover:bg-gray-100">
                    <td className="py-3 px-6 text-left whitespace-nowrap">{user.nome} {user.sobrenome}</td>
                    <td className="py-3 px-6 text-left">{user.email}</td>
                    <td className="py-3 px-6 text-left">{user.funcao ? user.funcao.charAt(0).toUpperCase() + user.funcao.slice(1) : 'N/A'}</td>
                    <td className="py-3 px-6 text-left">
                      <span className={`py-1 px-3 rounded-full text-xs ${user.ativo ? 'bg-green-200 text-green-600' : 'bg-red-200 text-red-600'}`}>
                        {user.ativo ? 'Ativo' : 'Inativo'}
                      </span>
                    </td>
                    <td className="py-3 px-6 text-center">
                      <div className="flex item-center justify-center space-x-2">
                        <button onClick={() => handleEdit(user)} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-full text-xs">
                          Editar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
	  <Footer /> {/* NOVO: Insere o rodapé aqui */}
    </div>
  );
}

export default UserManagementPage;