"""Agente de análise de logs de pipeline com IA generativa (Unidade 5).

Uso:

    python -m agent.analyze_log logs/pipeline-run-1-falha.log \
        --out reports/analise-genai-run-1.md

Variáveis de ambiente do provedor GenAI (todas opcionais):

* ``GENAI_BASE_URL`` — endpoint compatível com OpenAI. Padrão: LM Studio local
  (``http://localhost:1234/v1``).
* ``GENAI_MODEL``    — id do modelo. Padrão: ``google/gemma-4-e4b``.
* ``GENAI_API_KEY``  — token do provedor; **nunca** é impresso no relatório.

Se o endpoint não responder, o agente degrada para uma análise heurística
determinística (extração de traceback) e marca isso no relatório — o pipeline
continua produzindo evidência mesmo sem credenciais configuradas.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent.report import render_relatorio

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "google/gemma-4-e4b"

# --------------------------------------------------------------------------- #
# Etapa 1 — extração determinística das falhas (não depende de IA)
# --------------------------------------------------------------------------- #

FALHA_HEADER = re.compile(r"^_{5,}\s+(?P<nome>[\w./:\-\[\] ]+?)\s+_{5,}$")
# O pytest imprime o frame como "app/inventory.py:29: KeyError" ou "...:29: in reservar".
FRAME = re.compile(
    r"^(?P<arquivo>(?:app|src|tests)[\\/.][\w./\\-]+\.py):(?P<linha>\d+)"
    r"(?::\s*(?:in\s+(?P<funcao>[\w<>._]+)|(?P<contexto>.+?))?)?\s*$"
)
ERRO_LINHA = re.compile(r"^E\s+(?P<mensagem>\S.*)$")
EXCECAO = re.compile(r"^(?P<tipo>[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit))\b")
RESUMO = re.compile(r"^=+\s+(?P<resumo>[\d\s,]+(?:passed|failed|error).*?)\s+in\s+[\d.]+s.*?=+\s*$")


def extrair_resumo(log: str) -> str:
    """Linha de resumo do pytest (ex.: ``3 failed, 9 passed in 0.21s``)."""
    for linha in reversed(log.splitlines()):
        m = RESUMO.match(linha.strip())
        if m:
            return m.group("resumo")
    return "resumo não encontrado no log"


def extrair_falhas(log: str) -> list[dict[str, Any]]:
    """Converte o stdout do pytest em uma lista estruturada de falhas.

    Cada item traz o teste, o último frame de código da aplicação (a causa mais
    provável), a exceção levantada e o trecho do traceback — é esse pacote que vira
    contexto para o modelo, em vez do log inteiro.
    """
    linhas = log.splitlines()

    inicios: list[tuple[int, str]] = []
    for i, linha in enumerate(linhas):
        m = FALHA_HEADER.match(linha)
        if m:
            inicios.append((i, m.group("nome")))

    falhas: list[dict[str, Any]] = []
    for pos, (inicio, nome) in enumerate(inicios):
        fim = inicios[pos + 1][0] if pos + 1 < len(inicios) else _indice_failures_fim(linhas, inicio)
        bloco = linhas[inicio:fim]

        frames = [FRAME.match(l) for l in bloco]
        frames = [
            {"arquivo": m.group("arquivo").replace("\\", "/"), "linha": m.group("linha"),
             "funcao": m.group("funcao")}
            for m in frames if m
        ]
        mensagens = [m.group("mensagem") for m in (ERRO_LINHA.match(l) for l in bloco) if m]

        # Frame de produção vence o frame de teste: é onde a correção entra.
        frames_app = [f for f in frames if not f["arquivo"].startswith("tests")]
        alvo = frames_app[-1] if frames_app else (frames[-1] if frames else None)

        excecao, detalhe = "desconhecida", ""
        for mensagem in mensagens:
            m = EXCECAO.match(mensagem.strip())
            if m:
                excecao, detalhe = m.group("tipo"), mensagem.strip()
                break
        if not detalhe and mensagens:
            detalhe = mensagens[0].strip()

        falhas.append(
            {
                "teste": nome,
                "arquivo": alvo["arquivo"] if alvo else None,
                "linha": int(alvo["linha"]) if alvo else None,
                "funcao": (alvo or {}).get("funcao"),
                "excecao": excecao,
                "mensagem": detalhe,
                "traceback": "\n".join(bloco[:40]),
            }
        )

    # Falhas sem bloco de traceback (erro de coleta/job) ainda merecem registro.
    if not falhas:
        for linha in linhas:
            if linha.startswith(("FAILED", "ERROR")) and "::" in linha:
                partes = linha.split()
                falhas.append(
                    {
                        "teste": partes[1] if len(partes) > 1 else linha,
                        "arquivo": None,
                        "linha": None,
                        "funcao": None,
                        "excecao": "falha sem traceback no log",
                        "mensagem": linha.strip(),
                        "traceback": linha.strip(),
                    }
                )
    return falhas


def _indice_failures_fim(linhas: list[str], inicio: int) -> int:
    for i in range(inicio + 1, len(linhas)):
        if FALHA_HEADER.match(linhas[i]):
            return i
        if linhas[i].startswith(("short test summary", "=== short test")):
            return i
    return len(linhas)


def contexto_codigo(falhas: list[dict[str, Any]], raiz: Path, janela: int = 8) -> str:
    """Contexto de código que o agente consegue ler: produção inteira + frames do traceback.

    Em um serviço pequeno vale mais mandar o módulo de produção completo (o modelo
    precisa enxergar a regra, não só a linha que quebrou) e usar o frame do teste para
    mostrar o valor esperado pela especificação.
    """
    blocos: list[str] = []

    pasta_app = raiz / "app"
    if pasta_app.is_dir():
        for caminho in sorted(pasta_app.glob("*.py")):
            conteudo = caminho.read_text(encoding="utf-8").splitlines()
            numeradas = [f"{n:4d} | " + linha for n, linha in enumerate(conteudo, start=1)]
            blocos.append(f"### app/{caminho.name} (arquivo completo)\n```python\n" + "\n".join(numeradas) + "\n```")

    vistos: set[tuple[str, int]] = set()
    for falha in falhas:
        arquivo, linha = falha.get("arquivo"), falha.get("linha")
        if not arquivo or linha is None or (arquivo, linha) in vistos:
            continue
        vistos.add((arquivo, linha))

        caminho = raiz / arquivo
        if not caminho.exists():
            blocos.append(f"### {arquivo}\n(arquivo não encontrado no repositório)")
            continue

        linhas = caminho.read_text(encoding="utf-8").splitlines()
        inicio, fim = max(1, linha - janela), min(len(linhas), linha + janela)
        numeradas = [
            (f">>> {n:4d} | " if n == linha else f"     {n:4d} | ") + linhas[n - 1]
            for n in range(inicio, fim + 1)
        ]
        origem = "frame do teste (especificação)" if arquivo.startswith("tests") else "frame de produção"
        blocos.append(f"### {arquivo}:{linha} — {origem}\n```python\n" + "\n".join(numeradas) + "\n```")

    return "\n\n".join(blocos) if blocos else "(sem código-fonte associado às falhas)"


# --------------------------------------------------------------------------- #
# Etapa 2 — prompt, chamada ao modelo e fallback heurístico
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """Você é um engenheiro de DevOps sênior analisando o log de um job de CI \
que quebrou. Responda SEMPRE em português do Brasil e apenas com JSON válido, sem texto \
fora do JSON, no formato:
{"diagnostico": string, "falhas": [{"teste": string, "arquivo": string, "linha": int, \
"causa_provavel": string, "correcao_sugerida": string, "confianca": "alta|média|baixa", \
"risco": string, "como_validar": string}], "causa_comum": string|null, \
"o_que_a_ia_nao_pode_saber": [string]}
Regras: (1) baseie-se somente no log e no código fornecidos; (2) se duas falhas têm a mesma \
causa-raiz, diga isso em "causa_comum"; (3) nunca sugira apagar ou enfraquecer teste para o \
pipeline ficar verde; (4) se faltar contexto para ter certeza, marque confiança baixa e explique \
o que verificar; (5) "correcao_sugerida" deve ser um trecho de código curto e concreto."""


def montar_prompt(falhas: list[dict[str, Any]], resumo: str, codigo: str, log_nome: str) -> str:
    """Prompt enxuto: só o pacote das falhas + o código apontado, não o log cru inteiro."""
    return f"""Log analisado: {log_nome}
