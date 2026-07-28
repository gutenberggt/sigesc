# AUDITORIA_CAMPOS_ESCOLAS.md — Inventário campo a campo (Modelo × Interface)

> **Sprint READ-ONLY (Jun/2026).** Documento auxiliar da `AUDITORIA_CADASTRO_ESCOLAS.md`.
> **Nenhum código, modelo, coleção ou migração foi alterado.** Apenas leitura + evidência.
> **Fontes primárias:** `backend/models.py::SchoolBase` (linhas 356–574) e
> `frontend/src/pages/SchoolsComplete.js` (formulário de cadastro, 8 abas).

## 1. Método (reprodutível)
- **Modelo:** extração dos 135 atributos de `SchoolBase` (`SchoolCreate`/`SchoolUpdate` são espelhos).
- **Interface:** extração de todos os `updateFormData('<campo>', …)` de `SchoolsComplete.js`
  → **80 campos** efetivamente editáveis na UI (inclui subníveis de ensino e permissões).
- **Gap:** `comm -23 modelo interface` → **55 campos existem no modelo mas NÃO são
  editáveis em nenhuma aba da interface**.
- Abas da UI: `Geral · Infraestrutura · Dependências · Equipamentos · Ensino · Turmas · Servidores · Permissão`.

## 2. Placar
| Métrica | Valor |
|---|---|
| Campos no modelo `SchoolBase` | **135** |
| Campos editáveis na interface | **80** |
| **Campos do modelo OCULTOS na interface** | **55** (41%) |
| Campos exigidos por MP/FNDE **ausentes até do modelo** | ver §5 |

**Leitura:** o modelo é rico; a interface expõe menos da metade dos campos de
infraestrutura/segurança/gestão. **A lacuna dominante é de UX/exposição, não de modelo** —
confirmando a hipótese do owner.

## 3. Inventário por aba — o que a interface EXPÕE

### Aba "Geral"
Expõe: `name, inep_code, cnpj, caracteristica_escolar, zona_localizacao, tipo_unidade,
anexa_a` · Localização: `cep, logradouro, numero, complemento, bairro, municipio, estado` ·
Contatos: `telefone, celular, email, site`.

### Aba "Infraestrutura"
- **Serviços Básicos:** `abastecimento_agua`, `energia_eletrica`.
- **Acessibilidade:** `possui_rampas`, `possui_corrimao`, `banheiros_adaptados`, `sinalizacao_tatil`.
- **Conectividade:** `possui_internet`, `tipo_conexao`.

### Aba "Dependências"
`numero_salas_aula`, `capacidade_total_alunos`, `numero_banheiros`, `possui_biblioteca`,
`possui_lab_ciencias`, `possui_lab_informatica`, `possui_quadra`, `possui_cozinha`, `possui_refeitorio`.

### Aba "Equipamentos"
`qtd_computadores, qtd_tablets, qtd_projetores, qtd_impressoras, qtd_televisores,
qtd_projetores_multimidia, qtd_aparelhos_som, qtd_lousas_digitais`.

### Aba "Ensino"
Etapas: `educacao_infantil, fundamental_anos_iniciais, fundamental_anos_finais, ensino_medio,
eja, eja_final` + **todos os subníveis** (`educacao_infantil_*`, `fundamental_inicial_1..5ano`,
`fundamental_final_6..9ano`, `eja_inicial_*`, `eja_final_*`) · Atendimentos: `aee,
atendimento_integral, reforco_escolar, recomposicao_aprendizagem`.

### Aba "Permissão"
`bimestre_1..4_limite_lancamento`, `pre_matricula_ativa`, `anos_letivos`
(gerenciamento de status por ano letivo).

### Abas "Turmas" e "Servidores"
Relacionais (vínculos), sem campos próprios de `SchoolBase`.

## 4. Campos do MODELO OCULTOS na interface (55) — agrupados por relevância MP/FNDE

