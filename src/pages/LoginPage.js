import React, { useState } from "react";
import { Link } from "react-router-dom";
import { auth } from "../firebase/config"; //
import { signInWithEmailAndPassword, signOut } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore"; //
import { db } from "../firebase/config"; //
import { useUser } from "../context/UserContext";
import Footer from "../components/Footer"; //

function LoginPage() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const { setUserData } = useUser();

  const handleLogin = async (e) => {
    e.preventDefault();
    setErro("");
    try {
      const userCredential = await signInWithEmailAndPassword(
        auth,
        email,
        senha
      ); //
      const user = userCredential.user;

      const userDocRef = doc(db, "users", user.uid); //
      const userDocSnap = await getDoc(userDocRef); //

      if (userDocSnap.exists()) {
        //
        const fetchedUserData = userDocSnap.data(); //

        if (fetchedUserData.ativo) {
          //
          setUserData(fetchedUserData);
          window.location.href = "/dashboard"; //
        } else {
          await signOut(auth); //
          setErro(
            "Seu cadastro ainda está aguardando ativação pelo responsável."
          ); //
        }
      } else {
        await signOut(auth); //
        setErro("Usuário não encontrado no sistema."); //
      }
    } catch (error) {
      console.error(error); //
      setErro("Email ou senha inválidos."); //
    }
  };

  return (
    // Remova 'flex-row' do container principal e adicione 'flex flex-col'
    <div className="min-h-screen flex flex-col bg-white">
      {/* NOVO CONTAINER para a ilustração e o formulário, que serão flex-row */}
      <div className="flex flex-grow flex-col md:flex-row">
        {/* Lado esquerdo com imagem e logo */}
        <div className="md:w-1/2 hidden md:flex flex-col justify-center items-center p-6 relative">
          <div className="absolute top-4 left-4">
            <div className="flex items-center gap-2">
              <img
                src="/sigesc_log.png"
                alt="SIGESC Logotipo"
                className="h-10"
              />{" "}
              {/* */}
              <span className="text-2xl font-bold text-gray-800">
                SIGESC
              </span>{" "}
              {/* */}
            </div>
            <p className="text-sm text-gray-600 mt-1">
              Sistema Integrado de Gestão Escolar
            </p>
          </div>
          <img
            src="/login-ilustracao.png"
            alt="Login Ilustração"
            className="w-4/5 max-w-md mt-10"
          />
        </div>

        {/* Lado direito com o formulário */}
        <div className="w-full md:w-1/2 flex justify-center items-center px-6 py-12">
          <div className="bg-white shadow-lg rounded-xl p-8 w-full max-w-md">
            {/* Brasão e textos institucionais */}
            <div className="text-center mb-6 mt-4">
              <img
                src="/brasao_floresta.png"
                alt="Brasão de Floresta"
                className="mx-auto h-16 mb-2"
              />
              <p className="text-base font-semibold text-gray-800">
                Prefeitura Municipal de Floresta do Araguaia
              </p>
              <p className="text-sm text-gray-700">
                Secretaria Municipal de Educação
              </p>
            </div>
            <h2 className="text-2xl font-bold mb-6 text-center text-gray-800">
              Acesse sua conta
            </h2>

            <form onSubmit={handleLogin}>
              <input
                type="email"
                placeholder="Email"
                className="w-full p-3 mb-4 border border-gray-300 rounded-lg"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <input
                type="password"
                placeholder="Senha"
                className="w-full p-3 mb-4 border border-gray-300 rounded-lg"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
              />
              {erro && <p className="text-red-600 text-sm mb-4">{erro}</p>}
              <button
                type="submit"
                className="w-full bg-blue-600 text-white p-3 rounded-lg hover:bg-blue-700 transition duration-200"
              >
                Entrar
              </button>
            </form>

            <p className="text-sm text-center mt-4">
              Ainda não tem conta?{" "}
              <Link to="/cadastro" className="text-blue-600 underline">
                Cadastre-se
              </Link>
            </p>
            <p className="text-sm text-center mt-2">
              <Link to="/recuperar-senha" className="text-blue-600 underline">
                Esqueceu sua senha?
              </Link>
            </p>
          </div>
        </div>
      </div>{" "}
      {/* Fim do NOVO CONTAINER para a ilustração e o formulário */}
      <Footer />{" "}
      {/* O rodapé agora está fora do flex-row e será empurrado para baixo */}
    </div>
  );
}

export default LoginPage;
