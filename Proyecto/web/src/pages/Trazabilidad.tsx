import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getTrazabilidad } from "../api";

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
      <p className="lead">Consulta un lote por su código. Aguas arriba son los insumos; aguas abajo, los derivados y las ventas.</p>
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
            <p>SKU {data.lote.sku} · origen {data.lote.origen}{data.lote.origen_grupo ? ` (grupo ${data.lote.origen_grupo})` : ""}</p>
            <p>Cantidad inicial {data.lote.cantidad_inicial} · vence {data.lote.vence_en || "s/i"} · conservación {data.conservacion}</p>
            <p>Espacios: {Object.entries(data.espacios || {}).map(([k, v]) => `${k || "s/e"}:${v}`).join(", ") || "sin unidades en stock"}</p>
          </section>
          <h3>Unidades en inventario</h3>
          {(data.unidades_inventario || []).length === 0 ? <p>Ninguna en stock.</p> : (
            <ul>{data.unidades_inventario.map((u: any) => (
              <li key={u.id}>{u.id} · {u.espacio} · {u.estado}</li>
            ))}</ul>
          )}
          <h3>Aguas arriba</h3>
          <Arbol nodos={data.aguas_arriba || []} />
          <h3>Aguas abajo</h3>
          <Arbol nodos={data.aguas_abajo || []} />
          <h3>Clientes</h3>
          {(data.clientes || []).length === 0 ? <p>Sin ventas asociadas a este lote.</p> : (
            <ul>
              {data.clientes.map((c: any) => (
                <li key={c.venta_id}>
                  Pedido #{c.venta_id} · {c.comprador_nombre} · {c.comprador_email} · {c.estado} · {c.unidades.length} unidades
                </li>
              ))}
            </ul>
          )}
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
          <strong>{n.codigo}</strong> · {n.sku} · {n.origen}
          {n.origen_grupo ? ` grupo ${n.origen_grupo}` : ""} · consumió/generó {n.cantidad_relacion}
        </div>
      ))}
    </div>
  );
}
