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
ordenes_compra  OC recibidas por sFTP y Pub/Sub, y lo que se decidio con cada una
archivos_sftp   archivos de la casilla sFTP ya leidos
salud_componentes  ultima ejecucion correcta y ultimo error de cada pieza de pedidos
"""
from datetime import datetime

from sqlalchemy import (JSON, DateTime, Enum, ForeignKey, Index, Integer, MetaData, String,
                        Text, UniqueConstraint, func)
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
        _enum("pendiente_pago", "pagada", "cancelada", "error", "orden_compra",
              name="estado_venta"),
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


ESTADOS_OC = ("nueva", "aceptando", "aceptada", "rechazando", "rechazada",
              "cumplida", "vencida", "descartada")


class OrdenCompra(Base):
    """OC recibida. La clave primaria es el id de la OC: una OC repetida por
    cualquier canal no entra dos veces."""

    __tablename__ = "ordenes_compra"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    canal: Mapped[str] = mapped_column(_enum("sftp", "pubsub", "mensajeria", name="canal_oc"))
    origen_ref: Mapped[str | None] = mapped_column(String(255))  # archivo o id del mensaje
    sku: Mapped[str | None] = mapped_column(String(50), index=True)
    cantidad: Mapped[int | None] = mapped_column(Integer)
    vencimiento: Mapped[datetime | None] = mapped_column(Fecha)
    cliente: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(_enum(*ESTADOS_OC, name="estado_oc"), default="nueva")
    estado_remoto: Mapped[str | None] = mapped_column(String(20))
    despachado_remoto: Mapped[int] = mapped_column(Integer, default=0)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), unique=True)
    decision: Mapped[dict | None] = mapped_column(JSON)  # numeros vistos y motivo
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    recibida_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())
    decidida_en: Mapped[datetime | None] = mapped_column(Fecha)
    actualizada_en: Mapped[datetime] = mapped_column(
        Fecha, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_ordenes_compra_estado_vencimiento", "estado", "vencimiento"),)


class ArchivoSftp(Base):
    """Archivo de la casilla ya leido. La casilla puede seguir mostrandolo."""

    __tablename__ = "archivos_sftp"

    nombre: Mapped[str] = mapped_column(String(255), primary_key=True)
    oc_id: Mapped[str | None] = mapped_column(String(40))  # None si el archivo era invalido
    error: Mapped[str | None] = mapped_column(Text)
    leido_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())


class SaludComponente(Base):
    __tablename__ = "salud_componentes"

    nombre: Mapped[str] = mapped_column(String(40), primary_key=True)
    ultimo_ok: Mapped[datetime | None] = mapped_column(Fecha)
    ultimo_error_en: Mapped[datetime | None] = mapped_column(Fecha)
    ultimo_error: Mapped[str | None] = mapped_column(Text)


class Mensaje(Base):
    """Mensaje del canal de mensajeria. La clave es el messageId: un mensaje
    repetido no se procesa dos veces. Guarda que texto se interpreto, que
    respondio el modelo y que decidio el sistema, para revisar cada decision."""

    __tablename__ = "mensajes"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # messageId
    remitente: Mapped[str | None] = mapped_column(String(160))
    telefono: Mapped[str | None] = mapped_column(String(40))
    texto: Mapped[str] = mapped_column(Text, default="")
    recibido_en: Mapped[datetime] = mapped_column(Fecha)  # receivedAt del mensaje
    estado: Mapped[str] = mapped_column(
        _enum("pendiente", "respondiendo", "pedido", "descartado", "sin_respuesta",
              name="estado_mensaje"),
        default="pendiente",
    )
    interpretacion: Mapped[dict | None] = mapped_column(JSON)  # salida cruda del modelo
    decision: Mapped[dict | None] = mapped_column(JSON)  # lo que decidio el sistema y por que
    respuesta: Mapped[dict | None] = mapped_column(JSON)  # cuerpo enviado a la plataforma
    oc_id: Mapped[str | None] = mapped_column(String(40))
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    llegado_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        Fecha, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_mensajes_estado_recibido_en", "estado", "recibido_en"),)


class Retiro(Base):
    """Retiro de lote (recall) emitido por Farma Central."""

    __tablename__ = "retiros"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)  # recallId
    lote: Mapped[str] = mapped_column(String(60))  # codigo del lote retirado (batch)
    sku: Mapped[str | None] = mapped_column(String(50))
    motivo: Mapped[str | None] = mapped_column(Text)
    emitido_en: Mapped[datetime | None] = mapped_column(Fecha)
    plazo: Mapped[datetime | None] = mapped_column(Fecha)
    estado: Mapped[str] = mapped_column(
        _enum("pendiente", "reportado", "completo", name="estado_retiro"), default="pendiente"
    )
    reporte: Mapped[dict | None] = mapped_column(JSON)  # ultimo reporte enviado
    reportado_en: Mapped[datetime | None] = mapped_column(Fecha)
    completado_en: Mapped[datetime | None] = mapped_column(Fecha)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    recibido_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())


class RetiroUnidad(Base):
    """Unidad retirada de circulacion por un retiro (lo que muestra /recalls)."""

    __tablename__ = "retiro_unidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    retiro_id: Mapped[str] = mapped_column(ForeignKey("retiros.id"), index=True)
    unidad_id: Mapped[str] = mapped_column(ForeignKey("unidades.id"))
    sku: Mapped[str] = mapped_column(String(40))
    lote_codigo: Mapped[str] = mapped_column(String(60))
    espacio_original: Mapped[str | None] = mapped_column(String(20))
    en_cuarentena: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (UniqueConstraint("retiro_id", "unidad_id", name="uq_retiro_unidades_retiro_unidad"),)


class RetiroNotificacion(Base):
    """Notificacion enviada a un cliente por una OC afectada (una por OC y retiro)."""

    __tablename__ = "retiro_notificaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    retiro_id: Mapped[str] = mapped_column(ForeignKey("retiros.id"), index=True)
    oc_id: Mapped[str] = mapped_column(String(40))
    cuerpo: Mapped[dict] = mapped_column(JSON)
    enviada_en: Mapped[datetime | None] = mapped_column(Fecha)

    __table_args__ = (UniqueConstraint("retiro_id", "oc_id", name="uq_retiro_notificaciones_retiro_oc"),)


__all__ = [
    "Base", "Lote", "Unidad", "Movimiento", "Solicitud", "Consumo",
    "LotRelation", "Venta", "VentaItem", "VentaUnidad",
    "OrdenCompra", "ArchivoSftp", "SaludComponente", "ESTADOS_OC",
    "Mensaje", "Retiro", "RetiroUnidad", "RetiroNotificacion",
]
