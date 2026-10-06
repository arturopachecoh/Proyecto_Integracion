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
    validarCarrito(items.map((i) => ({ sku: i.sku, cantidad: i.cantidad })))
      .then((r) => {
        setTotal(r.total);
        setErrores(r.errores);
      })
      .catch((e) => setErrores([String(e.message || e)]));
  }, [items]);

  const stockDe = (sku: string) => kits.find((k) => k.sku === sku)?.stock ?? 99;

  return (
    <>
      <h1>Carro de compras</h1>
      {items.length === 0 ? (
        <p>El carro está vacío. <Link to="/">Volver al catálogo</Link></p>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>Producto</th>
                <th>Precio</th>
                <th>Cantidad</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.sku}>
                  <td>{i.nombre}<div className="stock">{i.sku}</div></td>
                  <td>{i.precio != null ? clp(i.precio) : "—"}</td>
                  <td>
                    <input
                      className="qty"
                      type="number"
                      min={1}
                      max={stockDe(i.sku)}
                      value={i.cantidad}
                      aria-label={`Cantidad de ${i.nombre}`}
                      onChange={(e) => {
                        setCantidad(i.sku, Number(e.target.value), stockDe(i.sku));
                        refresh();
                      }}
                    />
                  </td>
                  <td>
                    <button type="button" className="danger" onClick={() => { quitar(i.sku); refresh(); }}>
                      <FiTrash2 /> Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {errores.map((e) => <p key={e} className="error" role="alert">{e}</p>)}
          <p className="precio">Total: {clp(total)}</p>
          <Link className="btn" to="/checkout">Confirmar compra</Link>
        </>
      )}
    </>
  );
}
