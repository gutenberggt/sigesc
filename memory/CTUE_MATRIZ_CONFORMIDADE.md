# CTUE_MATRIZ_CONFORMIDADE.md — Matriz de Conformidade do CTUE
### Base normativa única de conformidade da Unidade Escolar (SSoT)

> **Sprint de PROPOSTA · Jun/2026 · READ-ONLY.** Documento para **aprovação prévia**. Nenhuma
> lógica implementada. Complementa `CTUE_ARQUITETURA.md`, `CTUE_ROADMAP.md` e
> `CTUE_PRINCIPIOS_ARQUITETURAIS.md`.
>
> **Papel deste documento:** ser a **fonte única** dos cálculos de completude e conformidade do
> CTUE. **Todos** os consumidores usam exatamente o mesmo resultado:
> `Cadastro → Conformidade → Painel → Dashboard → BI → Dossiê/PDF → API`. A lógica pertence ao
> CTUE; o PDF/painel apenas **representam** o resultado. **Nada duplicado.**

---

## 1. Princípios da matriz
1. **Configurável, não codificada.** As regras vivem em **dados** (coleção `ctue_conformity_rulesets`),
   não no código. No futuro a Secretaria altera regras/pesos sem deploy.
2. **Uma origem de cálculo.** Um único serviço `CTUEConformityService.evaluate(school, ruleset)`
   produz um objeto `ConformityResult`. Painel, índice lateral, indicadores por seção, dashboard
   da rede, BI, dossiê, PDF e API **consomem o mesmo objeto** (SSoT — baseline §3.9).
3. **Duas métricas distintas** (ver §3):
   - **Preenchimento (Completude):** *"quanto do cadastro já foi informado"* — ex.: `4/7 · 57%`.
   - **Conformidade:** *"a escola atende às exigências"* — ex.: `Segurança 66%`, status ✅/⚠/❌.
4. **Escala gradual (Fases).** Seções da Fase D (Obras, Documentação, Obs. Técnicas) ficam
   `inativa_ate_fase="D"` → **não penalizam** a conformidade hoje (excluídas do denominador) e
   passam a contar automaticamente quando os campos existirem. A matriz nasce funcional na Sprint A1.
5. **Segura por construção.** As expressões de regra usam um **DSL restrito** (lista branca de
   campos + operadores), avaliado por um interpretador seguro — **nunca** `eval` de código arbitrário.

---

## 2. Modelo de configuração (schema do ruleset)
Coleção proposta: **`ctue_conformity_rulesets`** (read-mostly, versionada).
- `mantenedora_id = null` → **ruleset global padrão**; um `mantenedora_id` preenchido = override
  local (futuro). O serviço resolve: override da mantenedora → senão global.

```json
{
  "ruleset_id": "ctue-default-v1",
  "mantenedora_id": null,
  "versao": 1,
  "ativo": true,
  "status_global_thresholds": { "conforme": 85, "parcial": 50 },
  "sections": [
    {
      "key": "seguranca",
      "label": "Segurança",
      "peso": 12,
      "inativa_ate_fase": null,
      "campos": [
        { "campo": "qtd_extintores", "classe": "obrigatorio", "peso": 3, "tipo": "int",  "requer_preenchimento": true },
        { "campo": "saidas_emergencia","classe": "recomendado","peso": 2, "tipo": "int",  "requer_preenchimento": true },
        { "campo": "brigada_incendio", "classe": "obrigatorio", "peso": 3, "tipo": "bool", "requer_preenchimento": false },
        { "campo": "plano_evacuacao",  "classe": "obrigatorio", "peso": 3, "tipo": "bool", "requer_preenchimento": false },
        { "campo": "qtd_cameras",      "classe": "opcional",    "peso": 1, "tipo": "int",  "requer_preenchimento": false },
        { "campo": "possui_cercamento","classe": "recomendado", "peso": 2, "tipo": "bool", "requer_preenchimento": false }
      ],
      "regras_conformidade": [
        { "id": "tem_extintor", "label": "Possui extintores",          "peso": 1, "expr": "coalesce(qtd_extintores, extintores, 0) > 0" },
        { "id": "tem_plano",    "label": "Possui plano de evacuação",  "peso": 1, "expr": "plano_evacuacao == true" },
        { "id": "tem_brigada",  "label": "Possui brigada de incêndio", "peso": 1, "expr": "brigada_incendio == true" }
      ],
      "section_thresholds": { "conforme": 100, "parcial": 1 }
    }
  ]
}
```

