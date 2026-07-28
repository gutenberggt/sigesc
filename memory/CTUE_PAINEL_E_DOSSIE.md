# CTUE_PAINEL_E_DOSSIE.md — Entrega 3 (Painel Gerencial) + Entrega 4 (Dossiê Institucional)

> **Sprint de PROPOSTA · Jun/2026 · READ-ONLY.** Nada implementado. Ambos **consomem
> exclusivamente** os dados do CTUE (`schools`) — SSoT. Nenhum campo novo nesta etapa.
> Complementa `CTUE_ARQUITETURA.md`.

---

## ENTREGA 3 — Painel Gerencial da Rede

### 3.1 Objetivo
Dar à Secretaria uma **visão imediata da situação física da rede**, 100% a partir do cadastro
atual. Cada card é um indicador **calculável hoje** ou **dependente da Fase D** (sinalizado).

### 3.2 Arquitetura (BI-ready, SSoT)
- **Endpoint read-only:** `GET /api/schools/network-infra-overview` (escopo por mantenedora,
  filtros por zona/etapa). Retorna contadores + listas de escolas por indicador (drill-down).
- **Sem recálculo distribuído:** o contrato de saída **espelha `bi_indicator_defs`** para ser
  **absorvido pelo Motor de Indicadores** (BI-2) sem retrabalho — quando o Motor existir, o
  painel passa a consumir dele (baseline §3.9). Até lá, agregação `read-only` sobre `schools`.
- **Zero escrita.** Nenhuma coleção nova de dados (apenas cache opcional de leitura, se preciso).

### 3.3 Catálogo de indicadores
✅ = calculável HOJE (campo existe) · ⛔ = requer campo da Fase D.

| Indicador | Fórmula (sobre `schools`) | Status |
|---|---|---|
| % escolas acessíveis | `rampas AND (banheiros_acessiveis>0 OR banheiros_adaptados) AND sinalizacao_tatil` | ✅ |
| Escolas sem internet | `possui_internet = false/null` | ✅ |
| Escolas sem extintores | `coalesce(qtd_extintores,extintores,0) = 0` | ✅ |
| Escolas sem brigada de incêndio | `brigada_incendio = false` | ✅ |
| Escolas sem plano de evacuação | `plano_evacuacao = false` | ✅ |
| Escolas necessitando reforma | `estado_conservacao ∈ {ruim, precário}` | ✅ |
| Escolas com AEE | `salas_recursos_multifuncionais>0 OR aee=true` | ✅ |
| Escolas com laboratório | `possui_lab_ciencias OR possui_lab_informatica` | ✅ |
| Escolas com biblioteca | `possui_biblioteca = true` | ✅ |
| Escolas sem quadra | `NOT possui_quadra` | ✅ |
| Escolas sem cozinha/refeitório | `NOT possui_cozinha OR NOT possui_refeitorio` | ✅ |
| Escolas sem cercamento | `possui_cercamento = false` | ✅ |
| Escolas sem energia | `energia_eletrica ∈ {"Não há", vazio}` | ✅ (proxy) |
| Escolas sem água potável | `agua_potavel = false` | ⛔ Fase D (hoje: proxy por `abastecimento_agua` vazio) |
| Escolas sem AVCB (Bombeiros) | `avcb_bombeiros = false/vencido` | ⛔ Fase D |
| Escolas com obras em andamento | `obras[].situacao = "em_obra"` | ⛔ Fase D |
| Escolas sem alvará/licença sanitária | documentação | ⛔ Fase D |

### 3.4 Wireframe textual (normativo)
```
┌───────────────────────────────────────────────────────────────────────────┐
│  PAINEL DA REDE — Infraestrutura        Mantenedora ▾   Zona ▾   Etapa ▾    │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌ Acessíveis ┐ ┌ Sem Internet ┐ ┌ Sem Extintor ┐ ┌ Sem Brigada ┐          │
│  │   62%      │ │     8 esc.    │ │    3 esc.     │ │   15 esc.    │  ...    │  ← cards clicáveis (drill-down)
│  └────────────┘ └───────────────┘ └───────────────┘ └──────────────┘        │
│                                                                             │
│  [ Mapa da rede (lat/long) ]        [ Ranking por escola: conformidade % ]  │
│                                                                             │
│  ▸ Tabela drill-down (ao clicar num card):                                  │
│    Escola | Zona | Situação | (indicador) | Ação: Abrir CTUE                 │
└───────────────────────────────────────────────────────────────────────────┘
```
- **Cor semântica:** verde (ok) / âmbar (atenção) / vermelho (crítico) — coerente com o app.
- **Drill-down obrigatório:** todo card lista as escolas afetadas e leva ao CTUE da unidade.
- **Mapa** usa `latitude/longitude` (hoje ocultos → passam a ser preenchidos via CTUE).
- `data-testid`: `panel-infra-card-<indicador>`, `panel-infra-drilldown`.

