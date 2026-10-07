import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getVentas, type VentaResumen } from "../api";

function fmtFecha(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function clp(n: number) {
  return new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(n);
}

export default function Pedidos() {
  const [ventas, setVentas] = useState<VentaResumen[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getVentas()
      .then(setVentas)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <h1>Pedidos y transacciones</h1>
      <p className="lead">
        Bitácora local de checkouts. Cada pedido pagado enlaza al lote FEFO que salió.
      </p>
      {loading && <p className="muted">Cargando pedidos…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && ventas.length === 0 && (
        <p className="empty">Aún no hay pedidos. <Link className="btn" to="/">Ir al catálogo</Link></p>
      )}
      {ventas.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Estado</th>
                <th>Comprador</th>
                <th>Total</th>
                <th>Lotes</th>
                <th>Transacción</th>
                <th>Fecha</th>
              </tr>
            </thead>
            <tbody>
              {ventas.map((v) => (
                <tr key={v.id}>
                  <td>{v.id}</td>
                  <td><span className={`pill estado-${v.estado}`}>{v.estado}</span></td>
                  <td>
                    {v.comprador_nombre || "—"}
                    <div className="muted">{v.comprador_email}</div>
                  </td>
                  <td>{clp(v.total || 0)}</td>
                  <td>
                    {v.lotes.length === 0 ? (
                      <span className="muted">—</span>
                    ) : (
                      <div className="chip-row">
                        {v.lotes.map((l) => (
                          <Link
                            key={l.codigo}
                            className="btn ghost btn-sm"
                            to={`/trazabilidad?lote=${encodeURIComponent(l.codigo)}`}
                          >
                            {l.codigo}
                          </Link>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="mono">{v.transaccion_id || "—"}</td>
                  <td>{fmtFecha(v.pagada_en || v.creada_en)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
