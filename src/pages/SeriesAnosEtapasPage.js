import React from 'react';

// NOVO: Estrutura de séries/anos/etapas exportada
export const seriesAnosEtapasData = {
  "Educação Infantil": [
    "Berçário I",
    "Berçário II",
    "Maternal I",
    "Maternal II",
    "Pré I",
    "Pré II"
  ],
  "Ensino Fundamental - Anos Iniciais": [
    "1º Ano",
    "2º Ano",
    "3º Ano",
    "4º Ano",
    "5º Ano"
  ],
  "Ensino Fundamental - Anos Finais": [
    "6º Ano",
    "7º Ano",
    "8º Ano",
    "9º Ano"
  ],
  "Educação de Jovens e Adultos - EJA": [
    "1ª Etapa",
    "2ª Etapa",
    "3ª Etapa",
    "4ª Etapa"
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