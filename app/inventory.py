"""Reserva de estoque.

A função é chamada pelo pipeline de deploy como *smoke check* pós-migração, então
uma quebra aqui derruba o job de testes do CI mesmo sem mudança no pricing.
"""

from __future__ import annotations

from typing import Any, Mapping


def reservar(
    config: Mapping[str, Any],
    sku: str,
    quantidade: int,
) -> dict[str, Any]:
    """Reserva ``quantidade`` unidades de ``sku``, respeitando o teto configurado.

    Validações na ordem: sku → quantidade → limite configurado. O limite vem da
    configuração para que a área de operações ajuste sem deploy.
    """
    if not sku or not str(sku).strip():
        raise ValueError("O sku do item é obrigatório.")

    quantidade = int(quantidade)
    if quantidade <= 0:
        raise ValueError(f"A quantidade reservada deve ser maior que zero (recebi {quantidade}).")

    limite = int(config["estoque_maximo_reserva"])
    if quantidade > limite:
        raise ValueError(f"Reserva de {quantidade} excede o limite configurado de {limite}.")

    return {"sku": str(sku).strip(), "quantidade": quantidade, "reservado": True}
