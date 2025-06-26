import React from 'react';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase/config';

function DashboardPage() {
  const handleLogout = async () => {
    await signOut(auth);
    window.location.href = "/";
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-blue-600 text-white p-4 shadow">
        <div className="container mx-auto flex justify-between items-center">
          <div className="flex items-center gap-3">
            <img src="/sigesc_log.png" alt="Logo SIGESC" className="h-8" />
            <h1 className="text-xl font-semibold">SIGESC - Painel</h1>
          </div>
          <button
            onClick={handleLogout}
            className="bg-white text-blue-600 px-4 py-2 rounded hover:bg-gray-100 transition"
          >
            Sair
          </button>
        </div>
      </header>

      {/* Conteúdo principal */}
      <main className="flex-grow container mx-auto p-6 text-center">
        <h2 className="text-2xl font-bold text-gray-800 mb-4">Bem-vindo ao SIGESC</h2>
        <p className="text-gray-700 text-lg">Você está logado com sucesso!</p>
        <p className="text-gray-500 text-sm mt-2">Este painel será personalizado de acordo com seu perfil de acesso.</p>
      </main>
    </div>
  );
}

export default DashboardPage;
