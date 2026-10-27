import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRetiro, getRetiros, RetiroDetalle, RetiroResumen } from "../api";

const ESTADO: Record<string, string> = {
  pendiente: "Pendiente",
  reportado: "Reportado",
  completo: "Completo",
};

function fmtFecha(iso: string | null) {
  if (!iso) return "s/i";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function Retiros() {
  const [filas, setFilas] = useState<RetiroResumen[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getRetiros().then(setFilas).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div>
      <h1>Retiros de lote</h1>
      <p className="lead">Retiros recibidos de Farma Central y los productos retirados de circulación.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {!filas && !error && <p className="muted">Cargando retiros…</p>}
      {filas && filas.length === 0 && <p className="empty">Aún no se ha recibido ningún retiro.</p>}
      {filas && filas.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Retiro</th>
              <th>Lote</th>
              <th>SKU</th>
              <th>Motivo</th>
              <th>Emitido</th>
              <th>Plazo</th>
              <th>Estado</th>
              <th>Unidades retiradas</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((r) => (
              <tr key={r.id}>
                <td><Link to={`/recalls/${encodeURIComponent(r.id)}`}>{r.id}</Link></td>
                <td><Link to={`/trazabilidad?lote=${encodeURIComponent(r.lote)}`}>{r.lote}</Link></td>
                <td>{r.sku || "s/i"}</td>
                <td>{r.motivo || ""}</td>
                <td>{fmtFecha(r.emitido_en)}</td>
                <td>{fmtFecha(r.plazo)}</td>
                <td>{ESTADO[r.estado] || r.estado}</td>
                <td>{r.unidades_retiradas}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function RetiroDetallePage() {
  const { id = "" } = useParams();
  const [data, setData] = useState<RetiroDetalle | null | undefined>(undefined);
  const [error, setError] = useState("");

  useEffect(() => {
    getRetiro(id).then(setData).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  return (
    <div>
      <p><Link to="/recalls">← Retiros de lote</Link></p>
      {error && <p className="error" role="alert">{error}</p>}
      {data === undefined && !error && <p className="muted">Cargando retiro…</p>}
      {data === null && <p className="empty">Retiro no encontrado.</p>}
      {data && (
        <>
          <h1>Retiro {data.id}</h1>
          <section className="kpi" aria-label="Datos del retiro">
            <Dato etiqueta="Lote retirado" valor={data.lote} />
            <Dato etiqueta="SKU" valor={data.sku || "s/i"} />
            <Dato etiqueta="Motivo" valor={data.motivo || "s/i"} />
            <Dato etiqueta="Emitido" valor={fmtFecha(data.emitido_en)} />
            <Dato etiqueta="Plazo" valor={fmtFecha(data.plazo)} />
            <Dato etiqueta="Reportado" valor={fmtFecha(data.reportado_en)} />
            <Dato etiqueta="Estado" valor={ESTADO[data.estado] || data.estado} />
          </section>

          <h2>Productos retirados de circulación ({data.unidades.length})</h2>
          {data.unidades.length === 0 ? (
            <p className="empty">No había unidades de este lote ni de sus derivados en stock.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>ID del producto</th>
                  <th>Lote</th>
                  <th>Espacio original</th>
                  <th>Cuarentena</th>
                </tr>
              </thead>
              <tbody>
                {data.unidades.map((u) => (
                  <tr key={u.id}>
                    <td>{u.sku}</td>
                    <td><code>{u.id}</code></td>
                    <td>{u.lote}</td>
                    <td>{u.espacio_original || "s/i"}</td>
                    <td>{u.en_cuarentena ? "En cuarentena" : u.estado === "vencida" ? "Vencida" : "Por mover"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Lotes derivados ({data.derivados.length})</h2>
          {data.derivados.length === 0 ? <p className="muted">Sin lotes derivados.</p> : (
            <ul>
              {data.derivados.map((d) => (
                <li key={d.batch}>
                  <Link to={`/trazabilidad?lote=${encodeURIComponent(d.batch)}`}>{d.batch}</Link>
                  {" · "}{d.sku} · generado desde {d.sourceBatch}
                </li>
              ))}
            </ul>
          )}

          <h2>Entregas afectadas ({data.entregas.length})</h2>
          {data.entregas.length === 0 ? <p className="muted">Sin entregas a clientes.</p> : (
            <ul>
              {data.entregas.map((e) => {
                const n = data.notificaciones.find((x) => x.oc_id === e.orderId);
                return (
                  <li key={e.orderId}>
                    OC <code>{e.orderId}</code> · {e.customerName || "s/i"} · {e.productIds.length} unidades
                    {" · "}{n?.enviada_en ? `notificada ${fmtFecha(n.enviada_en)}` : "notificación pendiente"}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div>
      <div className="kpi-label">{etiqueta}</div>
      <div>{valor}</div>
    </div>
  );
}
