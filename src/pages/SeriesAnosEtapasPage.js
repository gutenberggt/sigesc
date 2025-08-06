
import React from 'react';

// NOVO: Estrutura de séries/anos/etapas exportada
export const seriesAnosEtapasData = {
 "EDUCAÇÃO INFANTIL": [
    "BERÇÁRIO I",
    "BERÇÁRIO II",
    "MATERNAL I",
    "MATERNAL II",
    "PRÉ I",
    "PRÉ II"
  ],
  "ENSINO FUNDAMENTAL - ANOS INICIAIS": [
    "1º ANO",
    "2º ANO",
    "3º ANO",
    "4º ANO",
    "5º ANO"
  ],
  "ENSINO FUNDAMENTAL - ANOS FINAIS": [
    "6º ANO",
    "7º ANO",
    "8º ANO",
    "9º ANO"
  ],
  "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS INICIAIS": [
    "1ª ETAPA",
    "2ª ETAPA"
  ],
  "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS FINAIS": [
    "3ª ETAPA",
    "4ª ETAPA"
  ],
  "FORMAÇÃO COMPLEMENTAR": [
    "NÃO SERIADA"
],
  "ATENDIMENTO EDUCACIONAL ESPECIALIZADO - AEE": [
    "NÃO SERIADA"	


  ]
};

function SeriesAnosEtapasPage() {
  return (
    <div className="flex-grow p-6 bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">Séries / Anos / Etapas</h2>
        
        <div className="space-y-6 text-gray-700">
          {Object.keys(seriesAnosEtapasData).map((nivel) => (
            <div key={nivel}>
              <h3 className="text-xl font-semibold mb-2">{nivel}:</h3>
              <ul className="list-disc list-inside space-y-1">
                {seriesAnosEtapasData[nivel].map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SeriesAnosEtapasPage;
