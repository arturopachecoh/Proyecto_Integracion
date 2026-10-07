import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getLotes, getTrazabilidad, getVentas, type GrupoLotes, type VentaResumen } from "../api";

const ORIGEN: Record<string, string> = {
  farma_central: "Farma Central",
  produccion: "Producido por el grupo",
  distribuidora: "Otra distribuidora",
};

type Nodo = {
  codigo: string;
  sku: string;
  origen: string;
  origen_grupo: number | null;
  cantidad_relacion: number;
  cantidad_inicial?: number;
  profundidad: number;
};

type Entrega = {
  venta_id: number;
  comprador_nombre: string;
  comprador_email: string;
  estado: string;
  transaccion_id: string | null;
  pagada_en: string | null;
  creada_en: string | null;
  unidades: number;
  sku: string;
};

type Data = {
  lote: {
    codigo: string;
    sku: string;
    cantidad_inicial: number;
    vence_en: string | null;
    origen: string;
    origen_grupo: number | null;
  };
  conservacion: string;
  espacios: Record<string, number>;
  estado_unidades: Record<string, number>;
  unidades_producidas: number;
  vence_en_efectivo: string | null;
  unidades_inventario: { id: string; espacio: string | null; estado: string; vence_en: string | null }[];
  aguas_arriba: Nodo[];
  aguas_abajo: Nodo[];
  clientes: any[];
  clientes_derivados: any[];
  entregas: Entrega[];
  consulta_ms?: number;
};

