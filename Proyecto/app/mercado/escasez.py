"""Que insumos criticos puede comprar este grupo a Farma Central.

La asignacion es la del enunciado de la Entrega 3 y no cambia durante la
entrega. Un SKU que no esta en la tabla sigue disponible para todos.
"""
from __future__ import annotations

# sku -> grupos que Farma si se lo vende
AUTORIZADOS: dict[str, frozenset[int]] = {
    "EXC-LACTOSA-DC": frozenset({1, 2, 3}),
    "LAM-BLISTER-PVC": frozenset({2, 3, 4}),
    "EXC-SUERO-FISIO": frozenset({3, 4, 5}),
    "SOB-PAPEL-EST": frozenset({4, 5, 6}),
    "FRA-VIDRIO-120": frozenset({5, 6, 7}),
    "VIA-VIDRIO-10": frozenset({6, 7, 1}),
    "EXC-JARABE-BASE": frozenset({7, 1, 2}),
}


class InsumoNoDisponible(Exception):
    """Farma rechazaria la solicitud: este grupo no esta entre los tres autorizados."""

    def __init__(self, sku: str):
        self.sku = sku
        super().__init__(
            f"{sku} no se puede comprar a Farma Central: hay que conseguirlo en el mercado"
        )


def puede_comprar_en_farma(sku: str, grupo: int) -> bool:
    grupos = AUTORIZADOS.get(sku)
    if grupos is None:
        return True
    return int(grupo) in grupos


def debe_conseguir_en_mercado(grupo: int) -> list[str]:
    """Insumos criticos que este grupo no puede pedir a Farma."""
    return sorted(sku for sku, grupos in AUTORIZADOS.items() if int(grupo) not in grupos)


def puede_revender(grupo: int) -> list[str]:
    """Insumos criticos que este grupo si compra a Farma y puede ofrecer de sobra."""
    return sorted(sku for sku, grupos in AUTORIZADOS.items() if int(grupo) in grupos)
