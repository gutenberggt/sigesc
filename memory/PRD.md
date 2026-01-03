# SIGESC - Sistema de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Secretaria Municipal de Educação, com funcionalidades de:
- Cadastro de escolas, turmas, alunos, professores
- Registro de notas e frequência
- Geração de documentos (boletins, fichas individuais, certificados, declarações)
- Controle de ano letivo
- Gestão de lotações de servidores

## Implementações Recentes

### 2026-01-03
- **Ordenação de Componentes Curriculares**: Implementada ordenação personalizada para Anos Iniciais e Anos Finais
  - Anos Iniciais: Língua Portuguesa → Arte → Educação Física → Matemática → Ciências → História → Geografia → Ensino Religioso → Componentes de escola integral
  - Anos Finais: Língua Portuguesa → Arte → Educação Física → Língua Inglesa → Matemática → Ciências → História → Geografia → Ensino Religioso → Educação Ambiental e Clima → Estudos Amazônicos → Literatura e Redação → Componentes de escola integral

- **Condicionais para Aprovação (Mantenedora)**: Novos campos no cadastro da mantenedora:
  - Média para aprovação (5,0 a 10,0)
  - Aprovação com dependência (checkbox + qtd máxima de componentes 1-5)
  - Cursar apenas dependência (checkbox + qtd de componentes 1-5)

- **Lógica de Resultado Final**: Implementada função `calcular_resultado_final_aluno()` que considera:
  - Média mínima configurável pela mantenedora
  - Aprovação com dependência (se permitido e dentro do limite)
  - Cursar apenas dependência (quando reprovações excedem o limite)
  - Status especiais (transferido, desistente, falecido)
  - Resultados possíveis: APROVADO, REPROVADO, APROVADO COM DEPENDÊNCIA, CURSAR DEPENDÊNCIA, EM ANDAMENTO

### Anteriores
- Gerenciamento de Anos Letivos (aberto/fechado)
- Geração de Certificado de Conclusão (9º Ano e EJA)
- Campo de Brasão na Mantenedora
- Campo de Autorização/Reconhecimento na Escola
- Importação em massa de alunos via Excel

## Backlog Priorizado

### P0 (Crítico)
- [ ] Investigar bug de componentes ausentes no Boletim (logs de debug adicionados)

### P1 (Alto)
- [ ] Verificar bug de "Gerenciar Lotações" não salvando

### P2 (Médio)
- [ ] Limpar dados órfãos de lotações

### P3 (Baixo)
- [ ] Refatorar StudentsComplete.js
- [ ] Refatorar Calendar.js
- [ ] Refatorar pdf_generator.py
- [ ] Deletar arquivo obsoleto Courses.js

## Arquitetura

### Backend
- FastAPI + Motor (MongoDB async)
- Arquivos principais: server.py, models.py, pdf_generator.py, grade_calculator.py

### Frontend
- React + Vite + TailwindCSS + Shadcn/UI
- Contextos: AuthContext, MantenedoraContext

### Banco de Dados
- MongoDB
- Coleções: users, schools, classes, students, courses, grades, attendance, mantenedora, etc.

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: ricleidegoncalves@gmail.com / 007724