Resumo do job: {resumo}

Falhas extraídas do log (parse determinístico):
{json.dumps([{k: v for k, v in f.items() if k != 'traceback'} for f in falhas], ensure_ascii=False, indent=2)}

Tracebacks:
{chr(10).join('--- ' + f['teste'] + chr(10) + f['traceback'] for f in falhas)[:6000]}

Código-fonte do repositório (módulos de produção completos + frames do traceback; \
">>>" marca a linha apontada pelo erro):
{codigo[:14000]}

Diagnostique as falhas. Seja específico sobre arquivo e linha, e separe o que é fato \
observado no log do que é hipótese."""


#: Saída estruturada exigida do modelo. Nem todo provedor aceita ``json_schema``,
#: então a chamada tenta com schema e, se o provedor recusar, repete sem ele.
SCHEMA_DIAGNOSTICO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "diagnostico": {"type": "string"},
        "causa_comum": {"type": "string"},
        "falhas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "teste": {"type": "string"},
                    "arquivo": {"type": "string"},
                    "linha": {"type": "integer"},
                    "causa_provavel": {"type": "string"},
                    "correcao_sugerida": {"type": "string"},
                    "confianca": {"type": "string", "enum": ["alta", "média", "baixa"]},
                    "risco": {"type": "string"},
                    "como_validar": {"type": "string"},
                },
                "required": ["teste", "causa_provavel", "correcao_sugerida", "confianca"],
            },
        },
        "o_que_a_ia_nao_pode_saber": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["diagnostico", "falhas"],
}


def _post(url: str, corpo: dict[str, Any], timeout: int) -> dict[str, Any]:
    """POST JSON com Authorization opcional; erro HTTP sobe com o corpo da resposta."""
    requisicao = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST")
    requisicao.add_header("Content-Type", "application/json")
    chave = os.environ.get("GENAI_API_KEY")
    if chave:
        requisicao.add_header("Authorization", f"Bearer {chave}")

    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        detalhe = erro.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {erro.code} do endpoint GenAI: {detalhe}") from None


def chamar_ia(prompt: str, base_url: str, model: str, timeout: int) -> dict[str, Any]:
    """Chama o endpoint OpenAI-compatível pedindo saída estruturada.

    Ordem de tentativa: (1) ``response_format=json_schema`` — LM Studio e provedores
    estritos exigem isso; (2) sem ``response_format``, parseando o texto devolvido —
    provedores mais simples (Ollama, vLLM antigo) recusam o schema.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    corpo_base: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1400,
    }

    tentativas = (
        {**corpo_base, "response_format": {"type": "json_schema",
                                           "json_schema": {"name": "diagnostico_ci",
                                                           "schema": SCHEMA_DIAGNOSTICO}}},
        corpo_base,
    )

    erros: list[str] = []
    for corpo in tentativas:
        try:
            dados = _post(url, corpo, timeout)
            texto = dados["choices"][0]["message"]["content"] or ""
            return {"texto": texto, "dados": _extrair_json(texto), "modelo": model, "endpoint": url}
        except RuntimeError as erro:
            erros.append(str(erro))          # provedor pode não aceitar json_schema
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as erro:
            erros.append(f"{type(erro).__name__}: {erro}")

    raise RuntimeError(" | ".join(erros))


