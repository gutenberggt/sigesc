import React, { useState } from 'react';
import { sendPasswordResetEmail } from 'firebase/auth';
import { auth } from '../firebase/config';

function RecuperarSenhaPage() {
  const [email, setEmail] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [erro, setErro] = useState('');

  const handleRecuperarSenha = async (e) => {
    e.preventDefault();
    setMensagem('');
    setErro('');

    try {
      await sendPasswordResetEmail(auth, email);
      setMensagem('Um email de recuperação foi enviado. Verifique sua caixa de entrada.');
    } catch (err) {
      setErro('Erro ao enviar o email. Verifique se o endereço está correto.');
    }
  };

  return (
    <div className="flex justify-center items-center h-screen bg-gray-100">
      <form onSubmit={handleRecuperarSenha} className="bg-white p-8 rounded shadow-md w-full max-w-sm">
        <h2 className="text-2xl font-bold mb-6 text-center">Recuperar Senha</h2>
        <input
          type="email"
          placeholder="Email cadastrado"
          className="w-full p-2 mb-4 border rounded"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        {mensagem && <p className="text-green-600 text-sm mb-4">{mensagem}</p>}
        {erro && <p className="text-red-600 text-sm mb-4">{erro}</p>}
        <button type="submit" className="w-full bg-blue-600 text-white p-2 rounded hover:bg-blue-700">
          Enviar email de recuperação
        </button>
      </form>
    </div>
  );
}

export default RecuperarSenhaPage;
