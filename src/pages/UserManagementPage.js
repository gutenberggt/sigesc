import React, { useState, useEffect } from 'react';
import { auth, db } from '../firebase/config';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { doc, setDoc, getDocs, collection, query, updateDoc, deleteDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';
import { getFunctions, httpsCallable } from 'firebase/functions';

function UserManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const functions = getFunctions();

  // Cloud Functions Callables (mantidos, mas a lógica de uso será ajustada)
  const toggleUserAccountStatusCallable = httpsCallable(functions, 'toggleUserAccountStatus');
  const adminResetUserPasswordCallable = httpsCallable(functions, 'adminResetUserPassword');
  const adminDeleteUserCallable = httpsCallable(functions, 'adminDeleteUser');

  const [users, setUsers] = useState([]);
  const [editingUser, setEditingUser] = useState(null);

  // --- ESTADOS DOS CAMPOS SIMPLIFICADOS ---
  const [nomeCompleto, setNomeCompleto] = useState(''); // Renomeado de 'name'
  const [email, setEmail] = useState('');
  const [cpf, setCpf] = useState('');
  const [celular, setCelular] = useState(''); // Renomeado de 'phoneNumber'
  const [senha, setSenha] = useState(''); // Corresponde a 'password'
  const [confirmarSenha, setConfirmarSenha] = useState(''); // Corresponde a 'confirmPassword'
  const [funcao, setFuncao] = useState('aluno'); // Corresponde a 'userRole'
  const [status, setStatus] = useState('ativo'); // Corresponde a 'status'

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Limpa o formulário
  const resetForm = () => {
    setNomeCompleto('');
    setEmail('');
    setCpf('');
    setCelular('');
    setSenha('');
    setConfirmarSenha('');
    setFuncao('aluno');
    setStatus('ativo');
    setErrorMessage('');
    setSuccessMessage('');
    setEditingUser(null);
  };

  // Funções de formatação (ajustado nome de formatTelefone para formatCelular)
  const formatCPF = (value) => {
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    return value;
  };

  const formatCelular = (value) => { // Renomeado
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, '($1) $2');
    value = value.replace(/(\d)(\d{4})$/, '$1-$2');
    return value;
  };

  // Função de Validação de CPF (mantida)
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

  // Efeito para carregar usuários existentes (apenas para admins)
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
            // Certifique-se de que os dados do usuário no Firestore tenham 'nomeCompleto', 'telefone' etc.
            // ou ajuste aqui para mapear os campos existentes.
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

  // Função para lidar com o cadastro/edição de usuário
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    const cpfCleaned = cpf.replace(/\D/g, '');

    // Validações
    if (!nomeCompleto || !email || !cpfCleaned || !celular || !funcao || !status) {
      setErrorMessage('Nome Completo, E-mail, CPF, Celular, Função e Status são obrigatórios.');
      return;
    }
    if (!validateCPF(cpfCleaned)) {
      setErrorMessage('CPF inválido.');
      return;
    }
    if (!editingUser) { // Apenas para novo cadastro
      if (!senha || !confirmarSenha) {
        setErrorMessage('Senha e Confirmação de Senha são obrigatórios para novos usuários.');
        return;
      }
      if (senha !== confirmarSenha) {
        setErrorMessage('A senha e a confirmação de senha não coincidem.');
        return;
      }
      if (senha.length < 6) {
        setErrorMessage('A senha deve ter pelo menos 6 caracteres.');
        return;
      }
    }
    // Para edição, se a senha for preenchida, deve coincidir.
    if (editingUser && senha && senha !== confirmarSenha) {
        setErrorMessage('A nova senha e a confirmação não coincidem.');
        return;
    }
    if (editingUser && senha && senha.length < 6) {
        setErrorMessage('A nova senha deve ter pelo menos 6 caracteres.');
        return;
    }

    try {
      let userAuthId = editingUser ? editingUser.id : null;

      if (editingUser) {
        // MODO EDIÇÃO: Atualiza documento no Firestore
        const userDocRef = doc(db, 'users', editingUser.id);
        const updateData = {
          nomeCompleto: nomeCompleto.toUpperCase(), // Usando nomeCompleto
          email: email,
          cpf: cpfCleaned,
          telefone: celular, // Usando 'telefone' no Firestore para 'celular'
          funcao: funcao,
          ativo: status === 'ativo',
          ultimaAtualizacao: new Date(),
        };
        await updateDoc(userDocRef, updateData);

        // Atualiza senha do usuário no Firebase Auth via Cloud Function se uma nova senha for fornecida
        if (senha) {
          try {
            const result = await adminResetUserPasswordCallable({ uid: editingUser.id, newPassword: senha });
            console.log(result.data.message);
            setSuccessMessage('Usuário atualizado com sucesso e senha redefinida (via Cloud Function)!');
          } catch (cfError) {
            console.error("Erro na Cloud Function de reset de senha:", cfError);
            setErrorMessage('Erro ao redefinir senha via Cloud Function: ' + (cfError.message || cfError.code));
            return; // Sai se a redefinição de senha falhar
          }
        } else {
          setSuccessMessage('Usuário atualizado com sucesso!');
        }

        // Atualiza o estado local dos usuários
        setUsers(users.map(u => u.id === editingUser.id ? { ...u, ...updateData } : u));

      } else {
        // MODO CADASTRO DE NOVO USUÁRIO: Cria usuário no Firebase Auth e depois no Firestore
        const userCredential = await createUserWithEmailAndPassword(auth, email, senha);
        userAuthId = userCredential.user.uid;

        await setDoc(doc(db, 'users', userAuthId), {
          nomeCompleto: nomeCompleto.toUpperCase(), // Usando nomeCompleto
          email: email,
          cpf: cpfCleaned,
          telefone: celular, // Usando 'telefone' no Firestore para 'celular'
          funcao: funcao,
          ativo: status === 'ativo',
          criadoEm: new Date(),
          ultimaAtualizacao: new Date(),
        });
        setSuccessMessage('Usuário cadastrado com sucesso! Uma verificação de e-mail pode ser necessária.');

        // Adiciona o novo usuário à lista local
        setUsers([...users, { id: userAuthId, nomeCompleto: nomeCompleto.toUpperCase(), email, funcao: funcao, ativo: status === 'ativo' }]);
      }
      resetForm(); // Limpa o formulário após sucesso

    } catch (error) {
      console.error("Erro ao gerenciar usuário:", error);
      let msg = "Erro ao salvar dados do usuário: " + error.message;
      if (error.code === 'auth/email-already-in-use') {
        msg = 'Este e-mail já está cadastrado.';
      } else if (error.code === 'auth/weak-password') {
        msg = 'A senha é muito fraca. Deve ter pelo menos 6 caracteres.';
      } else if (error.code === 'auth/invalid-email') {
        msg = 'O formato do e-mail é inválido.';
      }
      setErrorMessage(msg);
    }
  };

  // Funções para a tabela: handleEdit
  const handleEdit = (userToEdit) => {
    setEditingUser(userToEdit);
    setNomeCompleto(userToEdit.nomeCompleto || ''); // Corrigido para nomeCompleto
    setEmail(userToEdit.email || '');
    setCpf(formatCPF(userToEdit.cpf || ''));
    setCelular(formatCelular(userToEdit.telefone || '')); // Pega 'telefone' do Firestore para 'celular'
    setFuncao(userToEdit.funcao || 'aluno');
    setStatus(userToEdit.ativo ? 'ativo' : 'inativo');
    setSenha(''); // Senhas nunca são preenchidas para edição
    setConfirmarSenha('');
    setErrorMessage('');
    setSuccessMessage('');
  };

  // Função handleDelete (mantida com Cloud Function)
  const handleDelete = async (userId) => {
    if (window.confirm('Tem certeza que deseja excluir este usuário permanentemente? Esta ação não pode ser desfeita e removerá também a conta de autenticação!')) {
      try {
        const result = await adminDeleteUserCallable({ uid: userId });
        console.log(result.data.message);
        setSuccessMessage('Usuário excluído com sucesso (via Cloud Function)!');
        setUsers(users.filter(user => user.id !== userId));
        resetForm();
      } catch (error) {
        console.error("Erro ao excluir usuário:", error);
        setErrorMessage("Erro ao excluir usuário: " + error.message);
      }
    }
  };

  // Verificação de permissão (apenas admins podem acessar)
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

        {/* Campo de Busca (mantido) */}
        <input
          type="text"
          placeholder="Buscar usuário por nome, CPF ou e-mail..."
          className="w-full p-2 border border-gray-300 rounded-md mb-6"
        />

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Nome Completo */}
          <div className="md:col-span-2"> {/* Ocupa a largura total em telas médias e maiores */}
            <label htmlFor="nomeCompleto" className="block text-sm font-medium text-gray-700">Nome Completo <span className="text-red-500">*</span></label>
            <input
              type="text"
              id="nomeCompleto"
              placeholder="Nome Completo"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
              value={nomeCompleto}
              onChange={(e) => setNomeCompleto(e.target.value.toUpperCase())}
              required
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

          {/* CPF */}
          <div>
            <label htmlFor="cpf" className="block text-sm font-medium text-gray-700">CPF <span className="text-red-500">*</span></label>
            <input
              type="text"
              id="cpf"
              placeholder="000.000.000-00"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={formatCPF(cpf)}
              onChange={(e) => setCpf(e.target.value)}
              maxLength="14"
              required
            />
          </div>

          {/* Celular */}
          <div>
            <label htmlFor="celular" className="block text-sm font-medium text-gray-700">Celular <span className="text-red-500">*</span></label>
            <input
              type="tel"
              id="celular"
              placeholder="(00)90000-0000"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={formatCelular(celular)}
              onChange={(e) => setCelular(e.target.value)}
              maxLength="15"
              required
            />
          </div>

          {/* Função */}
          <div>
            <label htmlFor="funcao" className="block text-sm font-medium text-gray-700">Função <span className="text-red-500">*</span></label>
            <select
              id="funcao"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
              value={funcao}
              onChange={(e) => setFuncao(e.target.value)}
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
          
          {/* Status */}
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

          {/* Senha e Confirmar Senha (apenas para novo cadastro) */}
          {!editingUser && (
            <>
              <div>
                <label htmlFor="senha" className="block text-sm font-medium text-gray-700">Senha <span className="text-red-500">*</span></label>
                <input
                  type="password"
                  id="senha"
                  placeholder="********"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  required={!editingUser}
                />
              </div>
              <div>
                <label htmlFor="confirmarSenha" className="block text-sm font-medium text-gray-700">Confirme a Senha <span className="text-red-500">*</span></label>
                <input
                  type="password"
                  id="confirmarSenha"
                  placeholder="********"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={confirmarSenha}
                  onChange={(e) => setConfirmarSenha(e.target.value)}
                  required={!editingUser}
                />
              </div>
            </>
          )}

          {/* Campos de Nova Senha para Edição */}
          {editingUser && (
            <div className="md:col-span-2 text-sm text-gray-600 mt-2">
              <p>Para alterar a senha do usuário, preencha os campos abaixo. Isso utilizará uma Cloud Function.</p>
              <div className="flex gap-4 mt-2">
                <div className="w-1/2">
                  <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">Nova Senha</label> {/* Removido "(Administrador)" */}
                  <input
                    type="password"
                    id="newPassword"
                    placeholder="Nova senha"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={senha} // Usando o estado 'senha' para a nova senha
                    onChange={(e) => setSenha(e.target.value)}
                  />
                </div>
                <div className="w-1/2">
                  <label htmlFor="confirmNewPassword" className="block text-sm font-medium text-gray-700">Confirme Nova Senha</label>
                  <input
                    type="password"
                    id="confirmNewPassword"
                    placeholder="Confirme nova senha"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={confirmarSenha} // Usando o estado 'confirmarSenha'
                    onChange={(e) => setConfirmarSenha(e.target.value)}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Mensagem de Desativação (Mantido) */}
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
                  <th className="py-3 px-6 text-left">Nome Completo</th> {/* Ajustado */}
                  <th className="py-3 px-6 text-left">E-mail</th>
                  <th className="py-3 px-6 text-left">Função</th>
                  <th className="py-3 px-6 text-left">Status</th>
                  <th className="py-3 px-6 text-center">Ações</th>
                </tr>
              </thead>
              <tbody className="text-gray-600 text-sm font-light">
                {users.map((user) => (
                  <tr key={user.id} className="border-b border-gray-200 hover:bg-gray-100">
                    <td className="py-3 px-6 text-left whitespace-nowrap">{user.nomeCompleto}</td> {/* Ajustado para nomeCompleto */}
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
                        {/* Botão Excluir (Mantido, mas lembre-se que usa Cloud Function) */}
                        <button onClick={() => handleDelete(user.id)} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full text-xs">
                          Excluir
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
    </div>
  );
}

export default UserManagementPage;