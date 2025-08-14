document.addEventListener("DOMContentLoaded", () => {
  const app = document.getElementById("app");

  // Cabeçalho
  const header = document.createElement("div");
  header.innerHTML = `
    <h2>Prefeitura Municipal de Floresta do Araguaia</h2>
    <h3>Secretaria Municipal de Educação</h3>
    <h4>E M E F MONSENHOR AUGUSTO DIAS DE BRITO</h4>
    <p><b>Turma:</b> 4ª ETAPA UNICA 2025 &nbsp; <b>Período:</b> De 17/02/2025 a 18/04/2025</p>
    <p><b>Disciplina:</b> Língua Portuguesa &nbsp; <b>Professor:</b> ELENI NERES MENEZES</p>
  `;
  app.appendChild(header);

  // Estilos
  const style = document.createElement("style");
  style.textContent = `
    table { border-collapse: collapse; font-family: Arial, sans-serif; font-size: 12px; }
    th, td { border: 1px solid #000; padding: 2px 4px; text-align: center; white-space: nowrap; }
    th:nth-child(2), td:nth-child(2) { text-align: left; }
    thead th { background: #ddd; }
    tbody tr:nth-child(even) { background: #f9f9f9; }
    .legenda { margin-top: 10px; font-size: 12px; }
    .scroll { overflow-x: auto; max-width: 100%; }
  `;
  document.head.appendChild(style);

  // Cabeçalho das datas
  const colunasDatas = [
    "4","5","6","3","4","5","6","4","5","6","3","4","5","6",
    "5","6","4","5","6","3","4","5","6","4","5","6","3","4","5","6",
    "4","5","6","3","4","5","6"
  ];
  const colunasDia = [
    17,17,17,18,18,21,21,24,24,24,25,25,28,28,
    3,4,5,7,7,10,10,10,11,11,14,14,17,17,17,18,
    18,21,21,24,24,24,25,25,28,28
  ];
  const colunasMes = [
    2,2,2,2,2,2,2,2,2,2,2,2,2,2,
    3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,
    3,3,3,3,3,3,3,3
  ];

  // Todos os 26 alunos da primeira página
  const alunos = [
    [1, "ADRIANA MENDES PEREIRA", [".",".",".",".",".",".",".",".",".",".",".","F","F","F",".",".",".",".","E","E","E",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".","."], 3, "95%"],
    [2, "ADRIENE DA SILVA FEITOSA", [".",".",".",".","F","F",".",".","F","F",".",".","E","E","E",".","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 25, "23%"],
    [3, "ALESSANDRA ALVES NOLETO DOS SANTOS", ["F","F","F","F","F","F","F","F","F","F","F","F",".",".","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 35, "21%"],
    [4, "AMANDA ROSA DA SILVA", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "0%"],
    [5, "ANA CLARA RIBEIRO SOUSA", [".",".",".",".",".",".",".",".",".",".","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 27, "43%"],
    [6, "ANA VITORIA SOUZA COSTA", ["F","F","F",".",".","F","F",".",".",".","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 32, "10%"],
    [7, "ANELITA DAS NEVES AGUIAR", ["F","F","F","F","F","F","F",".",".",".",".",".","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 32, "25%"],
    [8, "BENEDITA SOUZA DA SILVA", ["F","F","F",".",".","F","F",".",".",".",".",".",".",".","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 28, "28%"],
    [9, "BRENDO TRAGINO DA SILVA", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "4%"],
    [10, "BRENO ARAUJO GOMES SANTOS", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "0%"],
    [11, "CARLOS DANIEL NEVES DE SOUSA", ["N","N","N","N","N","N","N","N","N","N","N","N","N","N","E","E","E","N","N","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 21, "0%"],
    [12, "CAROLINE JHENNIFIR DA SILVA NASCIMENTO", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "0%"],
    [13, "DAVYD COSTA DOS SANTOS", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "0%"],
    [14, "DIANE ALVES RODRIGUES", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "0%"],
    [15, "EFRAIM BARROS DA SILVA", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "0%"],
    [16, "ELCILENE VITORIA DA SILVA RODRIGUES", [".",".",".","F","F","F","F","F","F","F","F","F","F","F","E","E","E",".",".","F","F","F",".",".","F","F",".",".",".",".",".",".",".",".",".",".",".","."], 16, "49%"],
    [17, "ELIÉZER DA SILVA NUNES", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "4%"],
    [18, "EVA PEREIRA DE SOUSA", [".",".",".",".",".",".",".",".",".",".","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 27, "23%"],
    [19, "FERNANDA FERREIRA RIOS", ["E","E","E"], 0, "100%"],
    [20, "JASILENE PEREIRA DE OLIVEIRA", [".",".",".",".",".",".","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 30, "17%"],
    [21, "JESIEL SANTOS DE FREITAS", [".",".",".",".",".",".","F","F","F",".",".",".",".","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 26, "41%"],
    [22, "JESSICA CAVALCANTE DOS SANTOS", ["N","N","N","N","N","N","N","N","N","N","N","N","N","N","E","E","E","N","N","N","N","N","N","N","N","N","N","N","N","N","N","N","N","N","N","N","N","N"], 0, "100%"],
    [23, "JOANICE ALMEIDA DA CONCEIÇÃO RIBEIRO", [".",".",".",".",".",".",".",".",".",".",".",".",".",".","E","E","E",".",".",".",".","F","F",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".","."], 2, "97%"],
    [24, "JOAO VITOR DA CRUZ PASLANDIN", [".",".",".",".","F","F",".",".","F","F",".",".","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 27, "45%"],
    [25, "JOSE ALVES DE SOUSA", ["F","F","F",".",".",".",".",".",".",".",".",".",".",".","E","E","E",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".",".","."], 3, "95%"],
    [26, "JOSE LUCIO DA SILVA", ["F","F","F","F","F","F","F","F","F","F","F","F","F","F","E","E","E","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F","F"], 37, "0%"],
  ];

  const wrapper = document.createElement("div");
  wrapper.classList.add("scroll");

  const table = document.createElement("table");

  // Linha 1: Aula
  const thead = document.createElement("thead");
  const tr1 = document.createElement("tr");
  tr1.innerHTML = `<th rowspan="3">Nº</th><th rowspan="3">Nome do aluno</th>` +
                  colunasDatas.map(d => `<th>${d}</th>`).join('') +
                  `<th rowspan="3">Faltas</th><th rowspan="3">Freq.</th>`;
  thead.appendChild(tr1);

  // Linha 2: Dia
  const tr2 = document.createElement("tr");
  colunasDia.forEach(d => {
    const th = document.createElement("th");
    th.textContent = d;
    tr2.appendChild(th);
  });
  thead.appendChild(tr2);

  // Linha 3: Mês
  const tr3 = document.createElement("tr");
  colunasMes.forEach(m => {
    const th = document.createElement("th");
    th.textContent = m;
    tr3.appendChild(th);
  });
  thead.appendChild(tr3);

  table.appendChild(thead);

  // Corpo
  const tbody = document.createElement("tbody");
  alunos.forEach(al => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${al[0]}</td><td>${al[1]}</td>` +
                   al[2].map(m => `<td>${m}</td>`).join('') +
                   `<td>${al[3]}</td><td>${al[4]}</td>`;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  wrapper.appendChild(table);
  app.appendChild(wrapper);

  // Legenda
  const legenda = document.createElement("div");
  legenda.className = "legenda";
  legenda.innerHTML = `
    <p>Legenda: N - Não enturmado, D - Dispensado da disciplina, FJ - Falta justificada, E - Feriado - Carnaval, E - Feriado - Quarta-feira de Cinzas</p>
  `;
  app.appendChild(legenda);
});