**Campos do schema**
- `peso` (seção): importância relativa da seção no total (Σ pesos ativos = base do cálculo global).
- `campos[].classe`: `obrigatorio | recomendado | opcional`.
- `campos[].peso`: peso do campo **no preenchimento** da seção (default por classe: Obrig=3, Recom=2, Opc=1; pode ser sobrescrito).
- `campos[].requer_preenchimento`: se `true`, o campo entra no **denominador de completude**
  (typicamente texto/número/enum). Booleanos "possui_X" normalmente `false` aqui (a resposta
  sim/não já é o dado; contam na **conformidade**, não inflam a completude).
- `regras_conformidade[]`: condições booleanas (DSL) que definem **atender**; cada uma com `peso`.
- `section_thresholds`: % para classificar status da seção (✅/⚠/❌).
- `status_global_thresholds`: % para o selo de Conformidade Geral.

**DSL de expressão (lista branca):** nomes de campos de `SchoolBase`; operadores
`== != > >= < <= && || !`; funções `coalesce(...)`, `count_true(...)`, `is_filled(campo)`,
`in(campo, [..])`. Sem acesso a código, rede ou atributos fora da escola.

---

## 3. Fórmulas de cálculo

### 3.1 Por campo
- **Preenchido** (`is_filled`): texto/enum ≠ vazio; número não nulo (e, quando aplicável, `> 0`);
  bool ≠ nulo. Só entra na completude se `requer_preenchimento = true`.
- **Atende** (conformidade): resultado das `regras_conformidade` (não do campo isolado).

### 3.2 Por seção
- **Completude da seção** =
  `Σ(peso_campo · preenchido) / Σ(peso_campo)` sobre campos com `requer_preenchimento=true`.
  → exibida como `n/N itens · XX%`.
- **Conformidade da seção** =
  `Σ(peso_regra · atende) / Σ(peso_regra)` sobre `regras_conformidade`.
  → **Status:** ✅ `conforme` se `% ≥ section_thresholds.conforme` **e** todas as regras de
  campos **obrigatórios** atendidas; ❌ `nao_conforme` se `% < section_thresholds.parcial`
  **ou** alguma regra obrigatória crítica falha; ⚠ `parcial` caso contrário.
- Seção **sem `regras_conformidade`** (ex.: Identificação/Equipamentos): conformidade =
  completude (o "atender" é "estar cadastrado").

### 3.3 Global (topo do CTUE)
Somente seções com `inativa_ate_fase = null` (ativas na fase corrente) entram:
- **Conformidade Geral** = `Σ(peso_seção · conformidade_seção) / Σ(peso_seção)`.
- **Completude Geral** = `Σ(peso_seção · completude_seção) / Σ(peso_seção)`.
- **Selo geral:** ✅ `≥ status_global_thresholds.conforme` · ⚠ `≥ parcial` · ❌ abaixo.

### 3.4 Objeto de saída (`ConformityResult`) — contrato único
```json
{
  "school_id": "…",
  "ruleset_id": "ctue-default-v1",
  "conformidade_geral": 63,
  "completude_geral": 71,
  "selo_geral": "parcial",
  "sections": [
    { "key": "seguranca", "label": "Segurança",
      "completude": 40, "itens_preenchidos": 2, "itens_total": 5,
      "conformidade": 66, "status": "parcial",
      "regras": [
        {"id":"tem_extintor","label":"Possui extintores","atende":true},
        {"id":"tem_plano","label":"Possui plano de evacuação","atende":true},
        {"id":"tem_brigada","label":"Possui brigada de incêndio","atende":false}
      ],
      "pendencias": ["brigada_incendio"] }
  ]
}
```
Este objeto alimenta: **Painel de Conformidade** (topo), **Índice inteligente** (lateral,
✔/⚠/❌ por seção com clique → navega), **Indicador por seção** (`n/N · %`), **Dashboard da rede**,
**BI**, **Dossiê/PDF** (quadro-resumo) e **API**. Um cálculo, muitos consumidores.

---

## 4. Matriz por seção (ruleset padrão `ctue-default-v1`)
Legenda classe: **O**=Obrigatório · **R**=Recomendado · **P**=Opcional. `[D]` = campo Fase D
(entra quando o modelo evoluir). Pesos de seção somam **100** (seções Fase D não pontuam até ativas).

