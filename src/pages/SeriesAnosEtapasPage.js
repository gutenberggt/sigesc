import React from 'react';

// ========================= INÍCIO DA CORREÇÃO =========================
// 1. O objeto 'seriesAnosEtapasData' foi removido daqui.
// 2. Agora, importamos o objeto do nosso arquivo central de constantes.
import { seriesAnosEtapasData } from '../data/ensinoConstants';
// ========================== FIM DA CORREÇÃO ===========================

// O componente de visualização agora usa o objeto importado para renderizar os dados.
function SeriesAnosEtapasPage() {
    return (
        <div className="p-6 bg-white rounded-lg shadow-md">
            <h2 className="text-2xl font-bold mb-4 text-gray-800">Séries, Anos e Etapas por Nível de Ensino</h2>
            <p className="mb-6 text-gray-600">Esta é uma lista de referência das séries, anos e etapas disponíveis para cada nível de ensino.</p>
            {Object.keys(seriesAnosEtapasData).map(nivel => (
                <div key={nivel} className="mb-6 pb-4 border-b last:border-b-0">
                    <h3 className="text-xl font-semibold text-gray-700 mb-2">{nivel}</h3>
                    <ul className="list-disc list-inside ml-4 space-y-1">
                        {seriesAnosEtapasData[nivel].map(serie => (
                            <li key={serie} className="text-gray-600">{serie}</li>
                        ))}
                    </ul>
                </div>
            ))}
        </div>
    );
}

export default SeriesAnosEtapasPage;