function fmtFecha(iso: string | null) {
  if (!iso) return "s/i";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function tonoOrigen(origen: string) {
  if (origen === "farma_central") return "node-farma";
  if (origen === "distribuidora") return "node-dist";
  return "node-propio";
}

function etiquetaOrigen(n: { origen: string; origen_grupo: number | null }) {
  if (n.origen === "farma_central") return "FARMA CENTRAL";
  if (n.origen === "distribuidora") return `DISTRIBUIDORA ${n.origen_grupo ?? "?"}`;
  return "PROPIO";
}

function resumenEstado(e: Record<string, number>) {
  const partes = [
    e.en_stock ? `${e.en_stock} en stock` : null,
    e.reservada ? `${e.reservada} reservadas` : null,
    e.consumida ? `${e.consumida} consumidas` : null,
    e.despachada ? `${e.despachada} despachadas` : null,
    e.vencida ? `${e.vencida} vencidas` : null,
    e.cuarentena ? `${e.cuarentena} en cuarentena` : null,
  ].filter(Boolean);
  return partes.join(" · ") || "sin unidades registradas";
}

export default function Trazabilidad() {
  const [params, setParams] = useSearchParams();
  const inicial = params.get("lote") || "";
  const [lote, setLote] = useState(inicial);
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [consultaMs, setConsultaMs] = useState<number | null>(null);

  async function buscar(codigo: string) {
    setError("");
    setData(null);
    if (!codigo.trim()) return;
    setLoading(true);
    const t0 = performance.now();
    try {
      const r = await getTrazabilidad(codigo.trim());
      const wall = Math.round(performance.now() - t0);
      if (!r) setError("Lote no encontrado en custodia local.");
      else {
        setData(r);
        setConsultaMs(typeof r.consulta_ms === "number" ? r.consulta_ms : wall);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLote(inicial);
    if (inicial) buscar(inicial);
  }, [inicial]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setParams({ lote: lote.trim() });
  }

  const padres = useMemo(
    () => (data?.aguas_arriba || []).filter((n) => n.profundidad === 1),
    [data],
  );
  const ancestros = useMemo(
    () => (data?.aguas_arriba || []).filter((n) => n.profundidad > 1),
    [data],
  );
  const hijos = useMemo(
    () => (data?.aguas_abajo || []).filter((n) => n.profundidad === 1),
    [data],
  );
  const descendientes = useMemo(
    () => (data?.aguas_abajo || []).filter((n) => n.profundidad > 1),
    [data],
  );

  return (
    <div className="trace">
      <header className="trace-head">
        <div>
          <h1>Trazabilidad de lote</h1>
          <p className="lead">Distribuidora 4 · consulta ascendente y descendente sobre la cadena de custodia</p>
        </div>
        <form onSubmit={onSubmit} className="trace-search">
          <input
            name="lote"
            value={lote}
            onChange={(e) => setLote(e.target.value)}
            placeholder="Código de lote"
            aria-label="Código de lote"
          />
          <button type="submit">Buscar</button>
        </form>
      </header>

      {loading && <p className="muted">Consultando lote…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !data && !error && (
        <p className="empty">Elige un código de la lista o pégalo arriba. También vale <code>?lote=</code> en la URL.</p>
      )}

      {data && (
        <>
          <section className="kpi" aria-label="Datos del lote">
            <Kpi etiqueta="ID de lote" valor={data.lote.codigo} />
            <Kpi etiqueta="SKU" valor={data.lote.sku} />
            <Kpi etiqueta="Unidades producidas" valor={String(data.unidades_producidas)} />
            <Kpi etiqueta="Vencimiento efectivo" valor={fmtFecha(data.vence_en_efectivo)} />
            <Kpi etiqueta="Conservación" valor={data.conservacion === "frio" ? "Refrigerado" : "Ambiente"} />
            <Kpi etiqueta="Estado actual" valor={resumenEstado(data.estado_unidades)} />
            <Kpi etiqueta="Tiempo de consulta" valor={consultaMs != null ? `${consultaMs} ms` : "—"} />
          </section>

          <section className="trace-graph" aria-label="Grafo de custodia">
            <div>
              <h2 className="trace-col-title">Lotes que lo generaron ({padres.length})</h2>
              {padres.length === 0 ? (
                <p className="muted">Origen terminal: {ORIGEN[data.lote.origen] || data.lote.origen}.</p>
              ) : padres.map((n) => (
                <LoteCard key={n.codigo} n={n} />
              ))}
              {ancestros.length > 0 && (
                <>
                  <p className="trace-col-title">Más arriba (recursivo)</p>
                  {ancestros.map((n) => <LoteCard key={n.codigo} n={n} />)}
                </>
              )}
            </div>
            <div className="trace-edges" aria-hidden>⟨</div>
            <div>
              <p className="trace-col-title" style={{ textAlign: "center" }}>Lote consultado</p>
              <article className="lot-card node-consultado">
                <strong>{data.lote.sku}</strong>
                <div className="code">{data.lote.codigo}</div>
                <div className="muted">
                  {data.unidades_producidas} unidades
                  {Object.keys(data.espacios || {}).length
                    ? ` · ${Object.entries(data.espacios).map(([k, v]) => `${k || "s/e"} ${v}`).join(", ")}`
                    : ""}
                </div>
                <div className="muted">{ORIGEN[data.lote.origen]}{data.lote.origen_grupo ? ` ${data.lote.origen_grupo}` : ""}</div>
              </article>
            </div>
            <div className="trace-edges" aria-hidden>⟩</div>
            <div>
              <h2 className="trace-col-title">
                Lotes generados y entregas ({hijos.length} lote{hijos.length === 1 ? "" : "s"} · {data.entregas.length} entrega{data.entregas.length === 1 ? "" : "s"})
              </h2>
              {hijos.map((n) => <LoteCard key={n.codigo} n={n} />)}
              {descendientes.length > 0 && (
                <>
                  <p className="trace-col-title">Más abajo (recursivo)</p>
                  {descendientes.map((n) => <LoteCard key={n.codigo} n={n} />)}
                </>
              )}
              {data.entregas.map((e) => (
                <article className="lot-card node-entrega" key={e.venta_id}>
                  <strong>Despacho / venta</strong>
                  <div className="code">{e.comprador_nombre || "Cliente portal"}</div>
                  <div className="muted">{e.comprador_email}</div>
                  <div className="muted">{e.unidades} u · pedido #{e.venta_id} · {e.estado}</div>
                  <div className="muted">Pagado: {fmtFecha(e.pagada_en || e.creada_en)}</div>
                  {e.transaccion_id && <div className="muted">tx {e.transaccion_id}</div>}
                </article>
              ))}
              {hijos.length === 0 && data.entregas.length === 0 && (
                <p className="muted">Sin derivados ni entregas registradas.</p>
              )}
            </div>
          </section>

          <ul className="legend">
            <li><span className="swatch node-consultado" /> Lote consultado</li>
            <li><span className="swatch node-propio" /> Lote propio o de otra distribuidora</li>
            <li><span className="swatch node-farma" /> Recibido de Farma Central</li>
            <li><span className="swatch node-entrega" /> Entregado a cliente</li>
          </ul>

          <details className="card">
            <summary>Unidades en inventario ({data.unidades_inventario.length})</summary>
            {data.unidades_inventario.length === 0 ? <p>Ninguna en stock o reservada.</p> : (
              <ul>
                {data.unidades_inventario.map((u) => (
                  <li key={u.id}>{u.id} · {u.espacio || "s/e"} · {u.estado}{u.vence_en ? ` · vence ${fmtFecha(u.vence_en)}` : ""}</li>
                ))}
              </ul>
            )}
          </details>
          <details className="card">
            <summary>Clientes de lotes derivados</summary>
            <Clientes filas={data.clientes_derivados || []} />
          </details>
        </>
      )}

      <Explorador
        seleccionado={inicial}
        onElegir={(codigo) => {
          setLote(codigo);
          setParams({ lote: codigo });
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      />
    </div>
  );
}

function Kpi({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div>
      <div className="kpi-label">{etiqueta}</div>
      <div>{valor}</div>
    </div>
  );
}

function LoteCard({ n }: { n: Nodo }) {
  return (
    <Link
      className={`lot-card ${tonoOrigen(n.origen)}`}
      to={`/trazabilidad?lote=${encodeURIComponent(n.codigo)}`}
      aria-label={`Ver lote ${n.codigo}`}
    >
      <strong>{n.sku}</strong>
      <div className="code">{n.codigo}</div>
      <div className="muted">{etiquetaOrigen(n)}</div>
      <div className="muted">{n.cantidad_relacion} u relacionadas</div>
    </Link>
  );
}

function Clientes({ filas }: { filas: any[] }) {
  if (!filas.length) return <p>Sin ventas asociadas.</p>;
  return (
    <ul>
      {filas.map((c) => (
        <li key={c.venta_id}>
          Pedido #{c.venta_id} · {c.comprador_nombre} · {c.comprador_email} · {c.estado}
          {" · "}{c.unidades.length} unidades
          {c.pagada_en ? ` · ${fmtFecha(c.pagada_en)}` : ""}
        </li>
      ))}
    </ul>
  );
}

function Explorador({
  seleccionado,
  onElegir,
}: {
  seleccionado: string;
  onElegir: (codigo: string) => void;
}) {
  const [q, setQ] = useState("");
  const [grupos, setGrupos] = useState<GrupoLotes[]>([]);
  const [ventas, setVentas] = useState<VentaResumen[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      getLotes(q).then(setGrupos).catch((e) => setErr(String(e.message || e)));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    getVentas().then(setVentas).catch(() => undefined);
  }, []);

  const pagadas = ventas.filter((v) => v.estado === "pagada" && v.lotes.length);

  return (
    <div className="explorer">
      <section className="card">
        <h2>Códigos de lote (kits)</h2>
        <p className="muted">No hace falta memorizarlos: filtra por SKU o código y pulsa para consultar.</p>
        <div className="field">
          <label htmlFor="filtro-lote">Filtrar</label>
          <input
            id="filtro-lote"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="KIT-DERMATO o L-KIT-…"
          />
        </div>
        {err && <p className="error">{err}</p>}
        <div className="sku-list">
          {grupos.map((g) => (
            <div key={g.sku} className="sku-group">
              <div className="sku-head">
                <strong>{g.sku}</strong>
                <span className="muted">{g.lotes.length} lote{g.lotes.length === 1 ? "" : "s"}{g.hay_mas ? "+" : ""}</span>
              </div>
              <div className="chip-row">
                {g.lotes.map((l) => (
                  <button
                    key={l.codigo}
                    type="button"
                    className={`chip${seleccionado === l.codigo ? " chip-on" : ""}`}
                    onClick={() => onElegir(l.codigo)}
                    title={`${l.en_stock} en stock · ${l.despachada} despachadas`}
                  >
                    <code>{l.codigo}</code>
                    <span className="muted">{l.en_stock} en stock · {l.despachada} desp.</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
          {grupos.length === 0 && <p className="muted">Ningún kit coincide.</p>}
        </div>
      </section>

      <section className="card">
        <h2>Transacciones recientes</h2>
        <p className="muted">Pedidos pagados y el lote que salió. Bitácora completa en Pedidos.</p>
        {pagadas.length === 0 ? (
          <p className="muted">Todavía no hay ventas pagadas.</p>
        ) : (
          <ul className="tx-list">
            {pagadas.slice(0, 8).map((v) => (
              <li key={v.id}>
                <div>
                  <strong>Pedido #{v.id}</strong>
                  <div className="muted">{v.comprador_nombre} · {fmtFecha(v.pagada_en || v.creada_en)}</div>
                  {v.transaccion_id && <div className="mono muted">tx {v.transaccion_id}</div>}
                </div>
                <div className="chip-row">
                  {v.lotes.map((l) => (
                    <button key={l.codigo} type="button" className="chip" onClick={() => onElegir(l.codigo)}>
                      <code>{l.codigo}</code>
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
        <Link className="btn ghost" to="/pedidos">Ver todos los pedidos</Link>
      </section>
    </div>
  );
}
