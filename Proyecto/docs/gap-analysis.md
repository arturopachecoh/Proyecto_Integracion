# Gap analysis Entrega 1

Requisito oficial del enunciado (`01`) frente al repo en `develop`.

- **Diseño / diagramas / 3 decisiones:** fuente formal en `docs/informe-e1/` (secuencias instanciadas, anexos, decisiones, estrategia, custodia, IA). El PDF de Canvas se arma desde `informe-e1/INFORME.md`.
- **Farma Central / PoW / acondicionamiento:** implementado. Riesgo: credenciales y rate limit. No llamar desde el agente.
- **30 kits en PROD:** código `producir` listo. Es operación en el servidor, no de este repo. P0 ops.
- **Custodia recepción/movimiento/consumo/generación:** funciona. Genealogía N:M materializada en `lot_relations`. P0 hecho.
- **Venta / despacho / unidades concretas:** cableado con reserva FEFO y mock de pago. Despacho físico a Farma solo si `DISPATCH_FARMA=1`. P0 software hecho; P1 Farma real con autorización.
- **Portal catálogo / stock / precio / carrito:** SPA + APIs. Precio mock si no hay Farma. P0 hecho.
- **Pagos y 20% error:** mock con `CHECKOUT_MODE=mock`. Modo real no se usa sin OK. P0 mock hecho.
- **Visor `/trazabilidad`:** UI + CTE aguas arriba/abajo + clientes. P0 hecho.
- **Vencimiento automático:** helpers existen, el worker no marca vencidas aún. P2.
- **Sensibilidad ±50% precio / umbrales:** política documentada en `implementation-plan.md`, no hay job automático. P1 informe / P2 código.
- **Nginx / HTTPS / servidor UC:** ejemplo de Nginx; no se despliega desde aquí. P1 ops.
- **Tests automatizados:** `tests/test_checkout_pow.py` y Playwright `clickthrough.spec.ts`. P2 ampliar cobertura de custodia.
- **E2 canales / recall:** `Venta.canal` y `origen_grupo` anticipan. P3.
