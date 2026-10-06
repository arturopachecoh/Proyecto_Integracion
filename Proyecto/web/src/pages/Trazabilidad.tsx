import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getTrazabilidad } from "../api";

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
  profundidad: number;
};

export default function Trazabilidad() {
  const [params, setParams] = useSearchParams();
  const inicial = params.get("lote") || "";
  const [lote, setLote] = useState(inicial);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  async function buscar(codigo: string) {
    setError("");
    setData(null);
    if (!codigo.trim()) return;
    const r = await getTrazabilidad(codigo.trim());
    if (!r) setError("Lote no encontrado");
    else setData(r);
  }

  useEffect(() => {
    if (inicial) buscar(inicial);
  }, [inicial]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setParams({ lote });
    buscar(lote);
  }

  return (
    <>
      <h1>Visor de trazabilidad</h1>
      <p className="lead">
        Consulta un lote por código o por <code>?lote=</code> en la URL.
        Aguas arriba: insumos hasta Farma u otra distribuidora. Aguas abajo: derivados, entregas y clientes.
      </p>
      <form onSubmit={onSubmit} className="row" style={{ marginBottom: "1rem" }}>
        <input
          name="lote"
          value={lote}
          onChange={(e) => setLote(e.target.value)}
          placeholder="Código de lote"
          aria-label="Código de lote"
        />
        <button type="submit">Buscar</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {data && (
        <>
          <section className="card">
            <h2>{data.lote.codigo}</h2>
            <p>
              SKU {data.lote.sku} · {ORIGEN[data.lote.origen] || data.lote.origen}
              {data.lote.origen_grupo ? ` (grupo ${data.lote.origen_grupo})` : ""}
            </p>
            <p>
              Cantidad inicial {data.lote.cantidad_inicial} · vence {data.lote.vence_en || "s/i"} ·
              conservación {data.conservacion}
            </p>
            <p>
              Espacios actuales:{" "}
              {Object.entries(data.espacios || {}).map(([k, v]) => `${k || "s/e"}:${v}`).join(", ") || "sin unidades en stock"}
            </p>
          </section>
          <h3>Unidades en inventario</h3>
          {(data.unidades_inventario || []).length === 0 ? <p>Ninguna en stock.</p> : (
            <ul>{data.unidades_inventario.map((u: any) => (
              <li key={u.id}>{u.id} · {u.espacio} · {u.estado}{u.vence_en ? ` · vence ${u.vence_en}` : ""}</li>
            ))}</ul>
          )}
          <h3>Aguas arriba</h3>
          <Arbol nodos={data.aguas_arriba || []} />
          <h3>Aguas abajo</h3>
          <Arbol nodos={data.aguas_abajo || []} />
          <h3>Clientes de este lote</h3>
          <Clientes filas={data.clientes || []} />
          <h3>Clientes de lotes derivados</h3>
          <Clientes filas={data.clientes_derivados || []} />
        </>
      )}
    </>
  );
}

function Arbol({ nodos }: { nodos: Nodo[] }) {
  if (!nodos.length) return <p>Sin relaciones registradas.</p>;
  return (
    <div>
      {nodos.map((n) => (
        <div className="node" key={n.codigo} style={{ marginLeft: n.profundidad * 12 }}>
          <Link to={`/trazabilidad?lote=${encodeURIComponent(n.codigo)}`}><strong>{n.codigo}</strong></Link>
          {" · "}{n.sku} · {ORIGEN[n.origen] || n.origen}
          {n.origen_grupo ? ` grupo ${n.origen_grupo}` : ""} · cantidad {n.cantidad_relacion}
        </div>
      ))}
    </div>
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
          {c.unidades[0]?.lote_codigo ? ` (${c.unidades[0].lote_codigo})` : ""}
        </li>
      ))}
    </ul>
  );
}
