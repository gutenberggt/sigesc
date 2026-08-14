# Matriz Canônica de Interoperabilidade do Estudante — SIGESC × SGP/CMDE

Data-base: 2026-08-13  
Status: **planejamento vinculante para implementação em branch; nenhum envio real ao MEC**

## 1. Objetivo

Definir uma única semântica canônica para os dados do estudante no SIGESC antes de ampliar o cadastro e antes de implementar o provider oficial do MEC Gestão Presente/CMDE. A matriz distingue:

1. dado já existente e diretamente compatível;
2. dado existente que deve ser derivado por regra;
3. dado ausente que exige novo campo;
4. dado cuja modelagem atual é semanticamente inadequada e precisa ser corrigida;
5. dado exibido no SGP cuja codificação oficial ainda deve ser confirmada no contrato CMDE antes do envio.

A tela do SGP usada como referência contém Informações pessoais, Matrícula, Endereço, Responsáveis legais, Ficha médica e Informações adicionais. O contrato público atual do CMDE v2 deve ser a fonte final para códigos e payloads de integração.

## 2. Princípios de arquitetura

- O **SIGESC é a fonte da verdade operacional da rede**; o mapper CMDE apenas traduz o dado canônico, sem inventar valores.
- Nenhum campo desconhecido será preenchido com valor fictício, zero, string vazia ou default sem semântica comprovada.
- Dados derivados precisam ter regra determinística e testável.
- Campos da matrícula pertencem à entidade `Enrollment`, não ao cadastro permanente do estudante.
- Dados de saúde devem ficar fora do objeto genérico do estudante, com controle de acesso e auditoria próprios.
- O campo legado `has_disability` não pode ser enviado diretamente como “estudante com deficiência”.
- Dados legados serão preservados; correções semânticas usarão migração/backfill auditável.
- Códigos oficiais (sexo, raça/cor, nacionalidade, deficiência, localização etc.) serão resolvidos no provider/mapper, não gravados como acoplamento ao MEC na entidade de domínio.

## 3. Matriz canônica

Legenda: **OK** = existe; **DERIVAR** = calcular; **NOVO** = novo campo/modelo; **REMODELAR** = corrigir semântica; **CONTRATO** = aguardar/confirmar domínio oficial CMDE.

