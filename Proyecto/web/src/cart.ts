const KEY = "d4-carrito";

export type CartItem = { sku: string; nombre: string; cantidad: number; precio: number | null };

export function leerCarrito(): CartItem[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as CartItem[]) : [];
  } catch {
    return [];
  }
}

export function guardarCarrito(items: CartItem[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new Event("d4-carrito"));
}

export function agregarAlCarrito(item: CartItem, stock: number) {
  const items = leerCarrito();
  const i = items.findIndex((x) => x.sku === item.sku);
  const actual = i >= 0 ? items[i].cantidad : 0;
  const cantidad = Math.min(stock, actual + item.cantidad);
  if (i >= 0) items[i] = { ...items[i], cantidad, nombre: item.nombre, precio: item.precio };
  else items.push({ ...item, cantidad });
  guardarCarrito(items.filter((x) => x.cantidad > 0));
}

export function setCantidad(sku: string, cantidad: number, stock: number) {
  const items = leerCarrito();
  const next = items
    .map((x) => (x.sku === sku ? { ...x, cantidad: Math.max(0, Math.min(stock, cantidad)) } : x))
    .filter((x) => x.cantidad > 0);
  guardarCarrito(next);
}

export function quitar(sku: string) {
  guardarCarrito(leerCarrito().filter((x) => x.sku !== sku));
}

export function vaciar() {
  guardarCarrito([]);
}
