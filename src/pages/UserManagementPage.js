import React, { useState, useEffect } from 'react';
import { auth, db } from '../firebase/config';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { doc, setDoc, getDocs, collection, query, updateDoc, deleteDoc, where, getDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';
import { getFunctions, httpsCallable } from 'firebase/functions';

function UserManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const functions = getFunctions();

  // Cloud Functions Callables
  const toggleUserAccountStatusCallable = httpsCallable(functions, 'toggleUserAccountStatus');
  const adminResetUserPasswordCallable = httpsCallable(functions, 'adminResetUserPassword');
  const adminDeleteUserCallable = httpsCallable(functions, 'adminDeleteUser');

  const [users, setUsers] = useState([]);
  const [editingUser, setEditingUser] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  // --- ESTADOS DOS CAMPOS DO FORMULÁRIO ---
  const [nomeCompleto, setNomeCompleto] = useState('');
  const [email, setEmail] = useState('');
  const [cpf, setCpf] = useState('');
  const [celular, setCelular] = useState('');
  const [senha, setSenha] = useState('');
  const [confirmarSenha, setConfirmarSenha] = useState('');
  const [funcao, setFuncao] = useState('aluno'); // Função primária do usuário (individual)
  const [status, setStatus] = useState('ativo');

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // --- NOVOS ESTADOS PARA A SEÇÃO DE PERMISSÕES ---
  const [userPermissions, setUserPermissions] = useState([]); // Array de objetos { permissao: '...', escolaId: '...', pessoaId: '...' }
  const [currentPermission, setCurrentPermission] = useState('aluno'); // Permissão selecionada no dropdown
  const [currentSchoolId, setCurrentSchoolId] = useState(''); // Escola selecionada para a permissão
  const [availableSchools, setAvailableSchools] = useState([]); // Lista de escolas que o usuário logado pode gerenciar/ver

  const [searchPersonName, setSearchPersonName] = useState(''); // Nome para busca de aluno/professor
  const [personSuggestions, setPersonSuggestions] = useState([]); // Sugestões de nomes de alunos/professores
  const [selectedPersonId, setSelectedPersonId] = useState(''); // ID da pessoa selecionada (aluno/professor)


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
    setUserPermissions([]); // Limpa as permissões também
    setCurrentPermission('aluno');
    setCurrentSchoolId('');
    setSearchPersonName('');
    setPersonSuggestions([]);
    setSelectedPersonId('');
    setErrorMessage('');
    setSuccessMessage('');
    setEditingUser(null);
  };

  // Funções de formatação CPF/Celular (mantidas)
  const formatCPF = (value) => {
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    return value;
  };

  const formatCelular = (value) => {
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

  // Filtra usuários para a busca
  const filteredUsers = users.filter(user =>
    (user.nomeCompleto && user.nomeCompleto.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (user.cpf && user.cpf.includes(searchTerm)) ||
    (user.email && user.email.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  // Efeito para carregar usuários existentes e escolas disponíveis
  useEffect(() => {
    if (!loading) {
      // Verifica permissões para acessar a página
      if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
        navigate('/dashboard');
        return;
      }

      const fetchUsersAndSchools = async () => {
        try {
          // Busca de Usuários
          const usersCol = collection(db, 'users');
          const userSnapshot = await getDocs(usersCol);
          const userList = userSnapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data()
          }));
          setUsers(userList);

          // Busca e Filtra Escolas para o Dropdown de Unidades
          const schoolsCol = collection(db, 'schools');
          const schoolsSnapshot = await getDocs(schoolsCol);
          let schoolsList = schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));

          // Se for Secretário, filtra as escolas que ele está associado
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


  // Lógica para adicionar uma permissão
  const handleAddPermission = () => {
    if (!currentPermission || !currentSchoolId) {
      setErrorMessage("Selecione a Permissão e a Unidade (Escola) para adicionar.");
      return;
    }
    // Verifica se a permissão já existe para evitar duplicatas
    const isDuplicate = userPermissions.some(p =>
      p.permissao === currentPermission && p.escolaId === currentSchoolId && p.pessoaId === selectedPersonId // Incluído pessoaId na verificação de duplicidade
    );

    if (isDuplicate) {
      setErrorMessage("Esta permissão para esta unidade já foi adicionada.");
      return;
    }

    // Validação extra para aluno/professor se a pessoa não foi selecionada
    if ((currentPermission === 'aluno' || currentPermission === 'professor') && !selectedPersonId) {
        setErrorMessage(`Selecione um(a) ${currentPermission} da lista de sugestões.`);
        return;
    }


    const newPermission = {
      permissao: currentPermission,
      escolaId: currentSchoolId,
      // Se for aluno ou professor, adiciona o ID da pessoa associada
      pessoaId: (currentPermission === 'aluno' || currentPermission === 'professor') ? selectedPersonId : null,
      pessoaNome: (currentPermission === 'aluno' || currentPermission === 'professor') ? searchPersonName : null,
    };

    setUserPermissions([...userPermissions, newPermission]);
    setCurrentPermission('aluno'); // Reseta para o padrão
    setCurrentSchoolId(''); // Reseta a escola selecionada
    setSearchPersonName(''); // Reseta o campo de busca de pessoa
    setPersonSuggestions([]);
    setSelectedPersonId('');
    setErrorMessage(''); // Limpa a mensagem de erro
  };

  // Lógica para remover uma permissão
  const handleRemovePermission = (index) => {
    const updatedPermissions = [...userPermissions];
    updatedPermissions.splice(index, 1);
    setUserPermissions(updatedPermissions);
  };

  // Lógica para sugestões de Aluno/Professor (IMPLEMENTAÇÃO REAL DE BUSCA NO FIRESTORE)
  useEffect(() => {
    if (searchPersonName.length >= 3 && (currentPermission === 'aluno' || currentPermission === 'professor')) {
      const fetchSuggestions = async () => {
        try {
          const collectionToSearch = currentPermission === 'aluno' ? 'students' : 'professors'; // Assumindo coleção 'professors' para servidores
          const q = query(
            collection(db, collectionToSearch),
            where('nomeCompleto', '>=', searchPersonName.toUpperCase()),
            where('nomeCompleto', '<=', searchPersonName.toUpperCase() + '\uf8ff')
            // Pode adicionar where('escolaId', '==', currentSchoolId) para filtrar por escola se necessário
          );
          const querySnapshot = await getDocs(q);
          const suggestions = querySnapshot.docs.map(doc => ({
            id: doc.id,
            nome: doc.data().nomeCompleto,
          }));
          setPersonSuggestions(suggestions);
        } catch (error) {
          console.error("Erro ao buscar sugestões:", error);
          setPersonSuggestions([]);
        }
      };
      const handler = setTimeout(() => {
        fetchSuggestions();
      }, 300); // Debounce para não buscar a cada tecla
      return () => clearTimeout(handler);
    } else {
      setPersonSuggestions([]);
    }
  }, [searchPersonName, currentPermission]); // Depende também do currentPermission


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
    // Validação para permissões: ao menos uma é necessária, exceto para Aluno
    if (userPermissions.length === 0 && funcao !== 'aluno') {
        setErrorMessage('Pelo menos uma permissão de Unidade/Escola é obrigatória para este perfil de usuário.');
        return;
    }
    // Validação para o campo pessoaId se a permissão for aluno ou professor
    const alunoOuProfessorPermissaoIncompleta = userPermissions.some(p => 
        (p.permissao === 'aluno' || p.permissao === 'professor') && !p.pessoaId
    );
    if (alunoOuProfessorPermissaoIncompleta) {
        setErrorMessage('Para permissões de Aluno ou Professor, você deve selecionar a pessoa na lista de sugestões.');
        return;
    }


    try {
      let userAuthId = editingUser ? editingUser.id : null;

      if (editingUser) {
        // MODO EDIÇÃO: Atualiza documento no Firestore
        const userDocRef = doc(db, 'users', editingUser.id);
        const updateData = {
          nomeCompleto: nomeCompleto.toUpperCase(),
          email: email,
          cpf: cpfCleaned,
          telefone: celular,
          funcao: funcao, // Função primária
          ativo: status === 'ativo',
          permissoes: userPermissions, // Salva as permissões detalhadas
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
            return;
          }
        } else {
          setSuccessMessage('Usuário atualizado com sucesso!');
        }

        setUsers(users.map(u => u.id === editingUser.id ? { ...u, ...updateData } : u));

      } else {
        // MODO CADASTRO DE NOVO USUÁRIO: Cria usuário no Firebase Auth e depois no Firestore
        const userCredential = await createUserWithEmailAndPassword(auth, email, senha);
        userAuthId = userCredential.user.uid;

        await setDoc(doc(db, 'users', userAuthId), {
          nomeCompleto: nomeCompleto.toUpperCase(),
          email: email,
          cpf: cpfCleaned,
          telefone: celular,
          funcao: funcao,
          ativo: status === 'ativo',
          permissoes: userPermissions, // Salva as permissões detalhadas
          criadoEm: new Date(),
          ultimaAtualizacao: new Date(),
          // Campos para regras de segurança (escolaId, escolasIds, turmasIds)
          // extraídos da primeira permissão ou de todas as permissões
          escolaId: userPermissions.length > 0 && userPermissions[0].escolaId ? userPermissions[0].escolaId : null,
          escolasIds: userPermissions.filter(p => p.escolaId).map(p => p.escolaId),
          turmasIds: userPermissions.filter(p => (p.permissao === 'aluno' || p.permissao === 'professor') && p.pessoaId).map(p => p.pessoaId)
        });
        setSuccessMessage('Usuário cadastrado com sucesso! Uma verificação de e-mail pode ser necessária.');

        setUsers([...users, { id: userAuthId, nomeCompleto: nomeCompleto.toUpperCase(), email, funcao: funcao, ativo: status === 'ativo', permissoes: userPermissions }]);
      }
      resetForm();

    } catch (error) {
      console.error("Erro ao gerenciar usuário:", error);
      let msg = "Erro ao salvar dados do usuário: " + error.message;
      if (error.code === 'auth/email-already-in-use') {
        msg = 'Este e-mail já está em uso por outro usuário.';
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
    setNomeCompleto(userToEdit.nomeCompleto || '');
    setEmail(userToEdit.email || '');
    setCpf(formatCPF(userToEdit.cpf || ''));
    setCelular(formatCelular(userToEdit.telefone || ''));
    setFuncao(userToEdit.funcao || 'aluno');
    setStatus(userToEdit.ativo ? 'ativo' : 'inativo');
    setUserPermissions(userToEdit.permissoes || []); // Popula as permissões existentes
    setSenha('');
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

  // Verificação de permissão (apenas admins e secretários podem acessar)
  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        Carregando permissões...
      </div>
    );
  }

  // Redireciona se não for admin ou secretário
  if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
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

        {/* Campo de Busca */}
        <input
          type="text"
          placeholder="Buscar usuário por nome, CPF ou e-mail..."
          className="w-full p-2 border border-gray-300 rounded-md mb-6"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          autoComplete="off"
        />

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Nome Completo */}
          <div className="md:col-span-2">
            <label htmlFor="nomeCompleto" className="block text-sm font-medium text-gray-700">Nome Completo <span className="text-red-500">*</span></label>
            <input
              type="text"
              id="nomeCompleto"
              placeholder="Nome Completo"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
              value={nomeCompleto}
              onChange={(e) => setNomeCompleto(e.target.value.toUpperCase())}
              required
              autoComplete="off"
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
              autoComplete="off"
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
              autoComplete="off"
            />
          </div>

          {/* Celular */}
          <div className="md:col-span-2 flex flex-col md:flex-row gap-4">
            <div className="w-full md:w-1/3">
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
                autoComplete="off"
              />
            </div>

            {/* Função Primária (individual) */}
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

            {/* Status */}
            <div className="w-full md:w-1/3">
              <label htmlFor="status" className="block text-sm font-medium text-gray-700">Status <span className="text-red-500">*</span></label>
              <select
                id="status"
                className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                required
                autoComplete="off"
              >
                <option value="ativo">Ativo</option>
                <option value="inativo">Inativo</option>
              </select>
            </div>
          </div>
          {/* FIM DO CONTAINER PARA CELULAR, FUNÇÃO E STATUS */}

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
                  autoComplete="new-password"
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
                  autoComplete="new-password"
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
                  <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">Nova Senha</label>
                  <input
                    type="password"
                    id="newPassword"
                    placeholder="Nova senha"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={senha}
                    onChange={(e) => setSenha(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
                <div className="w-1/2">
                  <label htmlFor="confirmNewPassword" className="block text-sm font-medium text-gray-700">Confirme Nova Senha</label>
                  <input
                    type="password"
                    id="confirmNewPassword"
                    placeholder="Confirme nova senha"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={confirmarSenha}
                    onChange={(e) => setConfirmarSenha(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
              </div>
            </div>
          )}

          {/* INÍCIO DA SEÇÃO DE PERMISSÕES */}
          {/* Agora, esta seção aparecerá sempre, independentemente da Função Primária */}
          <div className="md:col-span-2 border p-4 rounded-lg bg-gray-50 mt-4">
            <h3 className="text-lg font-semibold text-gray-700 mb-4">Permissões de Acesso por Unidade</h3>
            
            {/* Formulário para Adicionar Nova Permissão */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end mb-4">
              {/* Permissão */}
              <div>
                <label htmlFor="currentPermission" className="block text-sm font-medium text-gray-700">Permissão</label>
                <select
                  id="currentPermission"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={currentPermission}
                  onChange={(e) => {
                      setCurrentPermission(e.target.value);
                      setSearchPersonName(''); // Limpa a busca ao mudar a permissão
                      setPersonSuggestions([]);
                      setSelectedPersonId('');
                  }}
                  autoComplete="off"
                >
                  <option value="aluno">Aluno</option>
                  <option value="professor">Professor</option>
                  <option value="secretario">Secretário</option>
                  <option value="coordenador">Coordenador</option>
                  <option value="diretor">Diretor</option>
                  
                </select>
              </div>

              {/* Unidade (Escola) */}
              <div>
                <label htmlFor="currentSchoolId" className="block text-sm font-medium text-gray-700">Unidade (Escola)</label>
                <select
                  id="currentSchoolId"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={currentSchoolId}
                  onChange={(e) => setCurrentSchoolId(e.target.value)}
                  autoComplete="off"
                >
                  <option value="">Selecione uma Escola</option>
                  {availableSchools.map(school => (
                    <option key={school.id} value={school.id}>{school.nomeEscola}</option>
                  ))}
                </select>
              </div>

              {/* Botão Adicionar Permissão */}
              <button
                type="button"
                onClick={handleAddPermission}
                className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition h-10 flex items-center justify-center"
              >
                Adicionar Permissão
              </button>
            </div>

            {/* Campo de Busca de Aluno/Professor (Condicional) */}
            {(currentPermission === 'aluno' || currentPermission === 'professor') && (
              <div className="mb-4 relative">
                <label htmlFor="searchPersonName" className="block text-sm font-medium text-gray-700">
                  {currentPermission === 'aluno' ? 'Buscar Aluno' : 'Buscar Professor'}
                </label>
                <input
                  type="text"
                  id="searchPersonName"
                  placeholder={`Digite o nome do ${currentPermission} (mín. 3 letras)`}
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={searchPersonName}
                  onChange={(e) => {
                    setSearchPersonName(e.target.value);
                    setSelectedPersonId(''); // Reseta o ID selecionado ao digitar
                  }}
                  autoComplete="off"
                />
                {searchPersonName.length >=3 && personSuggestions.length > 0 && (
                  <ul className="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto mt-1">
                    {personSuggestions.map(person => (
                      <li
                        key={person.id}
                        className="p-2 cursor-pointer hover:bg-gray-200"
                        onClick={() => {
                          setSearchPersonName(person.nome); // Mostra o nome completo
                          setSelectedPersonId(person.id); // Salva o ID real
                          setPersonSuggestions([]); // Fecha as sugestões
                        }}
                      >
                        {person.nome}
                      </li>
                    ))}
                  </ul>
                )}
                {searchPersonName.length >=3 && personSuggestions.length === 0 && (
                    <p className="text-sm text-gray-500 mt-1">Nenhuma sugestão encontrada.</p>
                )}
                {selectedPersonId && (
                    <p className="text-sm text-gray-600 mt-1">Pessoa selecionada: {searchPersonName}</p>
                )}
              </div>
            )}

            {/* Lista de Permissões Adicionadas */}
            {userPermissions.length > 0 && (
              <div className="mt-4 border-t pt-4">
                <h4 className="text-md font-semibold text-gray-700 mb-2">Permissões Atribuídas:</h4>
                <ul className="space-y-2">
                  {userPermissions.map((perm, index) => (
                    <li key={index} className="flex justify-between items-center bg-white p-3 rounded-md shadow-sm border border-gray-200">
                      <span>
                        <span className="font-medium text-blue-700">{perm.permissao.charAt(0).toUpperCase() + perm.permissao.slice(1)}</span>
                        {perm.escolaId && ` em ${availableSchools.find(s => s.id === perm.escolaId)?.nomeEscola || 'Escola Desconhecida'}`}
                        {(perm.pessoaNome && (perm.permissao === 'aluno' || perm.permissao === 'professor')) && ` (${perm.pessoaNome})`}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRemovePermission(index)}
                        className="text-red-500 hover:text-red-700 p-1 rounded-full"
                        title="Remover Permissão"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {/* FIM DA SEÇÃO DE PERMISSÕES */}


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
        {filteredUsers.length === 0 ? (
          <p className="text-center text-gray-600">Nenhum usuário cadastrado ou encontrado.</p>
        ) : (
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