### 1) Identificação — peso 10 · sem regra (conformidade = completude)
| Campo | Classe | Peso | Preench.? |
|---|---|---|---|
| `name` | O | 3 | ✔ |
| `inep_code` | O | 3 | ✔ |
| `cnpj` | R | 2 | ✔ |
| `caracteristica_escolar` | R | 2 | ✔ |
| `situacao_funcionamento` | O | 3 | ✔ |
| `tipo_unidade` / `anexa_a` | R | 2 | ✔ |
| `zona_localizacao` | O | 3 | ✔ |
| `sigla` | P | 1 | ✔ |

### 2) Localização & Georreferência — peso 6 · regra: endereço mínimo + georreferência
| Campo | Classe | Peso | Preench.? |
|---|---|---|---|
| `cep`,`logradouro`,`numero`,`bairro`,`municipio`,`estado` | O | 3 cada | ✔ |
| `latitude`,`longitude` | R | 2 | ✔ |
| `telefone`/`celular`,`email` | R | 2 | ✔ |
| `complemento`,`distrito`,`site`,`ddd_telefone` | P | 1 | ✔ |
- **Regras:** `endereco_completo` (cep&logradouro&numero&bairro&municipio&estado preenchidos) · `georreferenciada` (latitude&longitude).

### 3) Gestão & Vinculação — peso 7 · regra: gestor + vínculo definidos
| Campo | Classe | Peso |
|---|---|---|
| `gestor_principal`,`cargo_gestor` | O | 3 |
| `secretario_escolar` | R | 2 |
| `dependencia_administrativa`,`esfera_administrativa` | O | 3 |
| `orgao_responsavel`,`regulamentacao` | R | 2 |
| `categoria_mantenedora`,`cnpj_mantenedora`,`forma_contratacao_*`,`possui_convenio` | P | 1 |
- **Regras:** `tem_gestor` (`is_filled(gestor_principal)`) · `tem_vinculo` (`is_filled(dependencia_administrativa) && is_filled(esfera_administrativa)`).

### 4) Infraestrutura Física — peso 8 · regra: capacidade e salas informadas
| Campo | Classe | Peso | Preench.? |
|---|---|---|---|
| `numero_salas_aula` | O | 3 | ✔ |
| `capacidade_total_alunos` | O | 3 | ✔ |
| `numero_banheiros` | O | 3 | ✔ |
| `sala_direcao`,`sala_secretaria`,`sala_coordenacao`,`sala_professores` | R | 2 | — |
| `possui_almoxarifado` | P | 1 | — |
| `[D] area_terreno_m2`,`[D] area_construida_m2`,`[D] ano_construcao`,`[D] regime_ocupacao`,`[D] predio_compartilhado` | R/P | — | — |
- **Regras:** `salas_informadas` (`numero_salas_aula>0`) · `capacidade_informada` (`capacidade_total_alunos>0`).

### 5) Ambientes Pedagógicos — peso 7 · regra: núcleo pedagógico mínimo
| Campo | Classe | Peso |
|---|---|---|
| `salas_recursos_multifuncionais` (AEE) | R | 2 |
| `possui_biblioteca` | R | 2 |
| `possui_lab_ciencias`,`possui_lab_informatica` | R | 2 |
| `possui_quadra` (canônico) | R | 2 |
| `possui_cozinha`,`possui_refeitorio` | R | 2 |
| `possui_patio`,`possui_parque`,`possui_brinquedoteca`,`possui_auditorio`,`possui_horta`,`possui_estacionamento` | P | 1 |
- **Regras:** `tem_cozinha_ou_refeitorio` · `tem_espaco_leitura_ou_biblioteca` · `tem_espaco_esportivo` (`possui_quadra`).

### 6) Acessibilidade — peso 12 · regra LBI (rampas + banheiro acessível + tátil)
| Campo | Classe | Peso |
|---|---|---|
| `possui_rampas` | O | 3 |
| `possui_corrimao` | R | 2 |
| `banheiros_acessiveis` (nº, canônico) | O | 3 |
| `sinalizacao_tatil` | R | 2 |
| `[D] vias_acessiveis`,`[D] dependencias_acessiveis` | R | — |
- **Regras (ex. da tela: 4/7 · 57%):** `tem_rampa` · `tem_corrimao` · `tem_banheiro_acessivel` (`banheiros_acessiveis>0 || banheiros_adaptados`) · `tem_sinalizacao_tatil` (+ 3 itens Fase D → total 7).

