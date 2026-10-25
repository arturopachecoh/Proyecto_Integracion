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

export type RetiroResumen = {
  id: string;
  lote: string;
  sku: string | null;
  motivo: string | null;
  emitido_en: string | null;
  plazo: string | null;
  estado: "pendiente" | "reportado" | "completo";
  recibido_en: string | null;
  reportado_en: string | null;
  completado_en: string | null;
  unidades_retiradas: number;
};

export type RetiroDetalle = RetiroResumen & {
  unidades: {
    id: string;
    sku: string;
    lote: string;
    espacio_original: string | null;
    en_cuarentena: boolean;
    estado: string;
    espacio_actual: string | null;
  }[];
  derivados: { batch: string; sku: string; sourceBatch: string }[];
  entregas: { orderId: string; customerName: string; productIds: string[] }[];
  notificaciones: { oc_id: string; cliente: string | null; unidades: number; enviada_en: string | null }[];
  ultimo_error: string | null;
};

export async function getRetiros(): Promise<RetiroResumen[]> {
  const r = await fetch("/api/recalls");
  if (!r.ok) throw new Error("No se pudieron cargar los retiros");
  return r.json();
}

export async function getRetiro(id: string): Promise<RetiroDetalle | null> {
  const r = await fetch(`/api/recalls/${encodeURIComponent(id)}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("No se pudo cargar el retiro");
  return r.json();
}
