import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FiTrash2 } from "react-icons/fi";
import { getCatalogo, validarCarrito, type Kit } from "../api";
import { leerCarrito, quitar, setCantidad, type CartItem } from "../cart";

function clp(n: number) {
  return new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(n);
}

export default function Carrito() {
  const [items, setItems] = useState<CartItem[]>([]);
  const [kits, setKits] = useState<Kit[]>([]);
  const [errores, setErrores] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const refresh = () => setItems(leerCarrito());
  useEffect(() => {
    refresh();
    getCatalogo().then(setKits).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (items.length === 0) {
      setTotal(0);
      setErrores([]);
      return;
    }
    setLoading(true);
    validarCarrito(items.map((i) => ({ sku: i.sku, cantidad: i.cantidad })))
      .then((r) => {
        setTotal(r.total);
        setErrores(r.errores);
      })
      .catch((e) => setErrores([String(e.message || e)]))
      .finally(() => setLoading(false));
  }, [items]);

  const stockDe = (sku: string) => kits.find((k) => k.sku === sku)?.stock ?? 0;

  return (
    <>
      <h1>Carro de compras</h1>
      {items.length === 0 ? (
        <p className="empty">El carro está vacío. <Link className="btn" to="/">Volver al catálogo</Link></p>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>Producto</th>
                <th>Precio</th>
                <th>Cantidad</th>
                <th>Subtotal</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.sku}>
                  <td>{i.nombre}<div className="stock">{i.sku} · máx. {stockDe(i.sku)}</div></td>
                  <td>{i.precio != null ? clp(i.precio) : "—"}</td>
                  <td>
                    <input
                      className="qty"
                      type="number"
                      min={1}
                      max={Math.max(1, stockDe(i.sku))}
                      value={i.cantidad}
                      aria-label={`Cantidad de ${i.nombre}`}
                      onChange={(e) => {
                        setCantidad(i.sku, Number(e.target.value), stockDe(i.sku));
                        refresh();
                      }}
                    />
                  </td>
                  <td>{i.precio != null ? clp(i.precio * i.cantidad) : "—"}</td>
                  <td>
                    <button type="button" className="danger" onClick={() => { quitar(i.sku); refresh(); }}>
                      <FiTrash2 /> Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && <p className="muted">Validando stock y precio vigente…</p>}
          {errores.map((e) => <p key={e} className="error" role="alert">{e}</p>)}
          <p className="precio">Total: {clp(total)}</p>
          {loading
            ? <button type="button" disabled>Validando stock…</button>
            : errores.length
              ? <button type="button" disabled>Corrige el carro para pagar</button>
              : <Link className="btn" to="/checkout">Confirmar compra</Link>}
        </>
      )}
    </>
  );
}
