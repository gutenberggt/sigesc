import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { auth } from '../firebase/config';
import { signInWithEmailAndPassword, signOut } from 'firebase/auth';
import { doc, getDoc } from 'firebase/firestore';
import { db } from '../firebase/config';

function LoginPage() {
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setErro('');
    try {
      const userCredential = await signInWithEmailAndPassword(auth, email, senha);
      const user = userCredential.user;

      // Consulta no Firestore para verificar se está ativo
      const userDocRef = doc(db, "users", user.uid);
      const userDocSnap = await getDoc(userDocRef);

      if (userDocSnap.exists()) {
        const userData = userDocSnap.data();

        if (userData.ativo) {
          // Usuário ativo: redireciona
          window.location.href = "/dashboard";
        } else {
          // Usuário inativo: desloga e avisa
          await signOut(auth);
          setErro("Seu cadastro ainda está aguardando ativação pelo responsável.");
        }
      } else {
        // Documento não existe, erro
        await signOut(auth);
        setErro("Usuário não encontrado no sistema.");
      }
    } catch (error) {
      console.error(error);
      setErro("Email ou senha inválidos.");
    }
  };

  // ... resto do código permanece igual

  return (
    <div className="flex justify-center items-center h-screen bg-gray-100">
      <form onSubmit={handleLogin} className="bg-white p-8 rounded shadow-md w-full max-w-sm">
        <h2 className="text-2xl font-bold mb-6 text-center">Login SIGESC</h2>
        <input
          type="email"
          placeholder="Email"
          className="w-full p-2 mb-4 border rounded"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Senha"
          className="w-full p-2 mb-4 border rounded"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
        />
        {erro && <p className="text-red-600 text-sm mb-4">{erro}</p>}
        <button
          type="submit"
          className="w-full bg-blue-600 text-white p-2 rounded hover:bg-blue-700"
        >
          Entrar
        </button>

        <p className="text-sm text-center mt-4">
          Ainda não tem conta? <Link to="/cadastro" className="text-blue-600 underline">Cadastre-se</Link>
        </p>
		<p className="text-sm text-center mt-2">
		  <a href="/recuperar-senha" className="text-blue-600 underline">Esqueceu sua senha?</a>
		</p>
      </form>
    </div>
  );
}

export default LoginPage;
