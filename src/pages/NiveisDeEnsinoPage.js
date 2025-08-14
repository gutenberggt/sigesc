import React from 'react';

// ========================= INÍCIO DA CORREÇÃO =========================
// 1. A lista de níveis de ensino foi removida daqui.
// 2. Agora, importamos a lista do nosso arquivo central de constantes.
import { niveisDeEnsinoList } from '../data/ensinoConstants';
// ========================== FIM DA CORREÇÃO ===========================

// O componente de visualização agora usa a lista importada para renderizar os dados.
// Nenhuma outra alteração é necessária no componente em si.
function NiveisDeEnsinoPage() {
    return (
        <div className="p-6 bg-white rounded-lg shadow-md">
            <h2 className="text-2xl font-bold mb-4 text-gray-800">Níveis de Ensino Cadastrados</h2>
            <p className="mb-6 text-gray-600">Esta é uma lista de referência dos níveis de ensino utilizados no sistema.</p>
            <ul className="list-disc list-inside space-y-2">
                {niveisDeEnsinoList.map(nivel => (
                    <li key={nivel} className="text-gray-700">{nivel}</li>
                ))}
            </ul>
        </div>
    );
}

export default NiveisDeEnsinoPage;