# Nomenclatura Institucional do SIGESC

> **Status:** norma viva de produto e documentação.  
> **Vigência:** agosto de 2026.  
> **Decisão canônica:** o SIGESC usa **Estudante / Estudantes** como linguagem institucional.

## 1. Modelo conceitual

```text
PESSOA → ESTUDANTE → MATRÍCULA
identidade  contexto       vínculo temporal
civil       educacional    com escola/turma/ano
```

- **Pessoa** representa a identidade civil.
- **Estudante** representa essa pessoa no contexto educacional do SIGESC.
- **Matrícula** representa o vínculo temporal do estudante com escola, turma e ano letivo.

Estudante e matrícula não são sinônimos.

## 2. Termo institucional

Em toda linguagem apresentada pelo SIGESC, usar:

| Evitar | Usar |
|---|---|
| Aluno | **Estudante** |
| Aluna | **Estudante** |
| Aluno(a) | **Estudante** |
| Alunos | **Estudantes** |
| Alunas | **Estudantes** |
| Alunos(as) | **Estudantes** |
| Novo(a) Aluno(a) | **Novo Estudante** |
| Nome do Aluno | **Nome do Estudante** |
| Portal do Aluno | **Portal do Estudante** |
| Total de Alunos | **Total de Estudantes** |
| Alunos Ativos | **Estudantes Ativos** |
| Aluno não encontrado | **Estudante não encontrado** |

Não usar **Estudante(a)** ou **Estudantes(as)**. A palavra *estudante* é comum aos dois gêneros.

## 3. Onde a regra é obrigatória

A nomenclatura canônica vale para:

- menus, cards, títulos, labels, botões, mensagens e ajuda da interface;
- tutoriais e Central de Tutoriais;
- PDFs, declarações, boletins, históricos, fichas e relatórios;
- mensagens humanas do backend/API;
- descrições OpenAPI destinadas a pessoas;
- documentação técnica viva em `README.md` e `docs/**`;
- textos de auditoria e integridade apresentados a usuários técnicos.

## 4. O que permanece técnico/legado

A iniciativa de nomenclatura **não** é uma migração estrutural. Permanecem válidos:

- collection `students`;
- `student`, `students`, `student_id`, `student_series`, classes/DTOs `Student*`;
- campos legados `aluno_*` quando fizerem parte de contrato/dado existente;
- valor técnico de papel `role = "aluno"`;
- comparações de autorização que dependem de `aluno`;
- rota legada `/aluno`;
- nomes de componentes/arquivos como `AlunoDashboard`, `BoletimAluno` e `AlunoTab`;
- slugs publicados como `cadastro-aluno` e `documentos-aluno`;
- a string histórica `"Aluno dependência"` em listas de variantes **proibidas**, quando sua finalidade é detectar e rejeitar nomenclatura legada.

O rótulo exibido ao usuário para o papel técnico `aluno` é **Estudante**.

## 5. Nomes oficiais externos

Quando um órgão, programa, contrato ou integração externa possuir nome oficial que contenha a palavra "Aluno", preservar o nome formal. A exceção deve ser contextual e não autoriza reutilizar o termo como nomenclatura própria do SIGESC.

## 6. Evidência histórica

Não reescrever retroativamente artefatos que registram estados passados, incluindo:

- `memory/audit/**`;
- entradas pretéritas de `memory/CHANGELOG.md`;
- homologações e relatórios históricos;
- `test_reports/**`;
- snapshots, CSVs e JSONs de evidência.

A documentação viva deve refletir a nomenclatura atual; a evidência histórica deve preservar fidelidade temporal.

## 7. Guard automático do CI

O CI executa `.github/scripts/nomenclature_guard.py`.

O guard possui duas camadas:

1. **Documentação viva:** verifica integralmente `README.md` e `docs/**/*.md`.
2. **Código de produto:** verifica somente linhas **adicionadas** no diff de `frontend/src` e das áreas de backend que podem produzir linguagem visível.

A abordagem por diff evita transformar legado técnico já existente em bloqueio retroativo, mas impede que novas mensagens visíveis reintroduzam "Aluno/Alunos".

### Exceções automáticas

O guard reconhece contextos técnicos deliberados, como:

- `role="aluno"` e comparações equivalentes;
- `/aluno`;
- `cadastro-aluno` e `documentos-aluno`;
- identificadores que contêm `aluno_`;
- `"Aluno dependência"` no validador de variantes proibidas;
- testes, snapshots e evidências históricas fora do escopo de produto.

### Waiver explícito

Para uma exceção legítima não coberta pelas regras automáticas, a mesma linha deve conter:

```text
nomenclature-allow
```

Exemplo em código:

```python
EXTERNAL_LABEL = "Programa Oficial do Aluno"  # nomenclature-allow: nome oficial externo
```

Exemplo em Markdown:

```markdown
Programa Oficial do Aluno <!-- nomenclature-allow: denominação oficial externa -->
```

O waiver deve explicar o motivo. Não usar waiver para contornar a regra institucional.

## 8. Critério para revisão de PR

Antes do merge, confirmar:

- texto próprio do SIGESC usa **Estudante / Estudantes**;
- não foi criado `Estudante(a)`;
- papel técnico continua `aluno` quando a alteração for apenas terminológica;
- rotas, IDs, collections e payloads não foram renomeados sem uma decisão arquitetural separada;
- nomes externos preservados possuem justificativa/waiver quando necessário;
- `Nomenclature - Estudante guard` está verde no CI.

## 9. Origem da decisão

Esta norma consolida a auditoria de nomenclatura de 15/08/2026 e as fases de saneamento:

- N1 — UI + Tutoriais;
- N2 — PDFs e documentos institucionais;
- N3 — mensagens e respostas do Backend/API;
- N4 — documentação viva + prevenção automática.

> No SIGESC, **Estudante** é a linguagem institucional. O legado técnico pode permanecer estável quando sua alteração não trouxer benefício e criar risco de compatibilidade.
