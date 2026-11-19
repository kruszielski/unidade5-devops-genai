"""Renderização do relatório de análise (evidência publicada como artefato do CI)."""

from __future__ import annotations

import datetime as dt
from typing import Any

CHECKLIST_VALIDACAO = """- [ ] Reproduzi a falha localmente antes de mexer em qualquer coisa (`pytest -v`).
- [ ] A correção ataca a **causa-raiz**, não o sintoma (não alterei teste para "passar").
- [ ] Rodei a suíte completa depois do patch e comparei com o resumo anterior.
- [ ] Confirmei com o dono do produto se a sugestão muda regra de negócio ou contrato público.
- [ ] Verifiquei se a correção não esconde um problema de ambiente/configuração fora do repo.
- [ ] Registrei no PR o que foi sugestão da IA e o que foi decisão minha."""


def render_relatorio(
    *,
    log_nome: str,
    resumo: str,
    falhas: list[dict[str, Any]],
    analise: dict[str, Any],
    modo: str,
    modelo: str,
    endpoint: str | None,
    motivo_fallback: str | None,
    resposta_bruta: str | None,
) -> str:
    agora = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    linhas: list[str] = [
        f"# Análise GenAI do pipeline — `{log_nome}`",
        "",
        f"- **Executado em:** {agora}",
        f"- **Modo:** {modo}",
        f"- **Modelo / endpoint:** `{modelo}` · `{endpoint or '—'}`",
        f"- **Resumo do job (pytest):** {resumo}",
        f"- **Falhas parseadas no log:** {len(falhas)}",
    ]
    if motivo_fallback:
        linhas.append(f"- **Motivo do fallback:** {motivo_fallback}")

    linhas += [
        "",
        "## 1. Fatos extraídos do log (parse determinístico)",
        "",
        "| Teste | Arquivo:linha | Exceção | Mensagem |",
        "| --- | --- | --- | --- |",
    ]
    for falha in falhas:
        local = f"{falha.get('arquivo') or '?'}:{falha.get('linha') or '?'}"
        mensagem = (falha.get("mensagem") or "").replace("|", "\\|")[:120]
        linhas.append(f"| `{falha['teste']}` | `{local}` | `{falha['excecao']}` | {mensagem} |")

    linhas += [
        "",
        "## 2. Diagnóstico gerado pela IA generativa",
        "",
        f"**Diagnóstico:** {analise.get('diagnostico')}",
        "",
    ]
    if analise.get("causa_comum"):
        linhas += [f"**Causa comum identificada:** {analise['causa_comum']}", ""]

    for i, item in enumerate(analise.get("falhas") or [], start=1):
        linhas += [
            f"### 2.{i} `{item.get('teste', '?')}`",
            "",
            f"- **Onde:** `{item.get('arquivo', '?')}:{item.get('linha', '?')}`",
            f"- **Causa provável:** {item.get('causa_provavel', '—')}",
            f"- **Confiança declarada:** {item.get('confianca', '—')}",
            f"- **Risco da mudança:** {item.get('risco', '—')}",
            f"- **Como validar:** {item.get('como_validar', '—')}",
            "",
            "Correção sugerida:",
            "",
            "```python",
            str(item.get("correcao_sugerida", "—")).strip(),
            "```",
            "",
        ]

    lacunas = analise.get("o_que_a_ia_nao_pode_saber") or []
    linhas += ["## 3. Limites do que foi analisado automaticamente", ""]
    linhas += [f"- {l}" for l in lacunas] if lacunas else ["- (o modelo não apontou lacunas)"]

    linhas += ["", "## 4. Checklist de validação humana antes de aplicar qualquer correção", "", CHECKLIST_VALIDACAO]

    if resposta_bruta:
        linhas += ["", "## 5. Resposta bruta do modelo (auditoria)", "", "```text", resposta_bruta.strip(), "```"]

    return "\n".join(linhas) + "\n"
