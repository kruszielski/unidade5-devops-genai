"""Testes de app.inventory — reserva de estoque usada como smoke check do deploy."""

from __future__ import annotations

import pytest

from app.config import carregar_configuracao
from app.inventory import reservar


def test_reserva_dentro_do_limite():
    reserva = reservar(carregar_configuracao(), "SKU-42", 10)

    assert reserva == {"sku": "SKU-42", "quantidade": 10, "reservado": True}


def test_reserva_no_teto_configurado_e_permitida():
    config = carregar_configuracao({"estoque_maximo_reserva": 5})

    assert reservar(config, "SKU-42", 5)["quantidade"] == 5


def test_reserva_acima_do_limite_e_recusada():
    config = carregar_configuracao({"estoque_maximo_reserva": 5})

    with pytest.raises(ValueError, match="excede o limite configurado de 5"):
        reservar(config, "SKU-42", 6)


def test_quantidade_zero_e_recusada_antes_de_ler_config():
    with pytest.raises(ValueError, match="maior que zero"):
        reservar(carregar_configuracao(), "SKU-42", 0)


def test_sku_vazio_e_recusado():
    with pytest.raises(ValueError, match="sku do item é obrigatório"):
        reservar(carregar_configuracao(), "   ", 1)
