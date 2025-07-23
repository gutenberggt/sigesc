import React from 'react';

// Dados dos componentes curriculares
const componentesCurricularesData = {
  "Educação Infantil - 0 a 5 Anos": [
    { nome: "Carga Horaria: 160" }
  ],
  "Educação Infantil": [
    { nome: "O eu, o outro e o nós", sigla: "EON", cargaHoraria: 120, isCampoDeExperiencia: true },
    { nome: "Corpo, gestos e movimentos", sigla: "CGM", cargaHoraria: 120, isCampoDeExperiencia: true },
    { nome: "Traços, sons, cores e formas", sigla: "TSCF", cargaHoraria: 160, isCampoDeExperiencia: true },
    { nome: "Escuta, fala, pensamento e imaginação", sigla: "EFPI", cargaHoraria: 160, isCampoDeExperiencia: true },
    { nome: "Espaços, tempos, quantidades, relações e transformações", sigla: "ETQRT", cargaHoraria: 160, isCampoDeExperiencia: true },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", isTemaTransversal: true },
    { nome: "Tecnologia", sigla: "TEC", isTemaTransversal: true }
  ],
  "Ensino Fundamental - Anos Iniciais - 1º ao 5º Ano": [
    { nome: "Carga Horaria: 160" }
  ],
  "1º ao 5º Ano": [
    { nome: "Língua Portuguesa", sigla: "POR", cargaHoraria: 160 },
    { nome: "Arte", sigla: "ART", cargaHoraria: 40 },
    { nome: "Educação Física", sigla: "FIS", cargaHoraria: 80 },
    { nome: "Matemática", sigla: "MAT", cargaHoraria: 160 },
    { nome: "Ciências", sigla: "CIE", cargaHoraria: 80 },
    { nome: "História", sigla: "HIS", cargaHoraria: 80 },
    { nome: "Geografia", sigla: "GEO", cargaHoraria: 80 },
    { nome: "Ensino Religioso", sigla: "REL", cargaHoraria: 40 },
    { nome: "Recreação, Esporte e Lazer", sigla: "REL", cargaHoraria: 80 },
    { nome: "Arte e Cultura", sigla: "AC", cargaHoraria: 160 },
    { nome: "Tecnologia e Informática", sigla: "TI", cargaHoraria: 40 },
    { nome: "Acompanhamento Pedagógico de Língua Portuguesa", sigla: "APLP", cargaHoraria: 160 },
    { nome: "Acompanhamento Pedagógico de Matemática", sigla: "APM", cargaHoraria: 160 },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", cargaHoraria: 80 }
  ],
  "Ensino Fundamental - Anos Finais - 6º ao 9º Ano": [
    { nome: "Carga Horaria: 160" }
  ],
  "6º Ano": [
    { nome: "Língua Portuguesa", sigla: "POR", cargaHoraria: 240 },
    { nome: "Arte", sigla: "ART", cargaHoraria: 80 },
    { nome: "Educação Física", sigla: "FIS", cargaHoraria: 80 },
    { nome: "Língua Inglesa", sigla: "ING", cargaHoraria: 80 },
    { nome: "Matemática", sigla: "MAT", cargaHoraria: 240 },
    { nome: "Ciências", sigla: "CIE", cargaHoraria: 80 },
    { nome: "História", sigla: "HIS", cargaHoraria: 80 },
    { nome: "Geografia", sigla: "GEO", cargaHoraria: 120 },
    { nome: "Ensino Religioso", sigla: "REL", cargaHoraria: 40 },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", cargaHoraria: 80 },
    { nome: "Estudos Amazônicos", sigla: "AMA", cargaHoraria: 80 },
    { nome: "Literatura e Redação", sigla: "RED", cargaHoraria: 80 },
    { nome: "Recreação, Esporte e Lazer", sigla: "REL", cargaHoraria: 80 },
    { nome: "Arte e Cultura", sigla: "AC", cargaHoraria: 160 },
    { nome: "Tecnologia e Informática", sigla: "TI", cargaHoraria: 40 },
    { nome: "Acompanhamento Pedagógico de Língua Portuguesa", sigla: "APLP", cargaHoraria: 160 },
    { nome: "Acompanhamento Pedagógico de Matemática", sigla: "APM", cargaHoraria: 160 }
  ],
  "7º Ano": [
    { nome: "Língua Portuguesa", sigla: "POR", cargaHoraria: 240 },
    { nome: "Arte", sigla: "ART", cargaHoraria: 80 },
    { nome: "Educação Física", sigla: "FIS", cargaHoraria: 80 },
    { nome: "Língua Inglesa", sigla: "ING", cargaHoraria: 80 },
    { nome: "Matemática", sigla: "MAT", cargaHoraria: 240 },
    { nome: "Ciências", sigla: "CIE", cargaHoraria: 120 },
    { nome: "História", sigla: "HIS", cargaHoraria: 80 },
    { nome: "Geografia", sigla: "GEO", cargaHoraria: 80 },
    { nome: "Ensino Religioso", sigla: "REL", cargaHoraria: 40 },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", cargaHoraria: 80 },
    { nome: "Estudos Amazônicos", sigla: "AMA", cargaHoraria: 80 },
    { nome: "Literatura e Redação", sigla: "RED", cargaHoraria: 80 },
    { nome: "Recreação, Esporte e Lazer", sigla: "REL", cargaHoraria: 80 },
    { nome: "Arte e Cultura", sigla: "AC", cargaHoraria: 160 },
    { nome: "Tecnologia e Informática", sigla: "TI", cargaHoraria: 40 },
    { nome: "Acompanhamento Pedagógico de Língua Portuguesa", sigla: "APLP", cargaHoraria: 160 },
    { nome: "Acompanhamento Pedagógico de Matemática", sigla: "APM", cargaHoraria: 160 }
  ],
  "8º Ano": [
    { nome: "Língua Portuguesa", sigla: "POR", cargaHoraria: 240 },
    { nome: "Arte", sigla: "ART", cargaHoraria: 80 },
    { nome: "Educação Física", sigla: "FIS", cargaHoraria: 80 },
    { nome: "Língua Inglesa", sigla: "ING", cargaHoraria: 80 },
    { nome: "Matemática", sigla: "MAT", cargaHoraria: 240 },
    { nome: "Ciências", sigla: "CIE", cargaHoraria: 80 },
    { nome: "História", sigla: "HIS", cargaHoraria: 120 },
    { nome: "Geografia", sigla: "GEO", cargaHoraria: 80 },
    { nome: "Ensino Religioso", sigla: "REL", cargaHoraria: 40 },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", cargaHoraria: 80 },
    { nome: "Estudos Amazônicos", sigla: "AMA", cargaHoraria: 80 },
    { nome: "Literatura e Redação", sigla: "RED", cargaHoraria: 80 },
    { nome: "Recreação, Esporte e Lazer", sigla: "REL", cargaHoraria: 80 },
    { nome: "Arte e Cultura", sigla: "AC", cargaHoraria: 160 },
    { nome: "Tecnologia e Informática", sigla: "TI", cargaHoraria: 40 },
    { nome: "Acompanhamento Pedagógico de Língua Portuguesa", sigla: "APLP", cargaHoraria: 160 },
    { nome: "Acompanhamento Pedagógico de Matemática", sigla: "APM", cargaHoraria: 160 }
  ],
  "9º Ano": [
    { nome: "Língua Portuguesa", sigla: "POR", cargaHoraria: 240 },
    { nome: "Arte", sigla: "ART", cargaHoraria: 80 },
    { nome: "Educação Física", sigla: "FIS", cargaHoraria: 80 },
    { nome: "Língua Inglesa", sigla: "ING", cargaHoraria: 80 },
    { nome: "Matemática", sigla: "MAT", cargaHoraria: 240 },
    { nome: "Ciências", sigla: "CIE", cargaHoraria: 80 },
    { nome: "História", sigla: "HIS", cargaHoraria: 120 },
    { nome: "Geografia", sigla: "GEO", cargaHoraria: 80 },
    { nome: "Ensino Religioso", sigla: "REL", cargaHoraria: 40 },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", cargaHoraria: 80 },
    { nome: "Estudos Amazônicos", sigla: "AMA", cargaHoraria: 80 },
    { nome: "Literatura e Redação", sigla: "RED", cargaHoraria: 80 },
    { nome: "Recreação, Esporte e Lazer", sigla: "REL", cargaHoraria: 80 },
    { nome: "Arte e Cultura", sigla: "AC", cargaHoraria: 160 },
    { nome: "Tecnologia e Informática", sigla: "TI", cargaHoraria: 40 },
    { nome: "Acompanhamento Pedagógico de Língua Portuguesa", sigla: "APLP", cargaHoraria: 160 },
    { nome: "Acompanhamento Pedagógico de Matemática", sigla: "APM", cargaHoraria: 160 }
  ],
  "Educação de Jovens e adultos - EJA - Anos Iniciais": [
    { nome: "Carga Horaria: 160" }
  ],
  "1ª e 2ª Etapa": [
    { nome: "Língua Portuguesa", sigla: "POR", cargaHoraria: 160 },
    { nome: "Arte", sigla: "ART", cargaHoraria: 40 },
    { nome: "Educação Física", sigla: "FIS", cargaHoraria: 80 },
    { nome: "Matemática", sigla: "MAT", cargaHoraria: 160 },
    { nome: "Ciências", sigla: "CIE", cargaHoraria: 80 },
    { nome: "História", sigla: "HIS", cargaHoraria: 80 },
    { nome: "Geografia", sigla: "GEO", cargaHoraria: 80 },
    { nome: "Ensino Religioso", sigla: "REL", cargaHoraria: 40 },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", cargaHoraria: 80 }
  ],
  "Educação de Jovens e adultos - EJA - Anos Finais": [
    { nome: "Carga Horaria: 160" }
  ],
  "3ª e 4ª Etapa": [
    { nome: "Língua Portuguesa", sigla: "POR", cargaHoraria: 280 },
    { nome: "Arte", sigla: "ART", cargaHoraria: 80 },
    { nome: "Educação Física", sigla: "FIS", cargaHoraria: 80 },
    { nome: "Língua Inglesa", sigla: "ING", cargaHoraria: 80 },
    { nome: "Matemática", sigla: "MAT", cargaHoraria: 280 },
    { nome: "Ciências", sigla: "CIE", cargaHoraria: 120 },
    { nome: "História", sigla: "HIS", cargaHoraria: 80 },
    { nome: "Geografia", sigla: "GEO", cargaHoraria: 80 },
    { nome: "Ensino Religioso", sigla: "REL", cargaHoraria: 40 },
    { nome: "Educação Ambiental e Clima", sigla: "EAC", cargaHoraria: 80 }
  ]
};

