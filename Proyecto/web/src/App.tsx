import { NavLink, Route, Routes } from "react-router-dom";
import { FiAlertTriangle, FiList, FiPackage, FiSearch, FiShoppingCart } from "react-icons/fi";
import { useEffect, useState } from "react";
import Catalogo from "./pages/Catalogo";
import Carrito from "./pages/Carrito";
import Checkout from "./pages/Checkout";
import Trazabilidad from "./pages/Trazabilidad";
import Pedidos from "./pages/Pedidos";
import Pago from "./pages/Pago";
import { RetiroDetallePage, Retiros } from "./pages/Retiros";
import { leerCarrito } from "./cart";

export default function App() {
  const [n, setN] = useState(0);
  useEffect(() => {
    const sync = () => setN(leerCarrito().reduce((s, i) => s + i.cantidad, 0));
    sync();
    window.addEventListener("d4-carrito", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("d4-carrito", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return (
    <>
      <header className="top">
        <strong>Distribuidora 4</strong>
        <nav>
          <NavLink to="/" end><FiPackage /> Catálogo</NavLink>
          <NavLink to="/carrito"><FiShoppingCart /> Carro{n > 0 && <span className="badge">{n}</span>}</NavLink>
          <NavLink to="/trazabilidad"><FiSearch /> Trazabilidad</NavLink>
          <NavLink to="/pedidos"><FiList /> Pedidos</NavLink>
          <NavLink to="/recalls"><FiAlertTriangle /> Retiros</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Catalogo />} />
          <Route path="/carrito" element={<Carrito />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/trazabilidad" element={<Trazabilidad />} />
          <Route path="/pedidos" element={<Pedidos />} />
          <Route path="/pago/:estado" element={<Pago />} />
          <Route path="/recalls" element={<Retiros />} />
          <Route path="/recalls/:id" element={<RetiroDetallePage />} />
        </Routes>
      </main>
    </>
  );
}
