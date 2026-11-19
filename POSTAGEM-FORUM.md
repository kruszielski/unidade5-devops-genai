# Postagem para o fórum — Unidade 5 (DevOps + IA Generativa)

Duas versões do mesmo conteúdo: completa e curta, caso o fórum limite caracteres.
Tudo que está descrito aqui foi executado, e a evidência (logs, relatórios do agente e runs de
pipeline) está versionada no repositório.

---

## Versão completa

### 1. Repositório

**https://github.com/kruszielski/unidade5-devops-genai** (público)

O `.gitlab-ci.yml` do laboratório está no repo (estágios `test` → `analyze`). Como minha
execução foi publicada no GitHub, mantive um espelho em `.github/workflows/ci.yml` com os
mesmos dois jobs — a importação para o GitLab é direta.

| O que | Onde | Resultado |
| --- | --- | --- |
| Pipeline com o defeito intencional | [run #1 (branch `pipeline-com-falha`)](https://github.com/kruszielski/unidade5-devops-genai/actions/runs/44433058717) | job `test` **failure** · job `genai-analysis` success |
| Pipeline após a correção | [run #2 (branch `main`)](https://github.com/kruszielski/unidade5-devops-genai/actions/runs/44433145054) | **success** — 12 passed |
| Log da rodada quebrada | `logs/pipeline-run-1-falha.log` | 2 failed, 10 passed |
| Relatório do agente (IA generativa) | `reports/analise-genai-run-1.md` | duas causas-raiz corretas |
| Patch literal da IA aplicado à prova | `logs/pipeline-run-1b-patch-literal-da-ia.log` | regressão de regra de negócio |
| Decisões de correção | `docs/DECISOES-CORRECAO.md` | aceitei 1 sugestão, corrigi 1 |

### 2. Execução do projeto

A aplicação é um serviço pequeno de pedidos: `app/pricing.py` calcula subtotal, cupom, ICMS e
frete; `app/inventory.py` reserva estoque lendo o teto da configuração em `app/config.py`. Doze
testes `pytest`, com `Decimal` e sem mock.

Etapas que executei:

1. **Pipeline vermelho.** Com os dois defeitos intencionais no código, o job de testes quebrou:

   ```text
   FAILED tests/test_inventory.py::test_reserva_dentro_do_limite - KeyError: 'estoque_maximo_reserva'
   FAILED tests/test_pricing.py::test_frete_gratis_no_limite_exato - AssertionError: assert Decimal('25.00') == Decimal('0.00')
   ========================= 2 failed, 10 passed in 0.04s =========================
   ```

2. **Captura do log como artefato.** O job grava o stdout em `logs/pipeline-<id>.log` e o
   publica; o segundo estágio consome esse artefato.
3. **Análise pelo agente.** `python -m agent.analyze_log logs/pipeline-run-1-falha.log` — parseia
   o log, monta o contexto de código e chama o modelo. Modelo usado: **Gemma 4 E4B** servido
   localmente pelo LM Studio (endpoint OpenAI-compatível em `localhost:1234`, saída estruturada
   por JSON Schema). O agente escreve um relatório Markdown com tabela de fatos, diagnóstico por
   falha, confiança declarada, risco, como validar e a resposta bruta do modelo para auditoria.
4. **Validação humana da sugestão** (detalhes na seção 3) e aplicação da correção escolhida.
5. **Pipeline verde.** `12 passed`, inclusive os três testes que cobrem a transição do frete
   (abaixo do limite, no limite exato, acima do limite).

O agente **não aplica patch nem abre PR** — ele devolve diagnóstico e sugestão; quem decide sou eu.

### 3. Análise com IA generativa: qual erro foi identificado

As duas falhas tinham naturezas diferentes, e o modelo tratou as duas bem:

* **`KeyError: 'estoque_maximo_reserva'`** — o `config.py` tinha renomeado a chave para
  `max_reserva` sem atualizar o consumidor. O modelo apontou `app/inventory.py:29` e escreveu a
  causa exata: *"a chave não existe no dicionário de configurações fornecido (que contém
  `max_reserva`)"*. Isso exigiu cruzar dois arquivos: o traceback só mostra onde estourou, não a
  origem do contrato renomeado.
* **Frete grátis no limite exato** — aqui não houve exceção, foi um `AssertionError` silencioso de
  R$ 25,00. O modelo localizou `app/pricing.py:69`, leu o docstring (regra R4, limite inclusivo) e
  concluiu: *"se o líquido for exatamente igual ao limite, ele cai no bloco `else` e aplica o frete
  padrão"*. Sugestão: trocar `>` por `>=`. **Aceitei como veio** — é local e não muda contrato.

**A segunda sugestão eu rejeitei na forma proposta, e isso foi a parte mais instrutiva.** Para o
`KeyError`, a IA propôs renomear o *consumidor* (`inventory.py` passaria a ler `max_reserva`). O
que ela não podia saber: os testes injetam `carregar_configuracao({"estoque_maximo_reserva": 5})`.
Aplicando literalmente, esses overrides deixariam de valer e o teto lido voltaria a ser o padrão
(50). Fui verificar em vez de confiar — `logs/pipeline-run-1b-patch-literal-da-ia.log`:

```text
FAILED tests/test_inventory.py::test_reserva_acima_do_limite_e_recusada - Failed: DID NOT RAISE <class 'ValueError'>
========================= 2 failed, 10 passed in 0.03s =========================
```

O `KeyError` sumiu (uma falha a menos) e entrou uma **regressão de regra de negócio**: reserva de
6 unidades contra um teto configurado de 5 passou a ser aceita. O pipeline continuaria vermelho,
mas por um motivo pior — teste que falha é visível; limite de estoque ignorado em produção não é.
A correção que apliquei padronizou a chave no *produto* (`config.py` expõe
`estoque_maximo_reserva`), porque esse já era o nome observado por quem configura e pelos testes.
Critério de escolha que a IA simplesmente não tinha.

Um terceiro achado, este sobre a própria ferramenta: na resposta bruta (seção 5 do relatório), duas
chaves do JSON saíram corrompidas pelo modo estruturado — `causa_comum_raiz` em vez de
`causa_comum`, e `o_que_a_ia_nao_pode_saberudos` em vez de `o_que_a_ia_nao_pode_saber`. O conteúdo
estava lá (o modelo apontou duas lacunas), mas meu parser não o encontrou e a seção "Limites da
análise" saiu vazia. Lido com pressa, esse relatório diria "a IA não viu risco algum".

### 4. Desafios encontrados

* **O pipeline ficava verde com teste quebrado.** `pytest | tee log` devolve o código de saída do
  `tee`, que é sempre 0. Confirmei no shell: sem `pipefail`, `false | tee` → exit 0; com
  `set -o pipefail` → exit 1. Sem isso, o estágio de análise nunca rodaria e a falha viria à tona só
  em produção. Está comentado nos dois arquivos de CI hoje.
* **Incompatibilidade de provedor.** A primeira chamada ao LM Studio retornou `HTTP 400` — o servidor
  exigia saída estruturada (`'response_format.type' must be 'json_schema' or 'text'`). Passei a
  enviar `json_schema`, mas provedores mais simples recusam o schema. O agente agora tenta com schema
  e, se o provedor não aceitar, repete sem ele e faz parse do texto.
* **Meu parser de log estava errado, e só apareceu na execução real.** Eu assumia que o pytest imprime
  o frame como `arquivo.py:29: in funcao`, mas ele imprime `app/inventory.py:29: KeyError`. A primeira
  versão do relatório apontava `tests/test_inventory.py:12` (o teste) e `?:?` para a falha de asserção
  — o agente estava "analisando" sem enxergar o código de produção. Ajustei a regex e passei a mandar
  os módulos de produção completos como contexto, não só a linha que quebrou.
* **Runner público sem credencial.** No GitHub Actions não há endpoint de IA nem chave. Em vez de
  deixar o job quebrar, o agente degrada para análise heurística determinística do traceback e o
  relatório sai marcado com o motivo (`Connection refused`). Foi o que aconteceu no run #1: job de
  análise **success**, artefato publicado, nenhuma credencial exposta.
* **Escolher qual lado renomear** (a configuração ou o consumidor) não é decisão técnica, é de
  contrato — e a IA escolheu o lado errado com confiança declarada "alta".
* Menores: latência para carregar um modelo de ~6,8 GB local na primeira chamada (o job precisa de
  timeout generoso) e manter o prompt pequeno — despejar o log inteiro só infla custo e piora a
  atenção do modelo.

### 5. Reflexão crítica

**Vantagens que vi na prática.** Cobertura e velocidade: em segundos o modelo cruzou três arquivos,
leu a regra de negócio escrita num docstring e propôs as duas correções certas — inclusive para o
`AssertionError` silencioso de R$ 25,00, que é o tipo de falha que normalmente vira chute por
bisseção. Além disso, devolve um diagnóstico redigido, pronto para ir ao ticket/PR, e degrada bem:
sem IA eu ainda fico com a extração determinística dos fatos do log.

**Limitações que também vi.** (1) O modelo não vê o ambiente de execução, nem o histórico do
`config.py`, nem quem consome a chave — ele raciocina sobre o recorte que enviei, e errou o lado do
renomeio exatamente por não ter esse contexto. (2) A autoavaliação dele não é confiável: marcou
**confiança "alta"** numa mudança que introduzia regressão de regra de negócio. Confiança declarada
não é evidência. (3) A saída estruturada pode falhar em silêncio — campo com nome corrompido vira
"nenhum risco apontado". (4) Ele otimiza "o teste passar", não "o sistema correto": sem supervisão, o
caminho mais curto para um pipeline verde é enfraquecer o teste. Por isso isso está proibido no prompt
de sistema e no checklist do relatório.

**Por que validar antes de aplicar.** Porque o custo do erro é assimétrico: uma sugestão errada não
produz necessariamente um pipeline vermelho — pode produzir um pipeline **verde com comportamento
errado**, como quando a reserva acima do teto passou a ser aceita. A validação foi barata e
reprodutível: reproduzir a falha, aplicar a sugestão numa cópia isolada, rodar a suíte inteira (não só
o teste que estava quebrando) e comparar os números — `2 failed, 10 passed` antes e `2 failed, 10
passed` depois, porém com outra falha no lugar. Sem a suíte completa, eu teria visto apenas "o KeyError
sumiu" e aprovado a mudança.

O papel da IA aqui é de amplificador de triagem: ela encurta o tempo até a hipótese certa. Decidir se
a hipótese é segura continua humano, porque exige contexto que não está no log — contrato de
configuração, regra de negócio e consequência financeira.

*Transparência: modelo local Gemma 4 E4B via LM Studio; nenhum segredo em repositório, log ou
relatório. Os defeitos são intencionais e estão documentados.*

---

## Versão curta

**Repositório:** https://github.com/kruszielski/unidade5-devops-genai (`.gitlab-ci.yml` do laboratório
incluído; espelho no GitHub Actions). Run vermelho:
[actions/runs/44433058717](https://github.com/kruszielski/unidade5-devops-genai/actions/runs/44433058717)
· run verde: [actions/runs/44433145054](https://github.com/kruszielski/unidade5-devops-genai/actions/runs/44433145054)

**Execução:** app Python de pedidos + 12 testes `pytest` com dois defeitos intencionais. O pipeline
quebrou (`2 failed, 10 passed`), o log virou artefato e um agente GenAI (Gemma 4 E4B local via LM
Studio, saída em JSON Schema) analisou o log e devolveu relatório com causa-raiz, correção sugerida,
risco e checklist de validação. Após a correção: `12 passed`.

**Análise com IA:** acertou as duas causas — `KeyError` por chave renomeada em `config.py` (apontou
`app/inventory.py:29`) e limite de frete grátis tratado como exclusivo quando a regra é inclusiva
(`app/pricing.py:69`, `>` → `>=`). A primeira sugestão aceitei; a segunda rejeitei na forma proposta:
renomear o consumidor para ler `max_reserva` invalidava os overrides dos testes e passava a aceitar
reserva acima do teto (prova em `logs/pipeline-run-1b-patch-literal-da-ia.log`, com `DID NOT RAISE`).
Padronizei a chave no produto.

**Desafios:** `pytest | tee` mascara o exit code e mantinha o pipeline verde com teste quebrado (falta
`set -o pipefail`); o LM Studio exigiu `response_format: json_schema`, que provedores mais simples
recusam (o agente tenta com schema e cai para texto); meu parser de traceback estava errado até rodar
de verdade; no runner público sem credencial o agente degrada para análise heurística e ainda publica
evidência.

**Reflexão:** a IA encurta o caminho até a hipótese certa e lê regra de negócio que está no código, mas
não conhece o ambiente nem o contrato entre módulos, e a própria nota de confiança não é confiável —
marcou "alta" numa mudança que causaria regressão. Validar importa porque o erro pode deixar o pipeline
**verde com comportamento errado**: rodei a suíte inteira antes de aprovar qualquer sugestão e mantive a
IA fora da decisão de merge.


