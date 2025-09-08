// src/pages/WelcomePage.js
import React from "react";

function WelcomePage() {
  return (
    <div className="flex-grow container mx-auto p-6 text-center">
      <h2 className="text-2xl font-bold text-gray-800 mb-4">
        Bem-vindo ao SIGESC
      </h2>
      <p className="text-gray-700 text-lg">Você está logado com sucesso!</p>
      <p className="text-gray-500 text-sm mt-2">
        Este painel será personalizado de acordo com seu perfil de acesso.
      </p>
    </div>
  );
}

export default WelcomePage;
