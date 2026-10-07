import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { confirmarCheckout, type LoteVenta } from "../api";
import { guardarCarrito } from "../cart";

const MAP: Record<string, "exito" | "cancelado" | "error"> = {
  exito: "exito",
  success: "exito",
  cancelado: "cancelado",
  cancelled: "cancelado",
  cancel: "cancelado",
  error: "error",
};

const COPY = {
  exito: {
    titulo: "Pago exitoso",
    texto: "Registramos tu pedido. Las unidades concretas quedaron asociadas a tu compra y transacción.",
  },
  cancelado: {
    titulo: "Pago cancelado",
    texto: "No se cobró nada. El stock reservado se liberó; restauramos tu carro si lo tenías.",
  },
  error: {
    titulo: "Error de pago",
    texto: "La pasarela no pudo completar la transacción (en E1 ocurre cerca del 20% de las veces). Inténtalo de nuevo.",
  },
};

export default function Pago() {
  const { estado = "error" } = useParams();
  const [params] = useSearchParams();
  const venta = params.get("venta");
  const [detalle, setDetalle] = useState("");
  const [lotes, setLotes] = useState<LoteVenta[]>([]);
  const [tx, setTx] = useState<string | null>(null);
  const clave = MAP[estado] || "error";
  const info = COPY[clave];

  useEffect(() => {
    if (clave !== "exito") {
      try {
        const raw = sessionStorage.getItem("d4-carrito-backup");
        if (raw) {
          guardarCarrito(JSON.parse(raw));
          sessionStorage.removeItem("d4-carrito-backup");
        }
      } catch {
        /* ignore */
      }
    } else {
      sessionStorage.removeItem("d4-carrito-backup");
    }
    if (!venta) return;
    confirmarCheckout(Number(venta), clave)
      .then((d) => {
        setDetalle(d.estado ? `Pedido #${d.venta_id} · ${d.estado}` : "");
        setLotes(d.lotes || []);
        setTx(d.transaccion_id || null);
      })
      .catch(() => undefined);
  }, [venta, clave]);

  const primerLote = lotes[0]?.codigo;

  return (
    <>
      <h1>{info.titulo}</h1>
      <p className="lead">{info.texto}</p>
      {detalle && <p>{detalle}</p>}
      {tx && <p className="muted">Transacción Integrapay: <code>{tx}</code></p>}

      {clave === "exito" && lotes.length > 0 && (
        <section className="card" style={{ maxWidth: 560, marginBottom: "1rem" }}>
          <strong>Lotes de este pedido</strong>
          <p className="muted" style={{ margin: 0 }}>
            Usa estos códigos en el visor de trazabilidad (no hace falta memorizarlos).
          </p>
          <ul className="lote-list">
            {lotes.map((l) => (
              <li key={l.codigo}>
                <span><code>{l.codigo}</code> · {l.sku}</span>
                <Link className="btn" to={`/trazabilidad?lote=${encodeURIComponent(l.codigo)}`}>
                  Ver trazabilidad
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="actions">
        <Link className="btn" to="/">Volver al catálogo</Link>
        <Link className="btn ghost" to="/carrito">Ir al carro</Link>
        <Link className="btn ghost" to="/pedidos">Ver pedidos</Link>
        {clave === "exito" && venta ? (
          <Link
            className="btn ghost"
            to={primerLote ? `/trazabilidad?lote=${encodeURIComponent(primerLote)}` : "/trazabilidad"}
          >
            {primerLote ? `Trazabilidad ${primerLote}` : "Ver trazabilidad"}
          </Link>
        ) : null}
      </div>
    </>
  );
}