### 7) Água, Saneamento & Energia — peso 12 · regra: serviços essenciais
| Campo | Classe | Peso |
|---|---|---|
| `abastecimento_agua` | O | 3 |
| `energia_eletrica` | O | 3 |
| `saneamento` (esgotamento) | O | 3 |
| `coleta_lixo` (resíduos) | R | 2 |
| `[D] agua_potavel`,`[D] certificado_potabilidade` | O | — |
| `[D] tipo_esgotamento`,`[D] tipo_destinacao_lixo` | R | — |
- **Regras:** `tem_agua` (`is_filled(abastecimento_agua)`) · `tem_energia` · `tem_esgotamento` (`is_filled(saneamento)`) · `[D] agua_potavel==true`.

### 8) Segurança — peso 12 · regra: extintor + plano + brigada (exemplo do owner)
Ver §2 (ruleset exemplo). Regras: `tem_extintor` · `tem_plano` · `tem_brigada` (+ `[D] avcb`).

### 9) Conectividade — peso 5 · regra: internet ativa
| Campo | Classe | Peso |
|---|---|---|
| `possui_internet` | O | 3 |
| `tipo_conexao` | R | 2 |
| `cobertura_rede` | P | 1 |
- **Regras:** `tem_internet` (`possui_internet==true`).

### 10) Equipamentos & Patrimônio — peso 5 · sem regra (completude)
`qtd_computadores`(R2), `qtd_tablets`,`qtd_projetores`,`qtd_impressoras`,`qtd_televisores`,
`qtd_projetores_multimidia`,`qtd_aparelhos_som`,`qtd_lousas_digitais`(P1), `possui_material_didatico`,
`tamanho_acervo`,`participa_programas_governamentais`(P1), `possui_kits_cientificos`,`possui_instrumentos_musicais`(P1).

### 11) Conservação — peso 6 · regra: estado informado e aceitável
| Campo | Classe | Peso |
|---|---|---|
| `estado_conservacao` | O | 3 |
| `[D] necessita_reforma`,`[D] itens_criticos` | R | — |
- **Regras:** `estado_informado` (`is_filled(estado_conservacao)`) · `sem_reforma_critica` (`!in(estado_conservacao,["ruim","precario"])`).

### 12) Obras — peso 4 · `inativa_ate_fase="D"`
`[D] obras[] (situacao/tipo/valor/fonte_recurso/datas)`. Regra: `obras_regularizadas` (sem obra paralisada). *Não pontua até a Fase D.*

### 13) Documentação — peso 6 · `inativa_ate_fase="D"`
`regulamentacao` (já existe) + `[D] alvara_funcionamento`,`[D] licenca_sanitaria`,`[D] avcb_bombeiros`,`[D] habite_se`.
Regras: `tem_ato_autorizacao` · `[D] tem_alvara` · `[D] tem_avcb` · `[D] tem_licenca_sanitaria`. *Ativa na Fase D.*

### 14) Observações Técnicas — peso 2 · `inativa_ate_fase="D"` · sem regra
`[D] observacoes_tecnicas` (texto). Completude informativa.

> **Soma dos pesos das seções ATIVAS na Sprint A1** (exclui 12,13,14 = 4+6+2=12): base = 88 →
> normalizada para 100% no cálculo global. Ao ativar a Fase D, a base volta a 100 pesos.

---

## 5. Governança da matriz (configurável, versionada)
- **Versionamento:** cada mudança de ruleset gera nova `versao`; o `ConformityResult` carimba
  `ruleset_id`+`versao` (auditável; dossiês antigos permanecem explicáveis).
- **Override por mantenedora:** futuro — Secretaria ajusta pesos/regras sem código (tela de
  administração de rulesets). Fallback sempre para o `default`.
- **Edição segura:** validação do DSL (lista branca de campos/operadores) ao salvar um ruleset.
- **SSoT:** proibido recalcular conformidade fora do `CTUEConformityService`. PDF/painel/BI só leem.

---

## 6. Como cada consumidor usa (um cálculo, muitos usos)
| Consumidor | Usa do `ConformityResult` |
|---|---|
| **Painel de Conformidade (topo do CTUE)** | `conformidade_geral`, `selo_geral`, status por seção |
| **Índice inteligente (lateral)** | `sections[].status` (✔/⚠/❌) + navegação |
| **Indicador por seção** | `sections[].completude` (`n/N · %`) |
| **Dashboard da Rede** | agregação de `conformidade_geral`/seções entre escolas |
| **BI / Motor de Indicadores** | indicadores de conformidade como métricas oficiais |
| **Dossiê Institucional / PDF** | `sections[].regras` → quadro-resumo ✓/✗ |
| **API** | expõe o mesmo objeto para integrações |

