# Decisões de correção — pipeline vermelho → verde

Registro do ciclo real executado neste repositório: **pipeline quebrado → log → análise
GenAI → validação humana → correção**. Os logs completos estão em `logs/` e os relatórios
do agente em `reports/`.

## 1. Estado inicial (rodada 1) — pipeline vermelho

`logs/pipeline-run-1-falha.log`

```text
FAILED tests/test_inventory.py::test_reserva_dentro_do_limite - KeyError: 'estoque_maximo_reserva'
FAILED tests/test_pricing.py::test_frete_gratis_no_limite_exato - AssertionError: assert Decimal('25.00') == Decimal('0.00')
========================= 2 failed, 10 passed in 0.04s =========================
```

Dois defeitos intencionais, de naturezas diferentes:

| # | Sintoma no log | Defeito real |
| --- | --- | --- |
| 1 | `KeyError: 'estoque_maximo_reserva'` em `app/inventory.py:29` | `app/config.py` renomeou a chave para `max_reserva` sem atualizar o consumidor |
| 2 | `AssertionError: Decimal('25.00') == Decimal('0.00')` no teste do limite de frete | `app/pricing.py:69` usava `>` em vez de `>=`, tornando exclusivo um limite que a regra R4 define inclusivo |

## 2. O que a IA generativa devolveu

Modelo local `google/gemma-4-e4b` (LM Studio, endpoint OpenAI-compatível), saída
estruturada por JSON Schema. Relatório integral: `reports/analise-genai-run-1.md`.

* **Falha 1** — apontou `app/inventory.py:29` e a causa exata: *"a chave não existe no
  dicionário de configurações fornecido (que contém `max_reserva`)"*. Confiança declarada:
  alta. Sugestão: *mudar o acesso para `config["max_reserva"]`*.
* **Falha 2** — apontou `app/pricing.py:69`, leu a regra R4 no docstring e concluiu que
  *"se o líquido for exatamente igual ao limite, ele cai no bloco `else`"*. Sugestão:
  *usar `>=`*.

## 3. Validação humana — uma sugestão aceita, uma corrigida

**Falha 2: aceita como veio.** `>` → `>=`. O teste do limite exato já existia e a mudança é
local, sem efeito em contrato público.

**Falha 1: rejeitada na forma proposta.** A IA escolheu o lado *errado* para renomear. Se
`inventory.py` passasse a ler `max_reserva`, os testes que injetam
`carregar_configuracao({"estoque_maximo_reserva": 5})` continuariam existindo, mas deixariam
de surtir efeito: o teto lido voltaria a ser o padrão (50).

Comprovado em `logs/pipeline-run-1b-patch-literal-da-ia.log`, aplicando literalmente a
sugestão da IA:

```text
FAILED tests/test_inventory.py::test_reserva_acima_do_limite_e_recusada - Failed: DID NOT RAISE ...
========================= 2 failed, 10 passed in 0.03s =========================
```

Ou seja: o `KeyError` sumiu (uma falha a menos) e entrou uma **regressão silenciosa de regra
de negócio** — uma reserva de 6 unidades contra um teto configurado de 5 passou a ser aceita.
O pipeline continuaria vermelho, mas agora por um motivo pior: um teste que falha é visível;
um limite de estoque ignorado em produção não seria.

**Correção aplicada:** padronizei a chave no *produto*, não no consumidor — `app/config.py`
passou a expor `estoque_maximo_reserva`, nome que já era usado por `inventory.py`, pelos
overrides dos testes e pela convenção das demais chaves. O critério de escolha (que a IA não
tinha) é: o contrato observável por quem configura e testava já usava esse nome.

## 4. Estado final (rodada 2) — pipeline verde

`logs/pipeline-run-2-corrigido.log`

```text
============================== 12 passed in 0.02s ==============================
```

## 5. Efeito colateral encontrado no caminho

Na resposta bruta do modelo (`reports/analise-genai-run-1.md`, seção 5), duas chaves do JSON
saíram corrompidas pelo modo estruturado: `causa_comum_raiz` (em vez de `causa_comum`) e
`o_que_a_ia_nao_pode_saberudos` (em vez de `o_que_a_ia_nao_pode_saber`). O conteúdo estava lá,
mas o parser do relatório não o encontrou e a seção "Limites do que foi analisado" saiu vazia.

Nada nisso invalida o diagnóstico — mas mostra que **validar a saída estruturada também é
parte do trabalho**: um campo silenciosamente ausente pode ser lido como "o modelo não viu
risco algum", quando na verdade ele apontou dois.
