# CTUE_PRINCIPIOS_ARQUITETURAIS.md — Princípios Arquiteturais do CTUE
### A "Constituição" do Cadastro Técnico da Unidade Escolar · Referência permanente

> **Status:** documento normativo permanente (Jun/2026). Toda evolução futura do cadastro de
> escolas DEVE consultar e respeitar este documento — para impedir que o cadastro volte a
> crescer de forma desorganizada. Complementa `ARCHITECTURE_BASELINE.md` (§3.1, §3.2, §3.9).

---

## 1. Objetivos do CTUE
1. Representar **completa e fielmente** a realidade **física, administrativa e patrimonial** de
   cada unidade escolar.
2. Ser a **Fonte Única da Verdade (SSoT)** de toda informação institucional da escola.
3. Servir de **origem única** para relatórios, indicadores, painéis, diagnósticos, dossiês e
   respostas a órgãos de controle (MP, TCM/TCE, FNDE, Câmara, CME) e subsídios ao PME.
4. Ser **estável no tempo** (dado de patrimônio muda pouco), separando-se do que é dinâmico.

## 2. Responsabilidades
O CTUE **é responsável por**: identificação, localização/georreferência, gestão/vinculação
administrativa, infraestrutura física, ambientes pedagógicos, acessibilidade, água/saneamento/
energia, segurança, conectividade, equipamentos/patrimônio, conservação, obras, documentação
legal e observações técnicas.

O CTUE **NÃO é responsável por** (pertence à Gestão Pedagógica/Operacional): matrículas,
turmas, servidores, horários, calendário, notas/frequência, diário, permissões de lançamento
e indicadores **pedagógicos**.

## 3. Limites do módulo
- O CTUE **armazena** o estado institucional; **não calcula** indicadores nem gera regras de
  negócio pedagógicas.
- O CTUE **não duplica** dados de outros módulos: referencia por `school_id`.
- O CTUE **não é** um repositório de documentos operacionais (esses seguem em seus módulos);
  guarda apenas metadados de conformidade institucional (alvará, AVCB, licenças) e anexos correlatos.

## 4. Relacionamento com os demais módulos
- **Turmas/Matrículas/Servidores:** consomem `school_id`; nunca copiam atributos físicos do CTUE.
- **Painel Gerencial da Rede / Dossiê Institucional:** **somente leitura** do CTUE.
- **Motor de Indicadores (BI):** quando ativo, é o **único** produtor de indicadores; o painel
  passa a consumir dele. O CTUE fornece os **dados de entrada**, não os indicadores.
- **Transferência Institucional / Documentos verificáveis:** reutilizam a identidade da escola
  do CTUE; nada é reimplementado.

## 5. Princípios SSoT (inegociáveis)
1. **Uma informação, uma origem.** Cada dado institucional existe em **um único campo** de `schools`.
2. **Sem módulos paralelos.** Proibido criar novo módulo/coleção que rearmazene dados já do CTUE.
3. **Consumidores não recalculam nem copiam.** Painéis, dossiês, IA e relatórios apenas leem.
4. **Indicador ≠ dado.** Indicadores são derivados e pertencem ao Motor de Indicadores (§3.9 baseline).
5. **Derivação em vez de duplicação.** Quando dois campos representam o mesmo fato, um é canônico
   e o outro é **derivado/deprecado** (ver redundâncias R1–R6).

## 6. Governança dos dados
- **Propriedade:** o dado do CTUE pertence à mantenedora (multi-tenant, RLS fail-closed).
- **Qualidade:** campos com indicador de completude por seção; "Não informado" explícito (nunca
  branco silencioso) para forçar atualização.
- **Auditabilidade:** alterações relevantes registram autor/quando; migrações seguem §3.2
  (auditoria + dry-run + rollback), padrão `with_critical_mutation`.
- **Acessibilidade e linguagem:** rótulos em linguagem de gestão, não jargão interno.
- **Retrocompatibilidade:** leitura tolerante a valores legados (`field_validator`); nada é
  removido sem aprovação e sem backfill do canônico.

## 7. Política de evolução do cadastro
1. **Consolidar antes de expandir** (baseline §3.1). Antes de propor campo novo, verificar se o
   dado já existe (mesmo que oculto na UI).
2. **Aditivo e retrocompatível.** Todo campo novo é `Optional`; nenhum campo existente é alterado
   sem plano de migração + rollback.
3. **UX primeiro, modelo depois.** Exposição/relatório têm prioridade sobre ampliação de schema.
4. **Sem inchaço de UI.** Novos campos entram na seção correta do CTUE, com divulgação progressiva.
5. **Deprecar com disciplina.** Campo redundante é marcado deprecado, congelado para escrita e
   removido só após período de observação + aprovação.

## 8. Critérios para inclusão de novos campos (gate obrigatório)
Um campo só é aceito se responder **SIM** a pelo menos uma das perguntas objetivas:
- É **exigido** por MP, TCM/TCE, FNDE, INEP/Educacenso ou Bombeiros?
- É **necessário** para um relatório/dossiê institucional ou para uma decisão de gestão concreta?
- Substitui/consolida um dado hoje disperso (reduz redundância)?

E deve trazer, **obrigatoriamente**, a ficha:
```
Campo:            <nome>            Classe: [Obrigatório | Recomendado | Opcional]
Finalidade:       <necessidade objetiva de gestão/controle>
Exigência (órgão):<MP/TCM/FNDE/INEP/Bombeiros/—>
Impacto backend:  <modelo/endpoint/migração>
Impacto frontend: <seção CTUE/validação>
Impacto relatórios:<painel/dossiê/quadro-resumo>
Retrocompatibilidade: <plano>
```
**Rejeição automática:** "pode ser útil", "por precaução", "para o futuro" — sem necessidade
objetiva **não entra**. O crescimento do cadastro é **dirigido por demanda comprovada**.

## 9. Classes de campo (definição)
- **Obrigatório:** ausência impede resposta a órgão de controle ou fere norma. Bloqueia
  conformidade no dossiê.
- **Recomendado:** eleva a qualidade do dossiê/painel; ausência é sinalizada mas não bloqueia.
- **Opcional:** enriquece o cadastro; sem impacto de conformidade.

## 10. Regra de ouro
> **Se o Secretário Municipal abrir o CTUE pela primeira vez e não souber, em segundos, onde
> está cada informação — a organização está errada e deve ser corrigida antes de adicionar
> qualquer campo.** Clareza e origem única acima de completude.

*Documento de referência permanente. Última atualização: Jun/2026 — Sprint Proposta CTUE.*