### 🔴 Infraestrutura crítica (MP/TCE cobram diretamente)
| Campo | Grupo | Observação |
|---|---|---|
| `saneamento` | Serviços | **Esgotamento sanitário** — no modelo, invisível na UI. Item central do MP. |
| `coleta_lixo` | Serviços | Destinação do lixo — invisível na UI. |
| `banheiros_acessiveis` | Acessibilidade | Contagem de banheiros acessíveis (PcD). |
| `estado_conservacao` | Conservação | **Seção inteira ausente** na UI. |
| `possui_cercamento` | Conservação | Muro/cerca — segurança patrimonial. |
| `saidas_emergencia` | Segurança | **Seção inteira ausente** na UI. |
| `extintores` / `qtd_extintores` | Segurança | Combate a incêndio. |
| `brigada_incendio` | Segurança | Exigido em vistoria de bombeiros. |
| `plano_evacuacao` | Segurança | Exigido em vistoria de bombeiros. |
| `qtd_cameras` | Segurança | Videomonitoramento. |
| `cobertura_rede` | Conectividade | Qualidade do sinal. |

### 🟠 Dependências físicas (Educacenso — ambientes existentes)
`salas_recursos_multifuncionais` (**AEE!**), `sala_direcao`, `sala_secretaria`,
`sala_coordenacao`, `sala_professores`, `possui_almoxarifado`, `possui_quadra_esportiva`,
`possui_patio`, `possui_parque`, `possui_brinquedoteca`, `possui_auditorio`, `possui_horta`,
`possui_estacionamento`. → **"Espaços Escolares" inteiro do modelo não tem UI.**

### 🟠 Georreferenciamento e identificação
`latitude`, `longitude` (localização de obras/vistorias), `sigla`, `situacao_funcionamento`,
`distrito`, `ddd_telefone`.

### 🟡 Vinculação / Mantenedora (dados administrativos oficiais)
`dependencia_administrativa`, `orgao_responsavel`, `esfera_administrativa`,
`categoria_mantenedora`, `cnpj_mantenedora`, `forma_contratacao_estadual`,
`forma_contratacao_municipal`, `possui_convenio`.

### 🟡 Equipe gestora
`gestor_principal`, `cargo_gestor`, `secretario_escolar`.

### 🟡 Regime pedagógico / recursos
`turnos_funcionamento`, `organizacao_turmas`, `tipo_avaliacao`, `niveis_ensino_oferecidos`,
`participa_programas_governamentais`, `possui_material_didatico`, `tamanho_acervo`,
`possui_kits_cientificos`, `possui_instrumentos_musicais`.

### ⚫ Técnicos / legados
`anos_letivos_ativos`, `bloquear_lancamento_anos_encerrados`, `usar_regra_alternativa`,
`aulas_complementares` (legado), `educacao_infantil_bercario` (retrocompat).

## 5. Campos exigidos por MP/FNDE/Educacenso 2026 AUSENTES ATÉ DO MODELO
> Detalhamento e cruzamento normativo em `MATRIZ_MP_FNDE_SIGESC.md`.

1. **Regime de ocupação do prédio** (próprio / alugado / cedido / compartilhado) — Educacenso "local de funcionamento".
2. **Prédio compartilhado** com outra escola (sim/não + qual).
3. **Potabilidade da água** / certificado de potabilidade (recorrente em MP/TCE) — modelo só tem *forma* de abastecimento.
4. **Esgotamento sanitário tipificado** (rede pública / fossa séptica / fossa rudimentar / inexistente) — hoje `saneamento` é texto livre.
5. **Destinação do lixo tipificada** (coleta periódica / queima / enterra / joga) — hoje `coleta_lixo` é texto livre.
6. **Obras/Reformas:** situação atual (em obra/reforma/paralisada), tipo, valor, **fonte do recurso (PAR/FNDE/PDDE)**, datas.
7. **Conformidade legal:** Alvará de funcionamento, Licença sanitária (Vigilância), **AVCB/laudo dos Bombeiros**, Habite-se.
8. **Metragem:** área do terreno (m²), área construída (m²), **ano de construção**.
9. **Alimentação escolar:** fornece alimentação? (Educacenso).
10. **Dependências Educacenso refinadas:** pátio coberto × descoberto (hoje 1 bool), sala de leitura, despensa, lavanderia, área verde, alojamento.

*Última atualização: Jun/2026 — Sprint READ-ONLY Auditoria do Cadastro de Escolas.*
