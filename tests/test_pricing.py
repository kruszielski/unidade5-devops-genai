"""Testes de app.pricing — contrato da regra de total do pedido."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing import calcular_total

CONFIG_PADRAO = {
    "aliquota_icms": 0.18,
    "frete_gratis_acima_de": "300.00",
    "custo_frete_padrao": "25.00",
}


def item(sku="SKU-1", preco="100.00", quantidade=1):
    return {"sku": sku, "preco_unitario": preco, "quantidade": quantidade}


def test_pedido_pequeno_paga_frete_e_imposto():
    totais = calcular_total([item(preco="100.00")], config=CONFIG_PADRAO)

    assert totais["subtotal"] == Decimal("100.00")
    assert totais["imposto"] == Decimal("18.00")
    assert totais["frete"] == Decimal("25.00")
    assert totais["total"] == Decimal("143.00")


def test_cupom_desconta_antes_de_calcular_imposto():
    totais = calcular_total([item(preco="100.00", quantidade=1)], cupom="BEMVINDO10", config=CONFIG_PADRAO)

    assert totais["desconto"] == Decimal("10.00")
    assert totais["liquido"] == Decimal("90.00")
    assert totais["imposto"] == Decimal("16.20")   # R3: imposto sobre o líquido
    assert totais["total"] == Decimal("131.20")


def test_frete_gratis_acima_do_limite():
    totais = calcular_total([item(preco="150.00", quantidade=3)], config=CONFIG_PADRAO)

    assert totais["liquido"] == Decimal("450.00")
    assert totais["frete"] == Decimal("0.00")
    assert totais["total"] == Decimal("531.00")


def test_frete_gratis_no_limite_exato():
    """R4 é limite inclusivo: R$ 300,00 líquidos já têm frete grátis."""
    totais = calcular_total([item(preco="300.00")], config=CONFIG_PADRAO)

    assert totais["liquido"] == Decimal("300.00")
    assert totais["frete"] == Decimal("0.00")
    assert totais["total"] == Decimal("354.00")


def test_cupom_inexistente_e_erro_claro():
    with pytest.raises(ValueError, match="não é válido"):
        calcular_total([item()], cupom="NAOEXISTE", config=CONFIG_PADRAO)


def test_quantidade_nao_positiva_e_recusada():
    with pytest.raises(ValueError, match="maior que zero"):
        calcular_total([item(quantidade=0)], config=CONFIG_PADRAO)


def test_pedido_vazio_e_recusado():
    with pytest.raises(ValueError, match="ao menos um item"):
        calcular_total([], config=CONFIG_PADRAO)
