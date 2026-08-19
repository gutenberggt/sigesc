# SIGESC — Especificação: Urgências / Ficha Individual Manual

Data: 2026-08-19
Branch: `feat/urgencias-ficha-individual`
Status: APROVADA PARA IMPLEMENTAÇÃO

## 1. Objetivo

Criar uma área de **Urgências** no Dashboard do SIGESC para ferramentas excepcionais de gestão escolar. O primeiro recurso será **Ficha Individual**, permitindo gerar uma ficha fiel ao documento oficial existente, porém com notas/conceitos, resultado e data de emissão informados manualmente.

A ferramenta é exclusivamente documental. **Não é uma alternativa ao Diário, ao módulo de Notas, à Frequência ou à Movimentação de matrícula.**

## 2. Navegação

Dashboard → Gestão Escolar → **Urgências** → **Ficha Individual**.

Rotas previstas:

- `/admin/urgencias`
- `/admin/urgencias/ficha-individual`

A Página de Urgências deve ser expansível para receber novas ferramentas futuramente.

## 3. Perfis inicialmente permitidos

- super_admin
- admin / admin_teste quando aplicável
- secretário
- diretor
- auxiliar_secretaria

O escopo de escola deve ser validado também no backend; não basta filtrar no frontend.

## 4. Seleção da Ficha Individual

Ordem obrigatória dos campos:

1. Escola
2. Turma
3. Ano/Série/Etapa
4. Estudante
5. Resultado
6. Data de emissão

Dependências:

- alterar Escola limpa Turma, Série, Estudante e tabela;
- alterar Turma limpa Série, Estudante e tabela;
- alterar Série limpa Estudante e tabela;
- alterar Estudante recarrega dados documentais e currículo.

O ano letivo deve vir da turma selecionada.

## 5. Turmas multisseriadas

Em turma regular, Ano/Série/Etapa é derivado da turma e fica somente leitura.

Em turma multisseriada, Ano/Série/Etapa é obrigatório e deve utilizar as séries permitidas pela própria turma. A matrícula/enrollment é a referência acadêmica e `student_series` deve prevalecer sobre `class_info.grade_level`, como já ocorre na Ficha Individual oficial.

## 6. Dados preenchidos automaticamente

Após selecionar o estudante, reutilizar as fontes oficiais do SIGESC para:

- mantenedora e identidade visual;
- escola;
- ano letivo;
- nome do estudante;
- sexo;
- INEP;
- nascimento;
- turma;
- turno;
- ano/série/etapa;
- carga horária;
- dias letivos;
- frequência/faltas, conforme regra documental vigente;
- componentes curriculares ou campos de experiência.

## 7. Currículo

É **proibido** criar lista hardcoded de disciplinas/campos.

A Ficha Individual Manual deve usar o mesmo `resolve_curriculum` evidence-first da ficha/boletim oficiais e hidratar os mesmos metadados dos cursos.

Deve respeitar:

- Educação Infantil;
- Ensino Fundamental — Anos Iniciais;
- Ensino Fundamental — Anos Finais;
- EJA;
- atendimento integral;
- turma multisseriada;
- componentes formativos;
- optativos;
- futuras alterações curriculares.

## 8. Avaliação conceitual

Quando a etapa usar conceito, reproduzir a estrutura oficial:

- Componente/Campo
- C.H.
- 1º Bim.
- 2º Bim.
- 3º Bim.
- 4º Bim.
- Conceito Final
- Faltas
- % Freq.

O usuário informa apenas os conceitos bimestrais. O conceito final é derivado pelas regras canônicas já existentes.

## 9. Avaliação numérica

Reproduzir exatamente a estrutura oficial:

- Componente
- C.H.
- 1º semestre: B1, B2, REC
- 2º semestre: B3, B4, REC
- Processo ponderado: B1×2, B2×3, B3×2, B4×3
- Total de pontos
- Média anual
- Faltas
- % frequência

Editáveis apenas: `b1`, `b2`, `rec_s1`, `b3`, `b4`, `rec_s2`.

