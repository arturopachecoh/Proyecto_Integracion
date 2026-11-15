"""Tablas del mercado. No son tablas de custodia: las unidades las escribe custodia.

id es el offerId de Farma cuando ya se conoce. Antes del POST puede ser
`pend-...`: al confirmarse se renombra y la FK de oferta_unidades tiene
ON UPDATE CASCADE.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, _enum

Fecha = DateTime(timezone=True)


class OfertaMercado(Base):
    __tablename__ = "ofertas_mercado"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    side: Mapped[str] = mapped_column(_enum("sell", "buy", name="side_oferta"))
    sku: Mapped[str] = mapped_column(String(40), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(
        _enum("publicando", "abierta", "aceptando", "cerrada", "expirada",
              "cancelada", "cancelando", name="estado_oferta"),
        default="publicando",
    )
    order_id: Mapped[str | None] = mapped_column(String(40))
    contraparte_grupo: Mapped[int | None] = mapped_column(Integer)
    rol: Mapped[str] = mapped_column(_enum("vendedor", "comprador", name="rol_oferta"))
    # Unidades de una compra ya atribuidas a esta oferta al llegar a la bodega.
    recibidas: Mapped[int] = mapped_column(Integer, default=0)
    publicada_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        Fecha, server_default=func.now(), onupdate=func.now()
    )


class OfertaUnidad(Base):
    """Unidad apartada por una oferta de venta abierta. Una unidad, una oferta."""

    __tablename__ = "oferta_unidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    oferta_id: Mapped[str] = mapped_column(ForeignKey("ofertas_mercado.id", onupdate="CASCADE",
                                                      ondelete="CASCADE"), index=True)
    unidad_id: Mapped[str] = mapped_column(ForeignKey("unidades.id"), unique=True)


class FaltanteMercado(Base):
    """Desde cuando falta un insumo. Sobrevive a un reinicio del worker."""

    __tablename__ = "mercado_faltantes"

    sku: Mapped[str] = mapped_column(String(40), primary_key=True)
    desde: Mapped[datetime] = mapped_column(Fecha)
