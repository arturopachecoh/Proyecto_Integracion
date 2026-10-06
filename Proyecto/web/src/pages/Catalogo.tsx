import { useEffect, useState } from "react";
import { FiPlus } from "react-icons/fi";
import { getCatalogo, type Kit } from "../api";
import { agregarAlCarrito } from "../cart";

function clp(n: number | null) {
  if (n == null) return "Precio no disponible";
  return new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(n);
}

export default function Catalogo() {
  const [kits, setKits] = useState<Kit[]>([]);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  useEffect(() => {
    getCatalogo().then(setKits).catch((e) => setError(String(e.message || e)));
  }, []);

  return (
    <>
      <h1>Kits clínicos</h1>
      <p className="lead">Precio vigente del mercado y stock real en custodia. Los vencidos y reservados no se ofrecen.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {ok && <p className="lead">{ok}</p>}
      <section className="grid">
        {kits.map((k) => (
          <article className="card" key={k.sku}>
            {k.imagen ? <img src={k.imagen} alt="" /> : <div style={{ height: 80, background: "#eef3f0", borderRadius: 8 }} />}
            <h2 style={{ margin: 0, fontSize: "1.05rem" }}>{k.nombre}</h2>
            <div className="muted">{k.sku}{k.frio ? " · cadena de frío" : ""}</div>
            <div className="precio">{clp(k.precio)}</div>
            <div className="stock">{k.stock} unidades disponibles</div>
            <button
              type="button"
              disabled={k.stock < 1 || k.precio == null}
              onClick={() => {
                agregarAlCarrito({ sku: k.sku, nombre: k.nombre, cantidad: 1, precio: k.precio }, k.stock);
                setOk(`${k.nombre} agregado al carro`);
              }}
            >
              <FiPlus /> Agregar al carro
            </button>
          </article>
        ))}
      </section>
      {kits.length === 0 && !error && <p>No hay kits para mostrar.</p>}
    </>
  );
}
