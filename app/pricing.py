"""Cálculo de total de pedido (subtotal, desconto, imposto e frete).

Regras de negócio:

* **R1** — ``subtotal = Σ (preço_unitário × quantidade)``.
* **R2** — o desconto do cupom incide sobre o subtotal; cupom inexistente é erro.
* **R3** — o imposto (ICMS) incide sobre ``subtotal − desconto``.
* **R4** — o frete é gratuito quando o valor líquido **atinge** o limite da
  configuração. O limite é **inclusivo**: um pedido de exatamente R$ 300,00 tem
  frete grátis.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping, Sequence

from app.config import carregar_configuracao

CENTAVOS = Decimal("0.01")

#: cupom → fração de desconto sobre o subtotal
CUPONS: dict[str, Decimal] = {
    "BEMVINDO10": Decimal("0.10"),
    "BLACK20": Decimal("0.20"),
}


def _decimal(valor: Any) -> Decimal:
    """Converte int/float/str em Decimal sem os ruídos do binário de ``float``."""
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def calcular_total(
    itens: Sequence[Mapping[str, Any]],
    *,
    cupom: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Decimal]:
    """Calcula o total de um pedido e devolve cada componente quantizado em centavos."""
    cfg = carregar_configuracao() if config is None else config

    if not itens:
        raise ValueError("O pedido precisa de ao menos um item.")

    subtotal = Decimal("0.00")
    for linha in itens:
        sku = str(linha.get("sku", "")).strip()
        quantidade = int(linha.get("quantidade", 0))
        if not sku:
            raise ValueError("Todo item de pedido precisa de um sku.")
        if quantidade <= 0:
            raise ValueError(f"A quantidade do item {sku!r} deve ser maior que zero.")
        subtotal += _decimal(linha["preco_unitario"]) * quantidade

    desconto = Decimal("0.00")
    if cupom:
        fracao = CUPONS.get(cupom.strip().upper())
        if fracao is None:
            raise ValueError(f"O cupom {cupom!r} não é válido.")
        desconto = subtotal * fracao

    liquido = subtotal - desconto                       # R2/R3
    imposto = liquido * _decimal(cfg["aliquota_icms"])   # R3

    limite_frete_gratis = _decimal(cfg["frete_gratis_acima_de"])
    if liquido > limite_frete_gratis:                    # BUG intencional: limite exclusivo
        frete = Decimal("0.00")
    else:
        frete = _decimal(cfg["custo_frete_padrao"])

    total = liquido + imposto + frete

    return {
        "subtotal": subtotal.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        "desconto": desconto.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        "liquido": liquido.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        "imposto": imposto.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        "frete": frete.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        "total": total.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
    }
