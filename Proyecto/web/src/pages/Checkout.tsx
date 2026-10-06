import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { crearCheckout, validarCarrito } from "../api";
import { leerCarrito, vaciar } from "../cart";

function clp(n: number) {
  return new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(n);
}

export default function Checkout() {
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [total, setTotal] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const items = leerCarrito();

  useEffect(() => {
    if (!items.length) return;
    validarCarrito(items.map((i) => ({ sku: i.sku, cantidad: i.cantidad })))
      .then((r) => {
        setTotal(r.total);
        if (!r.ok) setError(r.errores.join(" · "));
      })
      .catch((e) => setError(String(e.message || e)));
  }, [items.length]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      sessionStorage.setItem("d4-carrito-backup", JSON.stringify(items));
      const r = await crearCheckout({
        comprador_nombre: nombre,
        comprador_email: email,
        items: items.map((i) => ({ sku: i.sku, cantidad: i.cantidad })),
      });
      vaciar();
      window.location.href = r.redirect_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setEnviando(false);
    }
  }

  if (!items.length) {
    return <p className="empty">No hay productos para pagar. <Link to="/">Ir al catálogo</Link></p>;
  }

  return (
    <>
      <h1>Confirmar compra</h1>
      <p className="lead">
        Se reserva stock FEFO, se crea la sesión en Integrapay y te redirigimos a la pasarela.
        En Entrega 1 ~20% de los pagos fallan (error simulado).
      </p>
      <ul className="muted">
        {items.map((i) => (
          <li key={i.sku}>{i.nombre} × {i.cantidad}{i.precio != null ? ` · ${clp(i.precio * i.cantidad)}` : ""}</li>
        ))}
      </ul>
      <form onSubmit={onSubmit} className="card" style={{ maxWidth: 480 }}>
        <div className="field">
          <label htmlFor="nombre">Nombre</label>
          <input id="nombre" required autoComplete="name" value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="email">Correo</label>
          <input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <p>Total a pagar: <strong>{clp(total)}</strong></p>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={enviando || Boolean(error)}>{enviando ? "Abriendo pasarela…" : "Pagar"}</button>
      </form>
    </>
  );
}
