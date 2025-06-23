import React, { useState } from "react";
import { auth, db } from "../firebase/config";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { doc, setDoc, serverTimestamp } from "firebase/firestore";
import { useNavigate } from "react-router-dom";

function RegisterPage() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState("");
  const navigate = useNavigate();

  const handleRegister = async (e) => {
    e.preventDefault();
    setErro("");
    setSucesso("");
    try {
      // Criar usuário no Firebase Auth
      const userCredential = await createUserWithEmailAndPassword(auth, email, senha);
      const user = userCredential.user;

      // Criar documento no Firestore na coleção 'users'
      await setDoc(doc(db, "users", user.uid), {
        nome,
        email,
        telefone,
        perfil: null,      // perfil será definido depois pelo admin/secretário
        ativo: false,      // usuário começa inativo
        escolas: [],       // vazio inicialmente
        criadoEm: serverTimestamp(),
      });

      setSucesso("Cadastro realizado com sucesso! Aguarde a ativação pelo responsável.");
      
      // Opcional: limpar campos
      setEmail("");
      setSenha("");
      setNome("");
      setTelefone("");

      // Redirecionar para login após 3 segundos
      setTimeout(() => {
        navigate("/");
      }, 3000);
    } catch (error) {
      console.error(error);
      setErro("Erro ao cadastrar. Verifique os dados e tente novamente.");
    }
  };

  return (
    <div className="flex justify-center items-center h-screen bg-gray-100">
      <form onSubmit={handleRegister} className="bg-white p-8 rounded shadow-md w-full max-w-sm">
        <h2 className="text-2xl font-bold mb-6 text-center">Cadastro</h2>

        <input
          type="text"
          placeholder="Nome completo"
          className="w-full p-2 mb-4 border rounded"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          required
        />
        <input
          type="email"
          placeholder="Email"
          className="w-full p-2 mb-4 border rounded"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="tel"
          placeholder="Telefone"
          className="w-full p-2 mb-4 border rounded"
          value={telefone}
          onChange={(e) => setTelefone(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Senha"
          className="w-full p-2 mb-4 border rounded"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
          minLength={6}
        />

        {erro && <p className="text-red-600 text-sm mb-4">{erro}</p>}
        {sucesso && <p className="text-green-600 text-sm mb-4">{sucesso}</p>}

        <button
          type="submit"
          className="w-full bg-green-600 text-white p-2 rounded hover:bg-green-700"
        >
          Cadastrar
        </button>
      </form>
    </div>
  );
}

export default RegisterPage;
