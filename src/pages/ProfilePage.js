import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useUser } from '../context/UserContext';
import { updateProfile, updatePassword, reauthenticateWithCredential, EmailAuthProvider } from 'firebase/auth';
import { doc, updateDoc } from 'firebase/firestore';
import { auth, db } from '../firebase/config';
import Footer from '../components/Footer';

function ProfilePage() {
  const { user, userData, loading, setUserData } = useUser();
  const navigate = useNavigate();

  const [isEditing, setIsEditing] = useState(false);
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [userPhone, setUserPhone] = useState('');
  const [userCpf, setUserCpf] = useState('');

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');

  const [message, setMessage] = useState({ type: '', text: '' });

  // Carrega os dados do usuário ao iniciar ou quando userData muda
  useEffect(() => {
    if (!loading && userData) {
      setUserName(userData.nome || '');
      setUserEmail(userData.email || '');
      setUserPhone(userData.telefone || '');
      setUserCpf(userData.cpf || '');
    }
  }, [loading, userData]);

  // Redireciona se não estiver logado ou carregando
  useEffect(() => {
    if (!loading && !user) {
      navigate('/');
    }
  }, [loading, user, navigate]);

  // Funções de formatação CPF/Telefone
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

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setMessage({ type: '', text: '' });

    if (userCpf && !validateCPF(userCpf.replace(/\D/g, ''))) {
      setMessage({ type: 'error', text: 'CPF inválido.' });
      return;
    }

    try {
      await updateDoc(doc(db, 'users', user.uid), {
        nome: userName.toUpperCase(),
        telefone: userPhone,
        cpf: userCpf.replace(/\D/g, ''),
      });

      setUserData(prevData => ({
        ...prevData,
        nome: userName.toUpperCase(),
        telefone: userPhone,
        cpf: userCpf.replace(/\D/g, ''),
      }));

      setMessage({ type: 'success', text: 'Informações do perfil atualizadas com sucesso!' });
      setIsEditing(false);
    } catch (error) {
      console.error("Erro ao atualizar perfil:", error);
      setMessage({ type: 'error', text: 'Erro ao atualizar perfil: ' + error.message });
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setMessage({ type: '', text: '' });

    if (!oldPassword || !newPassword || !confirmNewPassword) {
      setMessage({ type: 'error', text: 'Todos os campos de senha são obrigatórios.' });
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setMessage({ type: 'error', text: 'A nova senha e a confirmação não coincidem.' });
      return;
    }
    if (newPassword.length < 6) {
      setMessage({ type: 'error', text: 'A nova senha deve ter pelo menos 6 caracteres.' });
      return;
    }

    try {
      const credential = EmailAuthProvider.credential(user.email, oldPassword);
      await reauthenticateWithCredential(user, credential);

      await updatePassword(user, newPassword);

      setMessage({ type: 'success', text: 'Senha alterada com sucesso!' });
      setOldPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
    } catch (error) {
      console.error("Erro ao alterar senha:", error);
      let errorMessage = 'Erro ao alterar senha.';
      if (error.code === 'auth/wrong-password') {
        errorMessage = 'Senha antiga incorreta.';
      } else if (error.code === 'auth/requires-recent-login') {
        errorMessage = 'Você precisa fazer login novamente para alterar a senha.';
      } else if (error.code === 'auth/weak-password') {
        errorMessage = 'A nova senha é muito fraca. Deve ter pelo menos 6 caracteres.';
      }
      setMessage({ type: 'error', text: errorMessage });
    }
  };

  const handleGoBack = () => {
    navigate(-1); // Volta para a página anterior
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-gray-700">Carregando perfil...</p>
      </div>
    );
  }

  if (!user || !userData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-red-100 text-red-700">
        <p>Erro: Usuário não logado ou dados não disponíveis. Redirecionando...</p>
      </div>
    );
  }

  return (
    <div className="flex-grow p-6 bg-gray-100">
      <div className="max-w-3xl mx-auto bg-white p-8 rounded-lg shadow-md">
        <h2 className="text-3xl font-bold text-gray-800 mb-6 text-center">Meu Perfil</h2>
        
        {message.text && (
          <div className={`p-3 mb-4 rounded-md text-center ${message.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
            {message.text}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Cartão de Informações Básicas com Foto */}
          <div className="bg-blue-50 p-6 rounded-lg shadow-sm flex flex-col items-center justify-center text-center">
            {/* Foto de Perfil - Placeholder ou imagem do usuário */}
            <div className="relative w-24 h-24 rounded-full bg-gray-300 flex items-center justify-center overflow-hidden mb-4">
              {userData.photoURL ? (
                <img src={userData.photoURL} alt="Foto de Perfil" className="w-full h-full object-cover" />
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-16 h-16 text-gray-600">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17.982 18.725A7.488 7.488 0 0 0 12 15.75a7.488 7.488 0 0 0-5.982 2.975M15 9.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                </svg>
              )}
              {/* Botão para Upload de Foto (Interface) */}
              <label htmlFor="photo-upload" className="absolute bottom-0 right-0 bg-blue-500 rounded-full p-1 cursor-pointer hover:bg-blue-600 transition">
                <input id="photo-upload" type="file" accept="image/*" className="hidden" /* onChange={handlePhotoUpload} - futura função */ />
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5 text-white">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175-.16.023-.32.046-.48.069-.07.01-.14.02-.21.033a.75.75 0 0 0-.25.127A.75.75 0 0 0 3 8.375V18.75c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V8.375c0-.131-.052-.25-.13-.348a.749.749 0 0 0-.21-.033 49.36 49.36 0 0 1-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.106-.17c-.573-.916-1.547-1.48-2.614-1.48 0 0-1.036 0-1.036 0Zm-3.13 5.845a.75.75 0 0 1 0-1.5h.008a.75.75 0 0 1 0 1.5H3.697ZM9.54 9a.75.75 0 0 0-1.5 0v1.25c0 .414.336.75.75.75h.75a.75.75 0 0 0 0-1.5h-.008V9Zm2.25-1.5a.75.75 0 0 0-1.5 0v.75a.75.75 0 0 0 1.5 0V7.5ZM13.5 9a.75.75 0 0 0-1.5 0v.75a.75.75 0 0 0 1.5 0V9Z" />
                </svg>
              </label>
            </div>

            <p className="text-xl font-semibold text-gray-800">{userData.nome}</p>
            <p className="text-sm text-blue-700">{userData.funcao ? userData.funcao.charAt(0).toUpperCase() + userData.funcao.slice(1) : 'Função Não Definida'}</p>
            <p className="text-sm text-gray-600">{userData.email}</p>
            <p className="text-sm text-gray-600">{formatTelefone(userData.telefone || '')}</p>
            <p className="text-sm text-gray-600">{formatCPF(userData.cpf || '')}</p>
          </div>

          {/* Cartão de Ações ou Edição */}
          <div className="bg-white p-6 rounded-lg shadow-sm">
            {!isEditing ? (
              <div className="flex flex-col items-center space-y-4">
                <h3 className="text-xl font-semibold text-gray-700 mb-4">Gerenciar Dados</h3>
                <button
                  onClick={() => setIsEditing(true)}
                  className="w-full bg-blue-600 text-white py-2 px-4 rounded hover:bg-blue-700 transition"
                >
                  Editar Informações
                </button>
                <button
                  onClick={handleGoBack} // Botão Voltar
                  className="w-full bg-gray-500 text-white py-2 px-4 rounded hover:bg-gray-600 transition"
                >
                  Voltar
                </button>
              </div>
            ) : (
              // Formulário de Edição de Informações
              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <h3 className="text-xl font-semibold text-gray-700 mb-4">Editar Informações</h3>
                <div>
                  <label htmlFor="editName" className="block text-sm font-medium text-gray-700">Nome Completo</label>
                  <input
                    type="text"
                    id="editName"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                    value={userName}
                    onChange={(e) => setUserName(e.target.value.toUpperCase())}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="editPhone" className="block text-sm font-medium text-gray-700">Telefone</label>
                  <input
                    type="tel"
                    id="editPhone"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={formatTelefone(userPhone)}
                    onChange={(e) => setUserPhone(e.target.value)}
                    maxLength="15"
                  />
                </div>
                <div>
                  <label htmlFor="editCpf" className="block text-sm font-medium text-gray-700">CPF</label>
                  <input
                    type="text"
                    id="editCpf"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={formatCPF(userCpf)}
                    onChange={(e) => setUserCpf(e.target.value)}
                    maxLength="14"
                  />
                </div>
                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => setIsEditing(false)}
                    className="bg-gray-300 hover:bg-gray-400 text-gray-800 py-2 px-4 rounded transition"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    className="bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded transition"
                  >
                    Salvar
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>

        {/* Seção de Alterar Senha */}
        <div className="bg-white p-6 rounded-lg shadow-md mt-8">
          <h3 className="text-xl font-semibold text-gray-700 mb-4 text-center">Alterar Senha</h3>
          <form onSubmit={handleChangePassword} className="space-y-4 max-w-md mx-auto">
            <div>
              <label htmlFor="oldPassword" className="block text-sm font-medium text-gray-700">Senha Antiga</label>
              <input
                type="password"
                id="oldPassword"
                className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">Nova Senha</label>
              <input
                type="password"
                id="newPassword"
                className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="confirmNewPassword" className="block text-sm font-medium text-gray-700">Confirmar Nova Senha</label>
              <input
                type="password"
                id="confirmNewPassword"
                className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                value={confirmNewPassword}
                onChange={(e) => setConfirmNewPassword(e.target.value)}
                required
              />
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded transition"
              >
                Alterar Senha
              </button>
            </div>
          </form>
        </div>
      </div>
	  <Footer /> {/* NOVO: Insere o rodapé aqui */}
    </div>
  );
}

export default ProfilePage;