import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { crearCheckout, validarCarrito } from "../api";
import { leerCarrito, vaciar } from "../cart";

export default function Checkout() {
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [total, setTotal] = useState(0);
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
    try {
      const r = await crearCheckout({
        comprador_nombre: nombre,
        comprador_email: email,
        items: items.map((i) => ({ sku: i.sku, cantidad: i.cantidad })),
      });
      vaciar();
      window.location.href = r.redirect_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!items.length) {
    return <p>No hay productos para pagar. <Link to="/">Ir al catálogo</Link></p>;
  }

  return (
    <>
      <h1>Confirmar compra</h1>
      <p className="lead">Al continuar se reserva el stock y se abre la pasarela de pago.</p>
      <form onSubmit={onSubmit} className="card" style={{ maxWidth: 480 }}>
        <div className="field">
          <label htmlFor="nombre">Nombre</label>
          <input id="nombre" required value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="email">Correo</label>
          <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <p>Total a pagar: <strong>{total}</strong></p>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit">Pagar</button>
      </form>
    </>
  );
}
