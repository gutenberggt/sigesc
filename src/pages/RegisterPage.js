import React, { useState } from "react";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { auth, db } from "../firebase/config";
import { doc, setDoc } from "firebase/firestore";
import { Link } from "react-router-dom";
import Footer from "../components/Footer";

function RegisterPage() {
  const [nome, setNome] = useState("");
  const [cpf, setCpf] = useState("");
  const [telefone, setTelefone] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [perfilSelecionado, setPerfilSelecionado] = useState("aluno");
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState("");

  // Funções de formatação (mantidas)
  const formatCPF = (value) => {
    value = value.replace(/\D/g, "");
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/(\d{3})(\d)/, "$1.$2");
    value = value.replace(/(\d{3})(\d)/, "$1.$2");
    value = value.replace(/(\d{3})(\d{1,2})$/, "$1-$2");
    return value;
  };

  const formatTelefone = (value) => {
    value = value.replace(/\D/g, "");
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, "($1) $2");
    value = value.replace(/(\d)(\d{4})$/, "$1-$2");
    return value;
  };

  // Função de Validação de CPF (mantida)
  const validateCPF = (rawCpf) => {
    let cpfCleaned = rawCpf.replace(/\D/g, "");
    if (cpfCleaned.length !== 11) return false;
    if (/^(\d)\1{10}$/.test(cpfCleaned)) return false;

    let sum = 0;
    let remainder;
    for (let i = 1; i <= 9; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (11 - i);
    }
    remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(9, 10))) return false;

    sum = 0;
    for (let i = 1; i <= 10; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (12 - i);
    }
    remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(10, 11))) return false;

    return true;
  };

  const handleCadastro = async (e) => {
    e.preventDefault();
    setErro("");
    setSucesso("");

    if (senha !== confirmarSenha) {
      setErro("As senhas não coincidem. Por favor, verifique.");
      return;
    }

    const cpfCleaned = cpf.replace(/\D/g, "");
    if (!validateCPF(cpfCleaned)) {
      setErro("CPF inválido. Por favor, verifique o número digitado.");
      return;
    }

    try {
      const userCredential = await createUserWithEmailAndPassword(
        auth,
        email,
        senha
      );
      const user = userCredential.user;

      await setDoc(doc(db, "users", user.uid), {
        nome,
        cpf: cpfCleaned,
        telefone,
        email,
        ativo: false,
        funcao: perfilSelecionado,
      });

      setSucesso(
        "Cadastro realizado com sucesso! Aguarde a ativação do seu acesso."
      );
    } catch (error) {
      console.error(error);
      if (error.code === "auth/email-already-in-use") {
        setErro(
          "Este e-mail já está em uso. Tente outro ou recupere sua senha."
        );
      } else {
        setErro("Erro ao realizar cadastro. Verifique os dados.");
      }
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <div className="flex flex-grow flex-col md:flex-row items-center justify-center py-6 md:py-0">
        {/* Lado esquerdo com logo e ilustração */}
        {/* Adicionado flex-col e justify-between para posicionar logo no topo e ilustração centralizada */}
        <div className="md:w-1/2 hidden md:flex flex-col justify-between items-center p-6 md:pr-12">
          {/* Container para o Logo SIGESC - Posicionado no topo e alinhado à esquerda */}
          <div className="w-full pl-6 pt-6 flex-shrink-0">
            {" "}
            {/* pl-6 e pt-6 para padding do topo/esquerda */}
            <div className="flex items-center gap-2">
              <img
                src="/sigesc_log.png"
                alt="SIGESC Logotipo"
                className="h-10"
              />
              <span className="text-2xl font-bold text-gray-800">SIGESC</span>
            </div>
            <p className="text-sm text-gray-600 mt-1">
              Sistema Integrado de Gestão Escolar
            </p>
          </div>

          {/* Ilustração - Agora centralizada e maior */}
          <div className="flex-grow flex items-center justify-center p-6">
            {" "}
            {/* Garante que a imagem cresça e se centralize */}
            <img
              src="/login-ilustracao.png"
              alt="Ilustração"
              className="w-full max-w-lg" // w-full para preencher o div, max-w-lg para limitar o tamanho
            />
          </div>
        </div>

        {/* Lado direito com o formulário */}
        <div className="flex justify-center items-center px-6 py-12 md:w-1/2 lg:w-2/5">
          <div className="bg-white shadow-lg rounded-xl p-8 w-full max-w-lg">
            {/* Brasão e textos institucionais */}
            <div className="text-center mb-6 mt-4">
              <img
                src="/brasao_floresta.png"
                alt="Brasão"
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
              Crie sua conta
            </h2>

            <form onSubmit={handleCadastro}>
              {/* Campo Nome Completo */}
              <input
                type="text"
                placeholder="Nome completo"
                className="w-full p-3 mb-4 border border-gray-300 rounded-lg uppercase"
                value={nome}
                onChange={(e) => setNome(e.target.value.toUpperCase())}
                required
              />

              {/* Container flexível para Seleção de Perfil e CPF */}
              <div className="flex flex-col md:flex-row gap-4 mb-4">
                <select
                  className="w-full md:w-1/2 p-3 border border-gray-300 rounded-lg"
                  value={perfilSelecionado}
                  onChange={(e) => setPerfilSelecionado(e.target.value)}
                  required
                >
                  <option value="aluno">Aluno</option>
                  <option value="professor">Professor</option>
                  <option value="secretario">Secretário</option>
                  <option value="coordenador">Coordenador</option>
                  <option value="diretor">Diretor</option>
                  <option value="administrador">Administrador</option>
                </select>

                {/* Campo CPF com formatação e validação */}
                <input
                  type="text"
                  placeholder="CPF"
                  className="w-full md:w-1/2 p-3 border border-gray-300 rounded-lg"
                  value={formatCPF(cpf)}
                  onChange={(e) => setCpf(e.target.value)}
                  maxLength="14"
                  required
                />
              </div>

              {/* Campo Telefone com formatação */}
              <input
                type="tel"
                placeholder="Telefone"
                className="w-full p-3 mb-4 border border-gray-300 rounded-lg"
                value={formatTelefone(telefone)}
                onChange={(e) => setTelefone(e.target.value)}
                maxLength="15"
                required
              />
              {/* Campo Email */}
              <input
                type="email"
                placeholder="Email"
                className="w-full p-3 mb-4 border border-gray-300 rounded-lg"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />

              {/* Container flexível para Senha e Confirmar Senha */}
              <div className="flex flex-col md:flex-row gap-4 mb-4">
                {/* Campo Senha */}
                <input
                  type="password"
                  placeholder="Senha"
                  className="w-full md:w-1/2 p-3 border border-gray-300 rounded-lg"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  required
                />
                {/* Campo Confirmar Senha */}
                <input
                  type="password"
                  placeholder="Confirme a senha"
                  className="w-full md:w-1/2 p-3 border border-gray-300 rounded-lg"
                  value={confirmarSenha}
                  onChange={(e) => setConfirmarSenha(e.target.value)}
                  required
                />
              </div>

              {sucesso && (
                <p className="text-green-600 text-sm mb-4">{sucesso}</p>
              )}
              {erro && <p className="text-red-600 text-sm mb-4">{erro}</p>}
              <button
                type="submit"
                className="w-full bg-blue-600 text-white p-3 rounded-lg hover:bg-blue-700 transition duration-200"
              >
                Cadastrar
              </button>
            </form>

            <p className="text-sm text-center mt-4">
              Já tem conta?{" "}
              <Link to="/" className="text-blue-600 underline">
                Entrar
              </Link>
            </p>
          </div>
        </div>
      </div>
      <Footer />
    </div>
  );
}

export default RegisterPage;
