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
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState("");

  useEffect(() => {
    getCatalogo()
      .then(setKits)
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  }, []);

  const visibles = kits.filter((k) => {
    const q = filtro.trim().toLowerCase();
    if (!q) return true;
    return k.nombre.toLowerCase().includes(q) || k.sku.toLowerCase().includes(q);
  });

  return (
    <>
      <h1>Kits clínicos</h1>
      <p className="lead">
        Precio vigente de Farma Central y stock real en custodia (sin vencidos ni reservados).
      </p>
      <div className="field" style={{ maxWidth: 360 }}>
        <label htmlFor="filtro">Buscar kit</label>
        <input id="filtro" value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="Nombre o SKU" />
      </div>
      {loading && <p className="muted">Cargando catálogo…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {ok && <p role="status">{ok}</p>}
      <section className="grid">
        {visibles.map((k) => (
          <KitCard key={k.sku} k={k} onOk={setOk} />
        ))}
      </section>
      {!loading && kits.length === 0 && !error && <p className="empty">No hay kits para mostrar.</p>}
      {!loading && kits.length > 0 && visibles.length === 0 && <p className="empty">Ningún kit coincide con “{filtro}”.</p>}
    </>
  );
}

function KitCard({ k, onOk }: { k: Kit; onOk: (s: string) => void }) {
  const [qty, setQty] = useState(1);
  const disabled = k.stock < 1 || k.precio == null;
  return (
    <article className="card">
      {k.imagen ? <img src={k.imagen} alt="" /> : <div className="ph" aria-hidden />}
      <h2 style={{ margin: 0, fontSize: "1.05rem" }}>{k.nombre}</h2>
      <div className="muted">{k.sku}{k.frio ? " · cadena de frío" : ""}</div>
      <div className="precio">{clp(k.precio)}</div>
      <div className="stock">
        {k.stock > 0
          ? `${k.stock} unidades disponibles`
          : "Sin stock local (hay que acondicionar este kit)"}
      </div>
      <div className="row">
        <input
          className="qty"
          type="number"
          min={1}
          max={Math.max(1, k.stock)}
          value={qty}
          disabled={disabled}
          aria-label={`Cantidad de ${k.nombre}`}
          onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            agregarAlCarrito({ sku: k.sku, nombre: k.nombre, cantidad: qty, precio: k.precio }, k.stock);
            onOk(`${k.nombre} × ${qty} en el carro`);
          }}
        >
          <FiPlus /> Agregar
        </button>
      </div>
    </article>
  );
}
