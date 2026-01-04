# SIGESC - Sistema de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Secretaria Municipal de Educação, com funcionalidades de:
- Cadastro de escolas, turmas, alunos, professores
- Registro de notas e frequência
- Geração de documentos (boletins, fichas individuais, certificados, declarações)
- Controle de ano letivo
- Gestão de lotações de servidores

## Implementações Recentes

### 2026-01-04
- **Correção Visual do Calendário Anual**:
  - Cores uniformizadas: dias letivos e sábados letivos com mesma cor verde (bg-green-100)
  - Removida legenda duplicada, mantida apenas a legenda original de tipos de eventos
  - Feriados em vermelho claro, recesso em azul claro, fim de semana em cinza

- **Bloqueio por Data Limite de Edição** (P1 - IMPLEMENTADO):
  - Nova função `check_bimestre_edit_deadline()` verifica data limite por bimestre
  - Nova função `verify_bimestre_edit_deadline_or_raise()` bloqueia edições após prazo
  - Verificação aplicada em: `/api/grades/batch`, `/api/attendance`, `/api/learning-objects`
  - Admin e secretário podem editar mesmo após data limite
  - Novo endpoint `/api/calendario-letivo/{ano}/status-edicao` retorna status de cada bimestre

### 2026-01-03
- **Ordenação de Componentes Curriculares**: Implementada ordenação personalizada para Anos Iniciais e Anos Finais

- **Condicionais para Aprovação (Mantenedora)**:
  - Média para aprovação (5,0 a 10,0)
  - Frequência mínima para aprovação (60% a 85%, padrão LDB: 75%)
  - Aprovação com dependência (checkbox + qtd máxima de componentes 1-5)
  - Cursar apenas dependência (checkbox + qtd de componentes 1-5)

- **Lógica de Resultado Final**: Função `calcular_resultado_final_aluno()` considera:
  - Média mínima, Frequência mínima, Aprovação com dependência, Cursar dependência
  - Resultados: APROVADO, REPROVADO, REPROVADO POR FREQUÊNCIA, APROVADO COM DEPENDÊNCIA, CURSAR DEPENDÊNCIA

- **Dias Letivos por Bimestre no Calendário Letivo**:
  - Campo de dias letivos em cada bimestre (1º, 2º, 3º, 4º)
  - Soma automática do total anual de dias letivos
  - Exibição visual com badges coloridas para cada bimestre
  - Total de dias letivos anuais exibido na mesma linha do título

- **Cálculo de Frequência no Boletim**:
  - Busca os dias letivos do calendário letivo
  - Calcula frequência: (dias_letivos - faltas) / dias_letivos * 100
  - Usa a frequência calculada na verificação de reprovação

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
- [x] ~~Implementar bloqueio por data limite de edição~~ (CONCLUÍDO 2026-01-04)
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
- Coleções: users, schools, classes, students, courses, grades, attendance, mantenedora, calendario_letivo, etc.

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: ricleidegoncalves@gmail.com / 007724
