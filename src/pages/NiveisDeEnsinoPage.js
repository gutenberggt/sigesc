
import React from 'react';

// NOVO: Lista de níveis de ensino exportada
export const niveisDeEnsinoList = [
  "EDUCAÇÃO INFANTIL",
  "ENSINO FUNDAMENTAL - ANOS INICIAIS",
  "ENSINO FUNDAMENTAL - ANOS FINAIS",
  "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS INICIAIS",
  "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS FINAIS",
  "FORMAÇÃO COMPLEMENTAR",
  "ATENDIMENTO EDUCACIONAL ESPECIALIZADO - AEE"
];

function NiveisDeEnsinoPage() {
  return (
    <div className="flex-grow p-6 bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">Níveis de Ensino</h2>
        
        <p className="text-gray-700 mb-4">Abaixo estão os níveis de ensino ofertados:</p>

        <ul className="list-disc list-inside space-y-2 text-gray-700">
          {niveisDeEnsinoList.map((nivel, index) => ( // Usando a lista exportada
            <li key={index}>{nivel}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default NiveisDeEnsinoPage;