| Campo exibido no SGP | Escopo canônico | SIGESC atual | Status | Decisão canônica |
|---|---|---|---|---|
| Nome completo | Student | `full_name` | OK | manter |
| Nome social | Student | inexistente | NOVO | `social_name: Optional[str]` |
| Data de nascimento | Student | `birth_date` | OK | manter |
| CPF | Student | `cpf` | OK | manter |
| RG | Student | `rg` | OK | manter; não presumir exigência CMDE sem contrato |
| E-mail do estudante | Student | `email` | OK | manter |
| Celular do estudante | Student | `phone` | OK | manter |
| NIS | Student | `nis` | OK | manter |
| Raça/Cor | Student | `color_race` | REMODELAR | limitar raça/cor ao domínio próprio; remover categorias de comunidade tradicional deste campo e preservar legado por migração |
| Sexo | Student | apenas masculino/feminino | NOVO | adicionar valor canônico `prefere_nao_informar`; distinguir de `null`/não preenchido |
| Nacionalidade | Student | `nationality` texto | OK/CONTRATO | manter domínio interno; mapper converte ao código CMDE oficial |
| Estado de nascimento | Student | `birth_state` | OK | manter |
| Município de nascimento | Student | `birth_city` | OK | manter; eventual código oficial deve ser resolvido pelo mapper |
| Estudante com deficiência | Derivado | `has_disability` é amplo | REMODELAR | nunca mapear diretamente; derivar apenas das condições oficiais após tabela CMDE confirmada |
| Autodeclaração quilombola | Student | `comunidade_tradicional` | DERIVAR | `quilombola = comunidade_tradicional == 'quilombola'` |
| Escola da matrícula | Enrollment/School | `school_id` | OK | usar escola da matrícula vigente |
| Etapa de ensino | Enrollment/Class | turma/série | DERIVAR | derivar de `education_level`, `grade_level`/`student_series` |
| Situação da matrícula | Enrollment | `status` | OK/CONTRATO | tabela de conversão explícita SIGESC → CMDE |
| Matrícula do estudante na rede | Enrollment | `enrollment_number` | OK | manter |
| Data de início da matrícula | Enrollment | `enrollment_date` | OK | manter |
| Data final da matrícula | Enrollment | inexistente canônico | NOVO | `enrollment_end_date: Optional[str]` |
| Data de conclusão EM/EJA | Enrollment | inexistente específico | NOVO | `high_school_eja_completion_date: Optional[str]` |
| ID da matrícula | Enrollment | `id` | OK | ID interno permanece interno; guardar ID SGP separadamente quando provider oficial existir |
| Ano de referência | Enrollment | `academic_year` | OK | manter |
| Necessidade de apoio pedagógico | Enrollment | inexistente equivalente | NOVO | `needs_pedagogical_support: Optional[bool]`; `None` = não informado |
| Matrícula integral | Enrollment/Class | `shift`, programa | DERIVAR/CONTRATO | não criar checkbox redundante; confirmar regra oficial antes do mapper |
| Participação em reforço escolar | Program enrollment | vínculo/programa | DERIVAR | derivar da existência de vínculo ativo de reforço; não depender apenas do campo visual corrente |
| CEP | StudentAddress | inexistente no Student | NOVO | `address.zip_code` |
| Estado de residência | StudentAddress | inexistente | NOVO | `address.state` + `address.state_ibge_code` |
| Município de residência | StudentAddress | inexistente | NOVO | `address.city` + `address.city_ibge_code` |
| Bairro | StudentAddress | inexistente | NOVO | `address.neighborhood` |
| Logradouro | StudentAddress | inexistente | NOVO | `address.street` |
| Número | StudentAddress | inexistente | NOVO | `address.number` |
| Complemento | StudentAddress | inexistente | NOVO | `address.complement` |
| Localização geográfica | StudentAddress | inexistente | NOVO/CONTRATO | campo canônico próprio; domínio somente após confirmar tabela oficial |
| Localização diferenciada | StudentAddress | inexistente | NOVO/CONTRATO | campo canônico próprio; domínio somente após confirmar tabela oficial |
| Responsável legal principal | Guardian link | existe responsável, mas pode haver `both` | REMODELAR | vínculo deve eleger exatamente um `is_primary_legal_guardian` |
| Nome do responsável | Guardian | `guardian_name`/cadastro de responsáveis | OK | preferir entidade Guardian como SSoT |
| Vínculo com estudante | Guardian link | `guardian_relationship` | OK/CONTRATO | manter texto/domínio interno; mapear para código oficial |
| CPF do responsável | Guardian | `guardian_cpf` | OK | manter |
| E-mail do responsável | Guardian | `guardian_email` | OK | manter |
| Celular do responsável | Guardian | `guardian_phone` | OK | manter |
| Celular 2 do responsável | Guardian | não existe no fluxo do estudante | NOVO | usar `cell_phone`/segundo contato canônico da entidade Guardian, sem duplicar no Student |
| Tipo sanguíneo | StudentHealthProfile | inexistente | NOVO SENSÍVEL | coleção/perfil de saúde separado |
| Alergias | StudentHealthProfile | inexistente | NOVO SENSÍVEL | coleção/perfil de saúde separado |
| Comorbidades | StudentHealthProfile | inexistente | NOVO SENSÍVEL | coleção/perfil de saúde separado |
| Medicação de uso contínuo | StudentHealthProfile | inexistente | NOVO SENSÍVEL | coleção/perfil de saúde separado |
| Necessidade nutricional individualizada | StudentHealthProfile | inexistente | NOVO SENSÍVEL | booleano tri-state + descrição opcional |
| Observações | Student/Enrollment conforme natureza | `observations` | OK | manter; não usar observação como substituto de campo estruturado |

## 4. Modelos-alvo

### 4.1 StudentAddress

```python
class StudentAddress(BaseModel):
    zip_code: Optional[str] = None
    state: Optional[str] = None
    state_ibge_code: Optional[str] = None
    city: Optional[str] = None
    city_ibge_code: Optional[str] = None
    neighborhood: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    geographic_location: Optional[str] = None
    differentiated_location: Optional[str] = None
```

Nos novos cadastros, **CEP, Município, UF e códigos IBGE de UF/município são pré-preenchidos a partir da Unidade Mantenedora**. Esses valores formam apenas uma cópia inicial: permanecem editáveis no cadastro do estudante e não existe sincronização automática posterior. Os demais componentes do endereço pertencem exclusivamente ao estudante.

Os códigos IBGE de UF e município serão armazenados de forma explícita para evitar inferências por texto livre na integração. A Unidade Mantenedora passa a manter `codigo_ibge_uf` e `codigo_ibge_municipio`, usados como defaults territoriais do novo estudante.

### 4.2 StudentHealthProfile

**Fase C1:** implementação em coleção própria `student_health_profiles`, com acesso restrito, auditoria de leitura/escrita sem conteúdo clínico e exclusão de listagens/exports genéricos.

Dados de saúde não entram no `StudentBase` genérico nem nas listagens comuns.

```python
class StudentHealthProfile(BaseModel):
    student_id: str
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    comorbidities: Optional[str] = None
    continuous_medication: Optional[str] = None
    individualized_nutritional_need: Optional[bool] = None
    nutritional_need_details: Optional[str] = None
```

Requisitos antes de ativar: RBAC específico, trilha de auditoria, minimização de exposição, exclusão de exports genéricos e revisão LGPD.

### 4.3 Enrollment

Adicionar sem quebrar registros existentes:

```python
enrollment_end_date: Optional[str] = None
high_school_eja_completion_date: Optional[str] = None
needs_pedagogical_support: Optional[bool] = None
sgp_enrollment_id: Optional[str] = None
```

O `sgp_enrollment_id` é identificador externo e jamais substitui `Enrollment.id`.

