# Análise GenAI do pipeline — `pipeline-run-1-falha.log`

- **Executado em:** 2026-11-18 21:53:00 -03
- **Modo:** heurístico
- **Modelo / endpoint:** `google/gemma-4-e4b (não utilizado)` · `—`
- **Resumo do job (pytest):** 2 failed, 10 passed
- **Falhas parseadas no log:** 2
- **Motivo do fallback:** Modo heurístico (--no-llm informado): localizei as exceções no traceback, mas não há diagnóstico semântico gerado por IA nesta execução.

## 1. Fatos extraídos do log (parse determinístico)

| Teste | Arquivo:linha | Exceção | Mensagem |
| --- | --- | --- | --- |
| `test_reserva_dentro_do_limite` | `app/inventory.py:29` | `KeyError` | KeyError: 'estoque_maximo_reserva' |
| `test_frete_gratis_no_limite_exato` | `tests/test_pricing.py:53` | `AssertionError` | AssertionError: assert Decimal('25.00') == Decimal('0.00') |

## 2. Diagnóstico gerado pela IA generativa

**Diagnóstico:** Modo heurístico (--no-llm informado): localizei as exceções no traceback, mas não há diagnóstico semântico gerado por IA nesta execução.

### 2.1 `test_reserva_dentro_do_limite`

- **Onde:** `app/inventory.py:29`
- **Causa provável:** KeyError levantada em app/inventory.py:29
- **Confiança declarada:** média
- **Risco da mudança:** sem análise semântica; apenas localização do erro
- **Como validar:** reproduzir localmente com `pytest -v` e inspecionar o frame apontado

Correção sugerida:

```python
(não sugerida — modo heurístico não aplica IA)
```

### 2.2 `test_frete_gratis_no_limite_exato`

- **Onde:** `tests/test_pricing.py:53`
- **Causa provável:** AssertionError levantada em tests/test_pricing.py:53
- **Confiança declarada:** média
- **Risco da mudança:** sem análise semântica; apenas localização do erro
- **Como validar:** reproduzir localmente com `pytest -v` e inspecionar o frame apontado

Correção sugerida:

```python
(não sugerida — modo heurístico não aplica IA)
```

## 3. Limites do que foi analisado automaticamente

- nenhuma análise generativa foi executada nesta rodada

## 4. Checklist de validação humana antes de aplicar qualquer correção

- [ ] Reproduzi a falha localmente antes de mexer em qualquer coisa (`pytest -v`).
- [ ] A correção ataca a **causa-raiz**, não o sintoma (não alterei teste para "passar").
- [ ] Rodei a suíte completa depois do patch e comparei com o resumo anterior.
- [ ] Confirmei com o dono do produto se a sugestão muda regra de negócio ou contrato público.
- [ ] Verifiquei se a correção não esconde um problema de ambiente/configuração fora do repo.
- [ ] Registrei no PR o que foi sugestão da IA e o que foi decisão minha.
