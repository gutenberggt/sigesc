import React, { useState } from 'react';
import { createUserWithEmailAndPassword } from 'firebase/auth';
import { auth, db } from '../firebase/config';
import { doc, setDoc } from 'firebase/firestore';
import { Link } from 'react-router-dom';

function RegisterPage() {
  const [nome, setNome] = useState('');
  const [telefone, setTelefone] = useState('');
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [sucesso, setSucesso] = useState('');

  const handleCadastro = async (e) => {
    e.preventDefault();
    setErro('');
    setSucesso('');
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, senha);
      const user = userCredential.user;

      await setDoc(doc(db, 'users', user.uid), {
        nome,
        telefone,
        email,
        ativo: false,
        perfil: 'aluno',
      });

      setSucesso('Cadastro realizado com sucesso! Aguarde a ativação do seu acesso.');
    } catch (error) {
      console.error(error);
      setErro('Erro ao realizar cadastro. Verifique os dados.');
    }
  };

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-white">
      <div className="md:w-1/2 hidden md:flex flex-col justify-center items-center p-6 relative">
        <div className="absolute top-4 left-4">
          <div className="flex items-center gap-2">
            <img src="/sigesc_log.png" alt="SIGESC Logotipo" className="h-10" />
            <span className="text-2xl font-bold text-gray-800">SIGESC</span>
          </div>
          <p className="text-sm text-gray-600 mt-1">
            Sistema Integrado de Gestão Escolar
          </p>
        </div>
        <img
          src="/login-ilustracao.png"
          alt="Ilustração"
          className="w-4/5 max-w-md mt-10"
        />
      </div>

      <div className="w-full md:w-1/2 flex justify-center items-center px-6 py-12">
        <div className="bg-white shadow-lg rounded-xl p-8 w-full max-w-md">
          <div className="text-center mb-6 mt-4">
            <img src="/brasao_floresta.png" alt="Brasão" className="mx-auto h-16 mb-2" />
            <p className="text-base font-semibold text-gray-800">
              Prefeitura Municipal de Floresta do Araguaia
            </p>
            <p className="text-sm text-gray-700">Secretaria Municipal de Educação</p>
          </div>
          <h2 className="text-2xl font-bold mb-6 text-center text-gray-800">Crie sua conta</h2>

          <form onSubmit={handleCadastro}>
            <input
              type="text"
              placeholder="Nome completo"
              className="w-full p-3 mb-4 border border-gray-300 rounded-lg"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              required
            />
            <input
              type="tel"
              placeholder="Telefone"
              className="w-full p-3 mb-4 border border-gray-300 rounded-lg"
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              required
            />
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
            {sucesso && <p className="text-green-600 text-sm mb-4">{sucesso}</p>}
            {erro && <p className="text-red-600 text-sm mb-4">{erro}</p>}
            <button
              type="submit"
              className="w-full bg-blue-600 text-white p-3 rounded-lg hover:bg-blue-700 transition duration-200"
            >
              Cadastrar
            </button>
          </form>

          <p className="text-sm text-center mt-4">
            Já tem conta? <Link to="/" className="text-blue-600 underline">Entrar</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default RegisterPage;