def _extrair_json(texto: str) -> dict[str, Any] | None:
    """Aceita resposta com cercas de código ou prosa ao redor do JSON."""
    limpo = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        inicio, fim = limpo.find("{"), limpo.rfind("}")
        if 0 <= inicio < fim:
            try:
                return json.loads(limpo[inicio : fim + 1])
            except json.JSONDecodeError:
                return None
    return None


def analise_heuristica(falhas: list[dict[str, Any]], motivo_fallback: str) -> dict[str, Any]:
    """Sem modelo disponível: devolve o que é fato do traceback e zero chute de correção."""
    itens = [
        {
            "teste": f["teste"],
            "arquivo": f.get("arquivo"),
            "linha": f.get("linha"),
            "causa_provavel": f"{f['excecao']} levantada em {f.get('arquivo')}:{f.get('linha')}",
            "correcao_sugerida": "(não sugerida — modo heurístico não aplica IA)",
            "confianca": "média",
            "risco": "sem análise semântica; apenas localização do erro",
            "como_validar": "reproduzir localmente com `pytest -v` e inspecionar o frame apontado",
        }
        for f in falhas
    ]
    return {
        "diagnostico": (
            f"Modo heurístico ({motivo_fallback}): localizei as exceções no traceback, "
            "mas não há diagnóstico semântico gerado por IA nesta execução."
        ),
        "falhas": itens,
        "causa_comum": None,
        "o_que_a_ia_nao_pode_saber": ["nenhuma análise generativa foi executada nesta rodada"],
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def analisar(caminho_log: Path, raiz: Path, args: argparse.Namespace) -> tuple[str, dict[str, Any], list[dict[str, Any]], str, str | None, str | None]:
    """Executa o pipeline de análise e devolve (modo, análise, falhas, resumo, endpoint, resposta bruta)."""
    log = caminho_log.read_text(encoding="utf-8", errors="replace")
    resumo = extrair_resumo(log)
    falhas = extrair_falhas(log)
    codigo = contexto_codigo(falhas, raiz)

    modo, endpoint, resposta_bruta = "heurístico", None, None
    analise: dict[str, Any] | None = None

    if args.no_llm:
        motivo = "--no-llm informado"
    else:
        prompt = montar_prompt(falhas, resumo, codigo, caminho_log.name)
        try:
            resultado = chamar_ia(prompt, args.base_url, args.model, args.timeout)
            endpoint, resposta_bruta = resultado["endpoint"], resultado["texto"]
            if resultado["dados"]:
                analise, modo = resultado["dados"], "IA generativa"
            else:
                motivo = "resposta do modelo não era JSON parseável"
        except Exception as erro:  # rede/timeout/formato: o job nunca pode quebrar aqui
            motivo = f"{type(erro).__name__}: {erro}"

    if analise is None:
        analise = analise_heuristica(falhas, motivo)
        resposta_bruta = None

    print(f"[info] {len(falhas)} falha(s) parseadas · resumo do job: {resumo} · modo: {modo}")
    return modo, analise, falhas, resumo, endpoint, resposta_bruta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analisa um log de CI com IA generativa.")
    parser.add_argument("log", help="caminho do log do job (stdout do pytest no pipeline)")
    parser.add_argument("--out", default=None, help="arquivo .md do relatório")
    parser.add_argument("--repo-root", default=".", help="raiz do repositório para ler o código")
    parser.add_argument("--base-url", default=os.environ.get("GENAI_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--model", default=os.environ.get("GENAI_MODEL") or DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--no-llm", action="store_true", help="força o modo heurístico (sem chamar IA)")
    args = parser.parse_args(argv)

    caminho_log = Path(args.log)
    if not caminho_log.exists():
        print(f"[erro] log não encontrado: {caminho_log}", file=sys.stderr)
        return 2

    raiz = Path(args.repo_root)
    modo, analise, falhas, resumo, endpoint, resposta_bruta = analisar(caminho_log, raiz, args)

    relatorio = render_relatorio(
        log_nome=caminho_log.name,
        resumo=resumo,
        falhas=falhas,
        analise=analise,
        modo=modo,
        modelo=args.model if modo == "IA generativa" else f"{args.model} (não utilizado)",
        endpoint=endpoint,
        motivo_fallback=None if modo == "IA generativa" else str(analise.get("diagnostico")),
        resposta_bruta=resposta_bruta,
    )

    destino = Path(args.out) if args.out else Path("reports") / f"analise-{caminho_log.stem}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(relatorio, encoding="utf-8")
    print(f"[ok] relatório salvo em {destino}")

    for item in analise.get("falhas") or []:
        print(f"  - {item.get('teste')}: {str(item.get('causa_provavel', ''))[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


