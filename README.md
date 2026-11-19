# DevOps com IA Generativa — diagnóstico de falhas em pipeline (Unidade 5)

Projeto Integrador da pós-graduação: uma aplicação Python pequena, com **defeito intencional**,
suíte de testes automatizados e um **agente de IA generativa que lê o log do job de CI,
diagnostica a causa-raiz e sugere correção** — sem aplicar nada sozinho.

O ciclo completo foi executado de verdade e está registrado no repositório:
`pipeline vermelho → log → análise GenAI → validação humana → pipeline verde`.

| Etapa | Evidência | Resultado |
| --- | --- | --- |
| Pipeline com defeito | `logs/pipeline-run-1-falha.log` | 2 failed, 10 passed |
| Análise do log pelo agente | `reports/analise-genai-run-1.md` | Gemma 4 E4B (LM Studio) acertou as duas causas-raiz |
| Patch literal da IA aplicado à prova | `logs/pipeline-run-1b-patch-literal-da-ia.log` | 2 failed — uma regressão de regra de negócio no lugar do `KeyError` |
| Fallback sem modelo disponível | `reports/analise-heuristica-run-1.md` | relatório determinístico, sem credencial nenhuma |
| Correção validada | `logs/pipeline-run-2-corrigido.log` | 12 passed |

A narrativa detalhada das decisões (o que a IA sugeriu, o que aceitei e o que corrigi) está em
[`docs/DECISOES-CORRECAO.md`](docs/DECISOES-CORRECAO.md).

## Estrutura

```text
app/                    aplicação sob teste
  config.py               configuração central (a renomeação de chave é o defeito nº 1)
  pricing.py              cálculo do total do pedido (o limite de frete é o defeito nº 2)
  inventory.py            reserva de estoque, consumidora da configuração
tests/                  12 testes pytest (stdlib + Decimal, sem mock)
agent/analyze_log.py    agente: parseia o log, monta contexto, chama o modelo, gera relatório
agent/report.py         renderização do relatório Markdown (artefato do CI)
logs/                   stdout real dos jobs de pipeline
reports/                relatórios gerados pelo agente
docs/                   registro das decisões de correção
.gitlab-ci.yml          pipeline do laboratório (GitLab: test → analyze)
.github/workflows/ci.yml  espelho executando no GitHub Actions
```

## Rodando localmente

```bash
python -m pip install -r requirements.txt

# 1) testes (é o job "test" do pipeline)
python -m pytest -v --tb=long | tee logs/pipeline-local.log

# 2) análise do log por IA generativa (job "analyze")
python -m agent.analyze_log logs/pipeline-local.log --out reports/analise-local.md
```

O agente usa **somente a biblioteca padrão** — nenhum pacote extra no runner.

### Provedor de IA generativa

Configurável por variáveis de ambiente; qualquer endpoint compatível com a API da OpenAI serve:

| Variável | Padrão | Observação |
| --- | --- | --- |
| `GENAI_BASE_URL` | `http://localhost:1234/v1` | LM Studio local neste projeto |
| `GENAI_MODEL` | `google/gemma-4-e4b` | troque por qualquer modelo do seu endpoint |
| `GENAI_API_KEY` | vazio | só necessário em provedor remoto; nunca é impresso no relatório |

Se o endpoint não responder (ou se a chave não existir, como no runner público), o agente **não
quebra o job**: degrada para análise heurística determinística do traceback e marca isso no
relatório. Use `--no-llm` para forçar esse modo.

### O que o agente faz, passo a passo

1. **Parse determinístico** do stdout do pytest: blocos de falha, frames `arquivo:linha`,
   exceção e mensagem. Nada aqui depende de IA — é o chão de fatos.
2. **Contexto de código**: módulos de produção completos + os frames apontados (com `>>>` na
   linha do erro), em vez de despejar o log inteiro no prompt.
3. **Chamada ao modelo** com saída estruturada (`response_format: json_schema`; se o provedor
   recusar o schema, repete a chamada sem ele e faz parse do texto).
4. **Relatório Markdown** com tabela de fatos, diagnóstico por falha (causa, correção,
   confiança declarada, risco, como validar), limites da análise, checklist de validação humana
   e a resposta bruta do modelo para auditoria.

O agente **não edita código nem abre PR**: a decisão de aplicar continua humana.

## Pipeline

`test` roda `pytest -v --tb=long | tee logs/…`; `analyze` consome o artefato de log, roda o
agente e publica o relatório. O job de análise tem `allow_failure: true` — IA é apoio ao
diagnóstico, não portão de merge.

Detalhe que quase passou despercebido: sem `set -o pipefail`, o `tee` devolve seu próprio código
de saída (sempre 0) e **o pipeline fica verde com testes quebrando**. Está comentado nos dois
arquivos de CI.

## Segurança

Nenhum segredo no repositório ou nos logs. Em CI, as credenciais do provedor vêm de secrets/CI
variables mascaradas; sem elas o job usa o fallback heurístico e continua produzindo evidência.