O processo ponderado, total e média devem seguir o `grade_calculator.py`; não reimplementar regra acadêmica em JavaScript.

## 10. Resultado manual

O resultado é selecionado manualmente e prevalece no PDF emergencial.

Usar domínio canônico compatível com a etapa, incluindo quando cabível:

- CURSANDO
- EM ANDAMENTO
- PROMOVIDO(A)
- CONCLUIU A ETAPA
- APROVADO
- APROVADO COM DEPENDÊNCIA
- EM DEPENDÊNCIA
- REPROVADO
- REPROVADO POR FREQUÊNCIA
- TRANSFERIDO
- DESISTENTE
- FALECIDO

Pode ser exibida advertência não bloqueante quando o resultado manual divergir do cálculo do SIGESC.

## 11. Data de emissão

Campo manual obrigatório, inicialmente preenchido com a data atual.

## 12. PDF — fonte única

**Não criar um segundo template visual.**

Reutilizar `backend/pdf/ficha_individual.py` e ampliar `generate_ficha_individual_pdf()` de forma retrocompatível com overrides opcionais:

```python
resultado_override=None
data_emissao_override=None
```

Quando ambos forem `None`, a Ficha Individual oficial deve continuar exatamente como hoje.

A Ficha de Urgência usa o mesmo gerador, fornecendo grades/conceitos manuais em memória e os overrides de resultado/data.

## 13. Endpoint

Criar endpoint específico, preferencialmente:

`POST /api/documents/ficha-individual-manual`

Responsabilidades:

1. autenticar e autorizar usuário;
2. validar escopo de escola;
3. validar escola/turma/matrícula/série/estudante;
4. resolver currículo oficial;
5. rejeitar `course_id` fora do currículo;
6. validar nota/conceito/data/resultado;
7. construir grades em memória;
8. obter os demais dados oficiais somente por leitura;
9. gerar PDF usando o mesmo gerador oficial;
10. registrar apenas a auditoria documental da emissão.

## 14. Trava de segurança acadêmica

A geração manual **NÃO PODE escrever** em:

- `grades`
- `attendance`
- `students`
- `enrollments`
- `student_history`

Notas, conceitos e resultado fornecidos nesta página existem apenas no contexto da emissão documental.

## 15. Auditoria documental

Registrar emissão em coleção própria, por exemplo `manual_document_issuances`, com:

- id
- document_type = ficha_individual
- student_id
- school_id
- class_id
- academic_year
- student_series
- resultado
- data_emissao
- manual_grades_snapshot
- issued_by
- issued_by_name
- issued_at
- pdf_sha256
- source = urgencias

Esse registro é rastreabilidade documental e não histórico acadêmico.

## 16. Critérios mínimos de homologação

1. botão Urgências aparece na seção Gestão Escolar para perfis autorizados;
2. página `/admin/urgencias` é expansível;
3. fluxo Escola → Turma → Série → Estudante funciona;
4. multisseriada usa `student_series` corretamente;
5. currículo é o mesmo da ficha oficial;
6. Educação Infantil e anos conceituais usam estrutura conceitual vigente;
7. avaliação numérica usa tabela ponderada oficial;
8. recuperações seguem `grade_calculator.py`;
9. resultado manual aparece exatamente no PDF;
10. data manual aparece no rodapé;
11. usuário fora do escopo recebe 403;
12. `course_id` fora do currículo é rejeitado;
13. nenhuma escrita ocorre em grades/frequência/aluno/matrícula/histórico;
14. a ficha oficial atual permanece funcional e visualmente inalterada;
15. emissão manual fica registrada em auditoria;
16. para o mesmo estudante e os mesmos valores, ficha oficial e manual têm o mesmo cabeçalho, currículo, ordenação, tabela, cálculos, rodapé e assinaturas.

## 17. Definição de pronto

A funcionalidade só será considerada homologada quando a **Ficha Individual de Urgência for a própria Ficha Individual oficial do SIGESC alimentada excepcionalmente por dados manuais**, e não uma segunda versão independente do documento.
