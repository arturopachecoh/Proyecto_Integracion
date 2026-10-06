import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
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
    fetch("/api/checkout/confirmar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ venta_id: Number(venta), resultado: clave }),
    })
      .then((r) => r.json())
      .then((d) => setDetalle(d.estado ? `Pedido #${d.venta_id} · ${d.estado}` : ""))
      .catch(() => undefined);
  }, [venta, clave]);

  return (
    <>
      <h1>{info.titulo}</h1>
      <p className="lead">{info.texto}</p>
      {detalle && <p>{detalle}</p>}
      <p>
        <Link to="/">Volver al catálogo</Link>
        {" · "}
        <Link to="/carrito">Ir al carro</Link>
        {clave === "exito" && venta ? (
          <>
            {" · "}
            <Link to="/trazabilidad">Ver trazabilidad</Link>
          </>
        ) : null}
      </p>
    </>
  );
}