### 4.4 Student

Adicionar:

```python
social_name: Optional[str] = None
address: Optional[StudentAddress] = None
sgp_student_id: Optional[str] = None
```

Ampliar `sex` com `prefere_nao_informar`, preservando `None` para dado ausente.

## 5. Correções semânticas obrigatórias

### 5.1 Raça/cor × comunidade tradicional

**Implementação de contenção:** novos cadastros deixam de oferecer `quilombola`, `cigano`, `ribeirinho` e `extrativista` como opções de raça/cor. Registros legados continuam legíveis e são sinalizados para revisão. O endpoint administrativo somente leitura `/students/race-community-audit` mede os registros afetados e conflitos antes de qualquer migração. Nenhuma correção automática de raça/cor é permitida, pois comunidade tradicional não permite inferir raça/cor.

`color_race` não deve guardar quilombola, cigano, ribeirinho ou extrativista como raça/cor. Esses valores pertencem a dimensões próprias. Antes de estreitar o enum, executar auditoria dos registros legados e migrá-los sem perda de informação.

### 5.2 Deficiência/AEE

`has_disability` hoje funciona como indicador amplo de condição educacional e não representa semanticamente o campo SGP “estudante com deficiência”. O mapper deve trabalhar com a lista canônica de condições e uma tabela oficial CMDE. TDAH, dislexia e demais transtornos de aprendizagem jamais podem transformar-se em deficiência por inferência.

### 5.3 Responsável principal

A opção corrente de “ambos” é válida para a operação escolar, mas a interoperabilidade exige a identificação inequívoca de um responsável principal quando o contrato assim solicitar. A solução deve ficar no vínculo estudante-responsável, não em duplicação de dados pessoais dentro do Student.

## 6. LGPD e segurança

Raça/origem étnica e dados de saúde são dados pessoais sensíveis. O tratamento de crianças e adolescentes deve observar o melhor interesse. Para o compartilhamento com o MEC Gestão Presente, a base jurídica oficial declarada pelo próprio MEC é execução de política pública e uso compartilhado de dados pela Administração Pública. Isso não elimina a obrigação do SIGESC de aplicar minimização, controle de acesso, finalidade, auditoria e segurança.

Dados médicos terão implementação separada do cadastro geral e não serão enviados ao MEC por simples existência no SIGESC; somente campos efetivamente previstos no contrato oficial poderão entrar no payload.

## 7. Sequência de implementação

### Fase A — alinhamento não sensível

1. Nome social.
2. Opção de sexo “Prefere não informar”.
3. `StudentAddress` e formulário de endereço, com códigos IBGE de UF/município.
4. Responsável principal e segundo contato na entidade Guardian.
5. Novos campos de matrícula: fim, conclusão EM/EJA e apoio pedagógico.
6. Auditoria e correção de `color_race` × `comunidade_tradicional`.
7. Testes de compatibilidade com registros antigos.

### Fase B — camada de interoperabilidade

1. DTO canônico de estudante/matrícula para o MIG.
2. Tabelas explícitas de conversão SIGESC → CMDE.
3. Mapper sem defaults fictícios.
4. Validador de prontidão por tipo de lote.
5. Armazenamento separado dos IDs externos SGP.
6. Dry-run/preview antes de qualquer provider real.

### Fase C — dados sensíveis de saúde

1. Modelo/coleção `student_health_profiles`.
2. RBAC e auditoria.
3. UI em seção própria.
4. Testes de não exposição em listagens/exports.
5. Mapeamento CMDE apenas para campos oficialmente previstos.

## 8. Critérios de aceite

- Nenhum registro antigo é perdido ou reinterpretado silenciosamente.
- `null`/não informado permanece distinto de “não”.
- O mapper não inventa dados.
- TDAH isolado não gera deficiência/AEE no payload.
- Comunidade tradicional não é raça/cor.
- Códigos IBGE de UF/município não são inferidos por aproximação textual no momento do envio.
- Dados de saúde não aparecem na API/listagem genérica de estudantes.
- IDs externos não substituem IDs do domínio SIGESC.
- Toda regra de derivação possui teste unitário.
- Nenhum envio real ao MEC é habilitado por esta etapa.

## 9. Fontes de referência

- Captura/PDF do cadastro do estudante no MEC Gestão Presente, fornecido em 13/08/2026.
- MEC — Gestão Presente na Escola: https://www.gov.br/mec/pt-br/mec-gestao-presente/gestao-presente-na-escola
- Termos de Uso e Aviso de Privacidade do MEC Gestão Presente: https://gpe.gestaopresente.mec.gov.br/termos-de-servico
- API pública CMDEB v2 / Swagger: https://api-cmde2.gestaopresente.mec.gov.br/docs
- Lei nº 13.709/2018 — LGPD.

## 10. Decisão

Esta matriz passa a ser o contrato interno para a evolução do cadastro do estudante e para o futuro mapper oficial do MIG/CMDE. Divergências descobertas no contrato oficial devem atualizar primeiro esta matriz, depois o código.