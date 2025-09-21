import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext";
import {
  updatePassword,
  reauthenticateWithCredential,
  EmailAuthProvider,
} from "firebase/auth";
import { doc, updateDoc } from "firebase/firestore";
import { db } from "../firebase/config";
import { getStorage, ref, uploadBytes, getDownloadURL } from "firebase/storage";

function ProfilePage() {
  const { user, userData, loading, setUserData } = useUser();
  const navigate = useNavigate();

  const [isEditing, setIsEditing] = useState(false);
  const [userName, setUserName] = useState("");
  const [userPhone, setUserPhone] = useState("");
  const [userBio, setUserBio] = useState("");

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");

  const [message, setMessage] = useState({ type: "", text: "" });

  useEffect(() => {
    if (!loading && userData) {
      setUserName(userData.nome || "");
      setUserPhone(userData.telefone || "");
      setUserBio(userData.biografia || "");
    }
  }, [loading, userData]);

  useEffect(() => {
    if (!loading && !user) {
      navigate("/");
    }
  }, [loading, user, navigate]);

  const formatTelefone = (value) => {
    value = value.replace(/\D/g, "");
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, "($1) $2");
    value = value.replace(/(\d)(\d{4})$/, "$1-$2");
    return value;
  };

  const handlePhoneChange = (e) => {
    const digits = e.target.value.replace(/\D/g, "");
    const masked = formatTelefone(digits);
    setUserPhone(masked);
  };

  const handlePhotoUpload = async (e) => {
    try {
      setMessage({ type: "", text: "" });
      const file = e.target.files && e.target.files[0];
      if (!file || !user) return;

      const storage = getStorage();
      const storageRef = ref(storage, `profilePictures/${user.uid}`);
      await uploadBytes(storageRef, file);
      const url = await getDownloadURL(storageRef);

      await updateDoc(doc(db, "users", user.uid), { photoURL: url });

      setUserData((prev) => ({
        ...(prev || {}),
        photoURL: url,
      }));

      setMessage({
        type: "success",
        text: "Foto de perfil atualizada com sucesso!",
      });
    } catch (error) {
      console.error("Erro ao enviar foto:", error);
      setMessage({
        type: "error",
        text: "Erro ao enviar foto. Tente novamente.",
      });
    }
  };

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setMessage({ type: "", text: "" });

    try {
      await updateDoc(doc(db, "users", user.uid), {
        nome: userName.toUpperCase(),
        telefone: userPhone,
        biografia: userBio.trim(),
      });

      setUserData((prevData) => ({
        ...(prevData || {}),
        nome: userName.toUpperCase(),
        telefone: userPhone,
        biografia: userBio.trim(),
      }));

      setMessage({
        type: "success",
        text: "Informações do perfil atualizadas com sucesso!",
      });
      setIsEditing(false);
    } catch (error) {
      console.error("Erro ao atualizar perfil:", error);
      setMessage({
        type: "error",
        text: "Erro ao atualizar perfil: " + error.message,
      });
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setMessage({ type: "", text: "" });

    if (!oldPassword || !newPassword || !confirmNewPassword) {
      setMessage({
        type: "error",
        text: "Todos os campos de senha são obrigatórios.",
      });
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setMessage({
        type: "error",
        text: "A nova senha e a confirmação não coincidem.",
      });
      return;
    }
    if (newPassword.length < 6) {
      setMessage({
        type: "error",
        text: "A nova senha deve ter pelo menos 6 caracteres.",
      });
      return;
    }

    try {
      const credential = EmailAuthProvider.credential(user.email, oldPassword);
      await reauthenticateWithCredential(user, credential);
      await updatePassword(user, newPassword);

      setMessage({ type: "success", text: "Senha alterada com sucesso!" });
      setOldPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
    } catch (error) {
      console.error("Erro ao alterar senha:", error);
      let errorMessage = "Erro ao alterar senha.";
      if (error.code === "auth/wrong-password") {
        errorMessage = "Senha antiga incorreta.";
      } else if (error.code === "auth/requires-recent-login") {
        errorMessage =
          "Você precisa fazer login novamente para alterar a senha.";
      } else if (error.code === "auth/weak-password") {
        errorMessage =
          "A nova senha é muito fraca. Deve ter pelo menos 6 caracteres.";
      }
      setMessage({ type: "error", text: errorMessage });
    }
  };

  const handleGoBack = () => {
    navigate(-1);
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
        <p>
          Erro: Usuário não logado ou dados não disponíveis. Redirecionando...
        </p>
      </div>
    );
  }

  return (
    <div className="flex-grow p-6 bg-gray-100">
      <div className="max-w-3xl mx-auto bg-white p-8 rounded-lg shadow-md">
        <h2 className="text-3xl font-bold text-gray-800 mb-6 text-center">
          Meu Perfil SIGESC
        </h2>

        {message.text && (
          <div
            className={`p-3 mb-6 rounded-md text-center ${
              message.type === "success"
                ? "bg-green-100 text-green-700"
                : "bg-red-100 text-red-700"
            }`}
          >
            {message.text}
          </div>
        )}

        <div className="flex flex-col items-center text-center mb-10">
          <div className="relative w-32 h-32 rounded-full bg-gray-200 overflow-hidden shadow">
            {userData.photoURL ? (
              <img
                src={userData.photoURL}
                alt="Foto de Perfil"
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-gray-500">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  fill="none"
                  className="w-16 h-16"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M17.982 18.725A7.488 7.488 0 0 0 12 15.75a7.488 7.488 0 0 0-5.982 2.975M15 9.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
                  />
                </svg>
              </div>
            )}
            <label
              htmlFor="photo-upload"
              className="absolute bottom-0 right-0 bg-blue-600 hover:bg-blue-700 text-white rounded-full p-2 cursor-pointer shadow"
              title="Trocar foto"
            >
              {/* CORREÇÃO: Adicionado texto acessível para o leitor de tela */}
              <span className="sr-only">Trocar foto de perfil</span>
              <input
                id="photo-upload"
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handlePhotoUpload}
              />
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                fill="none"
                className="w-4 h-4"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M7.5 12l4.5-4.5 4.5 4.5M12 7.5V15"
                />
              </svg>
            </label>
          </div>

          <div className="mt-4">
            <p className="text-2xl font-semibold text-gray-900">
              {userData.nome}
            </p>
            <p className="text-sm text-blue-700">
              {userData.funcao
                ? userData.funcao.charAt(0).toUpperCase() +
                  userData.funcao.slice(1)
                : "Função Não Definida"}
            </p>
            <p className="text-sm text-gray-600">{userData.email}</p>
            <p className="text-sm text-gray-600">
              {formatTelefone(userData.telefone || "")}
            </p>
            <p className="text-gray-800 mt-3">
              {userData.biografia || "Adicione uma biografia ao seu perfil."}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-white p-6 rounded-lg shadow-sm">
            {!isEditing ? (
              <div className="flex flex-col items-center space-y-4">
                <h3 className="text-xl font-semibold text-gray-700 mb-4">
                  Gerenciar Dados
                </h3>
                <button
                  onClick={() => setIsEditing(true)}
                  className="w-full bg-blue-600 text-white py-2 px-4 rounded hover:bg-blue-700 transition"
                >
                  Editar Informações
                </button>
                <button
                  onClick={handleGoBack}
                  className="w-full bg-gray-500 text-white py-2 px-4 rounded hover:bg-gray-600 transition"
                >
                  Voltar
                </button>
              </div>
            ) : (
              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <h3 className="text-xl font-semibold text-gray-700 mb-4">
                  Editar Informações
                </h3>

                <div>
                  <label
                    htmlFor="editName"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Nome Completo
                  </label>
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
                  <label
                    htmlFor="editEmail"
                    className="block text-sm font-medium text-gray-700"
                  >
                    E-mail
                  </label>
                  <input
                    type="email"
                    id="editEmail"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={userData.email || ""}
                    disabled={true}
                  />
                </div>

                <div>
                  <label
                    htmlFor="editPhone"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Telefone
                  </label>
                  <input
                    type="tel"
                    id="editPhone"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={userPhone}
                    onChange={handlePhoneChange}
                    maxLength={15}
                  />
                </div>

                <div>
                  <label
                    htmlFor="editBio"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Biografia
                  </label>
                  <textarea
                    id="editBio"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    rows={3}
                    value={userBio}
                    onChange={(e) => setUserBio(e.target.value)}
                    placeholder="Fale um pouco sobre você..."
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

          <div className="bg-white p-6 rounded-lg shadow-sm">
            <h3 className="text-xl font-semibold text-gray-700 mb-4 text-center">
              Alterar Senha
            </h3>
            <form
              onSubmit={handleChangePassword}
              className="space-y-4 max-w-md mx-auto"
            >
              <div>
                <label
                  htmlFor="oldPassword"
                  className="block text-sm font-medium text-gray-700"
                >
                  Senha Antiga
                </label>
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
                <label
                  htmlFor="newPassword"
                  className="block text-sm font-medium text-gray-700"
                >
                  Nova Senha
                </label>
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
                <label
                  htmlFor="confirmNewPassword"
                  className="block text-sm font-medium text-gray-700"
                >
                  Confirmar Nova Senha
                </label>
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

        <div className="flex justify-end">
          <button
            onClick={handleGoBack}
            className="bg-gray-500 text-white py-2 px-4 rounded hover:bg-gray-600 transition"
          >
            Voltar
          </button>
        </div>
      </div>
    </div>
  );
}

export default ProfilePage;