---

## 7. REFINAMENTOS APROVADOS PELO OWNER (Jun/2026) — vigentes na Sprint A1

### 7.1 Duas métricas independentes (aprovado)
Completude e Conformidade são **independentes** e aparecem **lado a lado** em todo o sistema.
Uma escola pode ter 100% completude e 60% conformidade (ou o inverso).

### 7.2 Perfis de Avaliação (evolução dos pesos)
Os pesos deixam de ser um único conjunto: passam a existir **perfis**. O **motor é único**; muda
apenas o ruleset/perfil selecionado. Perfis iniciais:
`default`, `mp`, `fnde`, `tcm`, `infraestrutura`, `seguranca`, `educacao_integral`.
Cada perfil define `section_weights` (peso por seção); seções fora do perfil = peso 0 (não contam).
A mesma escola exibe índices diferentes conforme o objetivo da análise.

### 7.3 Quatro estados (substitui 3)
| Estado | Ícone | Faixa padrão (%) |
|---|---|---|
| Conforme | 🟢 | ≥ 85 |
| Atenção | 🟡 | 65–84 |
| Crítico | 🟠 | 40–64 |
| Não Conforme | 🔴 | < 40 |
Aplica-se ao selo geral e por seção (thresholds configuráveis por ruleset).

### 7.4 Fase D — "Ainda não avaliado nesta versão"
Seções/campos inexistentes **NÃO reduzem** a conformidade (excluídos do denominador) e são
exibidos com estado neutro **🔘 "Ainda não avaliado nesta versão"** (nunca 🔴). Evita leitura equivocada.

### 7.5 Terceiro indicador — Atualização
Além de Completude e Conformidade, o CTUE expõe **Atualização** (frescor do cadastro), a partir
de `updated_at`: `Atualizado hoje` · `há N dias` · `há N meses` · `Nunca atualizado`
(`freshness: recent | ok | stale | never`).

### 7.6 Mini-card na listagem de escolas (a lista vira painel-resumo da rede)
Cada escola na lista exibe, sem abrir o cadastro: **Nome · Gestor · Situação (Ativa/Inativa) ·
Completude % · Conformidade % · Última atualização · Status visual (🟢🟡🟠🔴) · Nível de maturidade**.

### 7.7 Níveis de Maturidade (prontuário institucional)
Além dos percentuais, cada escola tem um **nível**:
| Nível | Nome | Critério (padrão, configurável) |
|---|---|---|
| 1 | Cadastro inicial | completude < 40% |
| 2 | Cadastro completo | completude ≥ 80% |
| 3 | Infraestrutura validada | completude ≥ 80% **e** seções de infraestrutura 🟢 |
| 4 | Conformidade institucional | conformidade geral ≥ 85% (selo 🟢) |
| 5 | Excelência operacional | conformidade ≥ 95% **e** completude ≥ 95% **e** atualização recente |

### 7.8 CTUE como "prontuário institucional" (histórico — arquitetura futura, NÃO implementar agora)
Cada alteração relevante deverá, no futuro, gerar histórico (quem/quando/o quê), permitindo
responder: *"quando a acessibilidade foi atualizada?"*, *"quando a conformidade de segurança caiu
de 100% para 66%?"*. **Sprint A1 NÃO implementa histórico**, mas a arquitetura já prevê:
- `updated_at` gravado a cada alteração (base do indicador de Atualização — já na A1);
- `ConformityResult` carimba `ruleset_id`+`versao`+timestamp (snapshotável no futuro);
- coleção futura `ctue_history` (append-only) sem quebrar o SSoT.

## 8. Pendência de aprovação → **APROVADA**. Sprint A1 autorizada.
Implementar (consumindo o **único** `CTUEConformityService`): nova interface do CTUE, Painel de
Conformidade, Índice Inteligente, indicadores por seção, mini-card na listagem e indicador de
Atualização. **Nenhuma regra de negócio duplicada entre frontend e backend** — o frontend só
consome o resultado do serviço.

*Base normativa única de conformidade do CTUE. Última atualização: Jun/2026 — refinamentos aprovados.*
