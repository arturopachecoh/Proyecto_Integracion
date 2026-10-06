import { Link, useParams } from "react-router-dom";

const COPY: Record<string, { titulo: string; texto: string }> = {
  exito: {
    titulo: "Pago exitoso",
    texto: "Registramos tu pedido y las unidades concretas quedan asociadas a tu compra.",
  },
  cancelado: {
    titulo: "Pago cancelado",
    texto: "No se cobró nada. El stock reservado se liberó y puedes volver al carro.",
  },
  error: {
    titulo: "Error de pago",
    texto: "La pasarela no pudo completar la transacción (en E1 ocurre cerca del 20% de las veces). Inténtalo de nuevo.",
  },
};

export default function Pago() {
  const { estado = "error" } = useParams();
  const info = COPY[estado] || COPY.error;
  return (
    <>
      <h1>{info.titulo}</h1>
      <p className="lead">{info.texto}</p>
      <p>
        <Link to="/">Volver al catálogo</Link>
        {" · "}
        <Link to="/carrito">Ir al carro</Link>
      </p>
    </>
  );
}
