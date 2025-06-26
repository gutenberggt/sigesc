import React, { useState } from 'react';
import { sendPasswordResetEmail } from 'firebase/auth';
import { auth } from '../firebase/config';
import { Link } from 'react-router-dom';

function RecuperarSenhaPage() {
  const [email, setEmail] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [erro, setErro] = useState('');

  const handleRecuperar = async (e) => {
    e.preventDefault();
    setMensagem('');
    setErro('');
    try {
      await sendPasswordResetEmail(auth, email);
      setMensagem('E-mail de recuperação enviado com sucesso.');
    } catch (error) {
      console.error(error);
      setErro('Não foi possível enviar o e-mail. Verifique o endereço informado.');
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
          <h2 className="text-2xl font-bold mb-6 text-center text-gray-800">Recuperar Senha</h2>

          <form onSubmit={handleRecuperar}>
            <input
              type="email"
              placeholder="Digite seu e-mail"
              className="w-full p-3 mb-4 border border-gray-300 rounded-lg"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            {mensagem && <p className="text-green-600 text-sm mb-4">{mensagem}</p>}
            {erro && <p className="text-red-600 text-sm mb-4">{erro}</p>}
            <button
              type="submit"
              className="w-full bg-blue-600 text-white p-3 rounded-lg hover:bg-blue-700 transition duration-200"
            >
              Enviar Link de Recuperação
            </button>
          </form>

          <p className="text-sm text-center mt-4">
            <Link to="/" className="text-blue-600 underline">
              Voltar ao login
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default RecuperarSenhaPage;
