import React from 'react';
import DeployButton from '../components/DeployButton';
import { auth } from '../firebase/config';

function DashboardPage() {
  const user = auth.currentUser;

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="bg-white shadow rounded p-6 max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold mb-4">
          Bem-vindo{user?.displayName ? `, ${user.displayName}` : ''}!
        </h1>
        <p className="mb-6">Este é o painel inicial do sistema SIGESC.</p>

        {/* Botão de deploy visível apenas para administradores futuramente */}
        <DeployButton />
      </div>
    </div>
  );
}

export default DashboardPage;
