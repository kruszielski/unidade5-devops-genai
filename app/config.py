"""Configurações da aplicação de pedidos.

Os padrões vivem em ``DEFAULTS`` e podem ser sobrescritos por variáveis de
ambiente (prefixo ``PEDIDOS_``) ou por um dicionário de *overrides* — caminho
usado pelos testes para não depender do ambiente.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

# Chaves consumidas por app.pricing e app.inventory. Qualquer renomeação aqui
# precisa ser propagada para os consumidores — foi exatamente isso que quebrou o
# pipeline (ver docs/DECISOES-CORRECAO.md).
DEFAULTS: dict[str, Any] = {
    "aliquota_icms": 0.18,              # usado por app.pricing
    "frete_gratis_acima_de": "300.00",  # limite INCLUSIVO (regra R4)
    "custo_frete_padrao": "25.00",
    "estoque_maximo_reserva": 50,       # usado por app.inventory
}

_ENV_PREFIX = "PEDIDOS_"


def carregar_configuracao(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Monta a configuração efetiva: padrões → variáveis de ambiente → overrides."""
    config: dict[str, Any] = dict(DEFAULTS)

    for chave in list(config):
        valor_env = os.environ.get(f"{_ENV_PREFIX}{chave.upper()}")
        if valor_env is not None:
            config[chave] = valor_env

    if overrides:
        config.update(overrides)

    return config
