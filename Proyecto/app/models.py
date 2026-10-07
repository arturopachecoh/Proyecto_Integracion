"""Modelo de custodia y trazabilidad.

lotes           grupo de unidades que nacio junto (una compra o una fabricacion)
unidades        estado ACTUAL de cada unidad (donde esta, en que estado)
movimientos     historial: todo lo que le paso a cada unidad
solicitudes     compras de insumos y fabricaciones pedidas a Farma Central
consumos        que unidades exactas se usaron en cada fabricacion
lot_relations   genealogia lote↔lote (N:M, materializada al nacer el lote hijo)
ventas          ventas a clientes (portal y, desde E2, otros canales)
venta_items     lineas de la venta con precio vigente al momento de comprar
venta_unidades  que unidades exactas se llevo cada venta
"""
from datetime import datetime

from sqlalchemy import (DateTime, Enum, ForeignKey, Index, Integer, MetaData, String,
                        UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nombres predecibles para indices y restricciones (Alembic los necesita
# para poder modificarlos o borrarlos en migraciones futuras)
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _enum(*valores: str, name: str) -> Enum:
    # native_enum=False: se guarda como texto con una restriccion CHECK.
    # Agregar un valor nuevo despues es mucho mas simple que con ENUM de Postgres.
    return Enum(*valores, name=name, native_enum=False, create_constraint=True, length=20)


ESPACIOS = ("checkIn", "bodega", "cold", "buffer", "packaging", "checkOut", "quarantine")
Fecha = DateTime(timezone=True)


class Solicitud(Base):
    __tablename__ = "solicitudes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(_enum("compra", "fabricacion", name="tipo_solicitud"))
    sku: Mapped[str] = mapped_column(String(40), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    challenge_id: Mapped[str | None] = mapped_column(String(40))
    pedida_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())
    llega_en: Mapped[datetime | None] = mapped_column(Fecha)  # availableAt de la API
    estado: Mapped[str] = mapped_column(
        _enum("pendiente", "recibida", "fallida", name="estado_solicitud"), default="pendiente"
    )

    __table_args__ = (Index("ix_solicitudes_estado_llega_en", "estado", "llega_en"),)


class Lote(Base):
    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)  # L-BLIAMOXI-261004-7F3A
    sku: Mapped[str] = mapped_column(String(40), index=True)
    cantidad_inicial: Mapped[int] = mapped_column(Integer)
    vence_en: Mapped[datetime | None] = mapped_column(Fecha)
    origen: Mapped[str] = mapped_column(
        _enum("farma_central", "distribuidora", "produccion", name="origen_lote")
    )
    origen_grupo: Mapped[int | None] = mapped_column(Integer)  # si vino de otra distribuidora
    # Solicitud que lo genero. Una solicitud genera a lo mas un lote (unique).
    solicitud_id: Mapped[int | None] = mapped_column(ForeignKey("solicitudes.id"), unique=True)
    lote_proveedor: Mapped[str | None] = mapped_column(String(60))  # por si la API entrega "batch"
    creado_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())


class Unidad(Base):
    __tablename__ = "unidades"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # _id de Farma Central
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    sku: Mapped[str] = mapped_column(String(40))
    espacio_actual: Mapped[str | None] = mapped_column(_enum(*ESPACIOS, name="espacio"))
    estado: Mapped[str] = mapped_column(
        _enum("en_stock", "reservada", "consumida", "despachada", "vencida", "cuarentena",
              name="estado_unidad"),
        default="en_stock",
    )
    vence_en: Mapped[datetime | None] = mapped_column(Fecha)
    actualizada_en: Mapped[datetime] = mapped_column(
        Fecha, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_unidades_sku_estado", "sku", "estado"),)


class Venta(Base):
    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(primary_key=True)
    canal: Mapped[str] = mapped_column(String(20), default="portal")  # E2: archivos, colas, texto
    orden_externa_id: Mapped[str | None] = mapped_column(String(60))  # E2: id de orden de compra
    comprador_nombre: Mapped[str | None] = mapped_column(String(120))
    comprador_email: Mapped[str | None] = mapped_column(String(120))
    transaccion_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    estado: Mapped[str] = mapped_column(
        _enum("pendiente_pago", "pagada", "cancelada", "error", name="estado_venta"),
        default="pendiente_pago",
    )
    total: Mapped[int] = mapped_column(Integer, default=0)
    creada_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())
    pagada_en: Mapped[datetime | None] = mapped_column(Fecha)


class VentaUnidad(Base):
    __tablename__ = "venta_unidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    unidad_id: Mapped[str] = mapped_column(ForeignKey("unidades.id"), unique=True)  # se vende una vez
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    estado: Mapped[str] = mapped_column(
        _enum("pendiente", "despachada", name="estado_despacho"), default="pendiente"
    )
    despachada_en: Mapped[datetime | None] = mapped_column(Fecha)


class Consumo(Base):
    __tablename__ = "consumos"

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id"), index=True)
    unidad_id: Mapped[str] = mapped_column(ForeignKey("unidades.id"), unique=True)  # se consume una vez
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)


class LotRelation(Base):
    """Arista N:M: el lote padre se consumo para generar el lote hijo."""

    __tablename__ = "lot_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    child_lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id"), index=True)

    __table_args__ = (
        UniqueConstraint("parent_lote_id", "child_lote_id", name="uq_lot_relations_parent_child"),
    )


class VentaItem(Base):
    __tablename__ = "venta_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    sku: Mapped[str] = mapped_column(String(40))
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[int] = mapped_column(Integer)


class Movimiento(Base):
    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[str] = mapped_column(ForeignKey("unidades.id"), index=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    tipo: Mapped[str] = mapped_column(
        _enum("recepcion", "traslado", "consumo", "generacion", "venta", "despacho",
              "vencimiento", "cuarentena", name="tipo_movimiento")
    )
    desde: Mapped[str | None] = mapped_column(_enum(*ESPACIOS, name="espacio_desde"))
    hacia: Mapped[str | None] = mapped_column(_enum(*ESPACIOS, name="espacio_hacia"))
    fecha: Mapped[datetime] = mapped_column(Fecha, server_default=func.now(), index=True)
    solicitud_id: Mapped[int | None] = mapped_column(ForeignKey("solicitudes.id"))
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"))


__all__ = [
    "Base", "Lote", "Unidad", "Movimiento", "Solicitud", "Consumo",
    "LotRelation", "Venta", "VentaItem", "VentaUnidad",
]
