export type Kit = {
  sku: string;
  nombre: string;
  imagen: string | null;
  precio: number | null;
  stock: number;
  frio: boolean;
};

export type LineaCarrito = {
  sku: string;
  nombre: string;
  cantidad: number;
  stock: number;
  precio: number;
  subtotal: number;
};

export async function getCatalogo(): Promise<Kit[]> {
  const r = await fetch("/api/catalogo");
  if (!r.ok) throw new Error("No se pudo cargar el catálogo");
  const data = await r.json();
  return data.kits as Kit[];
}

export async function validarCarrito(items: { sku: string; cantidad: number }[]) {
  const r = await fetch("/api/carrito/validar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!r.ok) throw new Error("No se pudo validar el carrito");
  return r.json() as Promise<{
    ok: boolean;
    items: LineaCarrito[];
    total: number;
    errores: string[];
  }>;
}

export async function getTrazabilidad(codigo: string) {
  const r = await fetch(`/api/trazabilidad/${encodeURIComponent(codigo)}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("No se pudo consultar la trazabilidad");
  return r.json();
}

export async function crearCheckout(payload: {
  comprador_nombre: string;
  comprador_email: string;
  items: { sku: string; cantidad: number }[];
}) {
  const r = await fetch("/api/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "No se pudo iniciar el pago");
  return data as { redirect_url: string; venta_id: number };
}

export type LoteVenta = { codigo: string; sku: string };

export type VentaResumen = {
  id: number;
  estado: string;
  total: number;
  transaccion_id: string | null;
  comprador_nombre: string | null;
  comprador_email: string | null;
  creada_en: string | null;
  pagada_en: string | null;
  lotes: LoteVenta[];
  items: { sku: string; cantidad: number; precio_unitario: number }[];
};

export async function confirmarCheckout(ventaId: number, resultado: string) {
  const r = await fetch("/api/checkout/confirmar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ venta_id: ventaId, resultado }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "No se pudo confirmar el pago");
  return data as {
    venta_id: number;
    estado: string;
    lotes: LoteVenta[];
    transaccion_id?: string | null;
  };
}

export async function getVentas(): Promise<VentaResumen[]> {
  const r = await fetch("/api/ventas");
  if (!r.ok) throw new Error("No se pudieron cargar los pedidos");
  const data = await r.json();
  return (data.ventas || []) as VentaResumen[];
}

export type GrupoLotes = {
  sku: string;
  hay_mas?: boolean;
  lotes: {
    codigo: string;
    unidades: number;
    en_stock: number;
    despachada: number;
    vence_en: string | null;
  }[];
};

export async function getLotes(q = ""): Promise<GrupoLotes[]> {
  const url = q.trim() ? `/api/lotes?q=${encodeURIComponent(q.trim())}` : "/api/lotes";
  const r = await fetch(url);
  if (!r.ok) throw new Error("No se pudieron cargar los códigos de lote");
  const data = await r.json();
  return (data.grupos || []) as GrupoLotes[];
}
