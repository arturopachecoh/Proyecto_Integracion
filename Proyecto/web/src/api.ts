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