### 3.5 Papéis (RBAC)
Secretário/SEMED/super_admin: rede inteira. Gestor escolar: sua(s) escola(s). Read-only.

---

## ENTREGA 4 — Dossiê Institucional da Escola (documento oficial)

### 4.1 Objetivo
Documento **anexável a processo administrativo** e endereçável a **MP, TCM/TCE, FNDE, Câmara
Municipal e Conselho Municipal de Educação**. Gerado **só com dados do CTUE**. Um clique →
PDF verificável.

### 4.2 Arquitetura (reuso — SSoT)
- **Gerador:** novo builder em `backend/pdf/dossie_institucional.py` (mesmo padrão institucional
  já usado — brasão/cabeçalho via `get_logo_image`, rodapé verificável via `verification_footer.py`).
- **Documento verificável:** reutiliza `verifiable_documents` + rota pública `/v/{token}` + QR
  (padrão já existente no sistema — nada novo de infraestrutura).
- **Endpoint:** `GET /api/schools/{id}/dossie` → PDF. Versão consolidada por mantenedora (lote).
- **Sem dado próprio:** lê `schools`; nada é recalculado nem duplicado.

### 4.3 Estrutura do documento (layout normativo)
```
┌── CABEÇALHO INSTITUCIONAL (brasão + mantenedora + secretaria) ──────────────┐
│  DOSSIÊ INSTITUCIONAL DA UNIDADE ESCOLAR — «Nome»                            │
│  Protocolo · Data de emissão · Ano-base                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. IDENTIFICAÇÃO      [foto da fachada*]   INEP · CNPJ · Zona · Situação     │  *Fase D (object storage)
│  2. LOCALIZAÇÃO        Endereço completo · georreferência (lat/long)          │
│  3. DADOS ADMINISTRATIVOS   Dependência · esfera · mantenedora · gestor       │
│  4. OFERTA DE ENSINO   Etapas/subníveis · turnos · atendimentos (AEE)         │
│  5. INFRAESTRUTURA     Salas · capacidade · ambientes pedagógicos             │
│  6. ACESSIBILIDADE     Rampas · corrimão · banheiros acessíveis · tátil       │
│  7. ÁGUA/SANEAMENTO/ENERGIA   Abastecimento · esgoto · resíduos · energia     │
│  8. SEGURANÇA          Extintores · brigada · plano evacuação · câmeras · muro│
│  9. CONECTIVIDADE      Internet · tipo · qualidade do sinal                   │
│  10. EQUIPAMENTOS/PATRIMÔNIO   Computadores · projetores · acervo · programas  │
│  11. CONSERVAÇÃO/OBRAS  Estado · reformas · obras (Fase D)                     │
│  12. DOCUMENTAÇÃO      Ato de autorização · alvará/AVCB/licença (Fase D)       │
│  13. OBSERVAÇÕES TÉCNICAS (Fase D)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  QUADRO-RESUMO DE CONFORMIDADE (checklist ✓/✗ por exigência MP/FNDE)          │
│    Água potável ✓ · Esgoto ✓ · Acessibilidade ✗ · Extintores ✓ · AVCB ✗ ...  │
├─────────────────────────────────────────────────────────────────────────────┤
│  RODAPÉ VERIFICÁVEL: código público + QR → /v/{token}   ·   assinatura        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Quadro-resumo de conformidade
Tabela final cruzando cada exigência de `MATRIZ_MP_FNDE_SIGESC.md` com o dado da escola
(✓ atende / ✗ não atende / — sem informação). É o "cartão de resposta" a órgãos de controle.

### 4.5 Regras
- Campos sem dado aparecem como **"Não informado"** (nunca em branco) — força atualização do CTUE.
- Foto: placeholder até a Fase D (object storage). Documento gera normalmente sem foto.
- Emissão **não** consome janela de rollback nem grava em logs pedagógicos (é read-only).

---

*Complemento de `CTUE_ARQUITETURA.md`. Última atualização: Jun/2026 — Sprint Proposta CTUE.*