function ComponentesCurricularesPage() {
  return (
    <div className="flex-grow p-6 bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">Componentes Curriculares</h2>

        <p className="text-gray-700 mb-6 text-center">
          Lista de componentes curriculares por série/etapa, incluindo a sigla e a carga horária.
        </p>

        {Object.keys(componentesCurricularesData).map((serieAnoEtapa) => (
          <div key={serieAnoEtapa} className="mb-8 p-4 border border-gray-200 rounded-lg shadow-sm bg-gray-50">
            {/* Título da Seção (ex: "1º ao 5º Ano", "Educação Infantil - Campos de Experiência") */}
            <h3 className="text-xl font-semibold text-blue-700 mb-4 border-b pb-2">{serieAnoEtapa}</h3>
            
            {/* Grid para os Componentes/Campos de Experiência */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-gray-800">
              {componentesCurricularesData[serieAnoEtapa].map((componente, index) => (
                <div key={index} className="bg-white p-3 rounded-md shadow-sm border border-gray-100">
                  <p className="font-semibold">{componente.nome}</p>
                  {/* Renderiza Sigla e Carga Horária, "Tema Transversal" ou "Campo de Experiência" */}
                  {componente.isTemaTransversal ? (
                    <p className="text-sm text-gray-600 italic">Tema Transversal</p>
                  ) : componente.isCampoDeExperiencia ? (
                    <p className="text-sm text-blue-600 italic">Campo de Experiência</p> 
                  ) : null /* Adicionado para evitar erro caso não seja nenhum dos dois */ }
                  
                  {/* Sempre exibe Sigla e Carga Horária se existirem */}
                  {componente.sigla && componente.cargaHoraria !== undefined && (
                    <>
                      <p className="text-sm text-gray-600">Sigla: {componente.sigla}</p>
                      <p className="text-sm text-gray-600">Carga Horária: {componente.cargaHoraria}h</p>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ComponentesCurricularesPage;