# C. Estrategia de abastecimiento y producción

El PDF pide criterios **concretos**, no una declaración de intenciones. Los números salen de `app/scripts/calcular_requerimientos.py` (objetivo por defecto: 30 por kit), `app/produccion.py` (`tanda=10`) y la corrida PROD de `logs.txt`.

Esta política la ejecuta **quien corre `producir`**, no un cron automático. Eso es deliberado en E1: un job que compre solo contra precio volátil puede vaciar presupuesto o llenar `buffer`. Queda como hueco a automatizar en E2 si el curso lo exige.

---

## Objetivo de planta (E1)

Antes de la fecha de entrega, en **PROD**, acondicionar **al menos 30 unidades de cada kit clínico vendible**. No hace falta que sigan en stock al evaluar; hace falta haberlas producido.

La corrida del 6 de octubre arrancó con:

```text
Producir {KIT-RESP-ADULTO: 30, KIT-PEDIA-FEBRIL: 30, KIT-CURACION: 30,
          KIT-CARDIO-BASICO: 30, KIT-DIABETES: 30, KIT-ANALGESIA: 30,
          KIT-ATB-IV: 30, KIT-VACUNA-INFLU: 30, KIT-GASTRO: 30, KIT-DERMATO: 30}
```

Diez SKU × 30 = 300 kits pedidos. El orquestador redondea cada nivel al `production.batch` de Farma.

---

## Umbrales de reposición

| Nivel | Se dispara cuando | Acción |
|---|---|---|
| Kit | `stock_disponible + fabricaciones_en_camino` del SKU &lt; **una tanda (10)** y el objetivo de campaña no está cubierto | `fabricar` ese kit por el mínimo múltiplo de batch que no pase lo que cabe en `packaging` |
| Intermedio (BLI, FRA, …) | La receta del kit en tanda pide más de lo que hay en espacios usables | `fabricar` el intermedio, de mayor profundidad a menor |
| Insumo (API, EXC, LAM, …) | `planificar` indica demanda y no hay suficiente `en_camino` | `comprar` el múltiplo de batch |

`stock_disponible` ignora `reservada`, `despachada`, `consumida`, `vencida` y lo que vence en menos de 1 h.

No reponemos “al 20% de capacidad de bodega”. Reponemos **por tanda de kits**, porque el cuello de botella real es `packaging` (150 unidades de huella; `calcular_requerimientos` avisa si un lote no cabe).

---

## Cantidades de compra

Siempre múltiplo de `tamano_lote(sku)` (`catalogo()[sku]["production"]["batch"]`). `comprar` rechaza cualquier otra cantidad.

Ejemplos de la primera ola PROD (`logs.txt`):

| SKU | Cantidad comprada (solicitud) | Notas |
|---|---|---|
| `API-AMOXI-500` | 250 (#1) | Insumo del blíster del kit respiratorio |
| `API-IBUPRO-400` | 150 (#2) | Compartido con otros kits |
| Más tarde `API-AMOXI-500` | 100 (#71) | Segunda ola cuando la tanda siguiente pidió más |

`calcular_requerimientos` explota la receta de **todos** los kits a la vez: un excipiente compartido se compra una sola vez, redondeado al batch, no diez veces. Eso importa: el enunciado dice que los insumos compartidos son intencionales.

La tanda de fabricación de kits no es 30 de un golpe: `producir(..., tanda=10)` arma de a 10 para no saturar acondicionamiento. Farma, en PROD, entregó lotes de kit de 3 o 6 unidades (p. ej. #56: 6 × `KIT-RESP-ADULTO`), que son múltiplos de su batch.

---

## Bodega externa (`buffer`)

Farma cobra por hora en el espacio `buffer`. Criterio:

- **Productos de ambiente:** no se dejan en `buffer`. `producir` los despeja a `bodega`. Si el orquestador ve acondicionamiento lleno de intermedios que no avanzan, los vacía a bodega (`_vaciar_acondicionamiento`), no al buffer.
- **Productos de frío:** el worker mueve `checkIn`/`bodega` → `cold` si hay cupo; **solo si `libres("cold") == 0`** usa `buffer`. Al nacer en `packaging`, lo mismo (`nacidas_en_acondicionamiento`).
- **Aceptar el costo:** únicamente como válvula de la cámara, nunca como almacén de campaña. Una tanda extra “porque el precio bajó” **no** se autoriza si eso implica pagar buffer.

Capacidades: se leen de `GET /farma-central/spaces` (`app/espacios.py`). No se hardcodean IDs (cambian entre DEV y PROD).

---

## Vencimiento y merma

- **Orden de consumo:** FEFO. `unidades_disponibles` ordena por `packaging` primero (ya están en la mesa) y después `vence_en` ascendente. Margen: no se usa lo que vence en **menos de 1 hora** (`timedelta(hours=1)`).
- **Portal:** `stock_disponible` usa el mismo margen. El catálogo no ofrece vencidos ni reservados.
- **Worker:** aún **no** llama `registrar_vencidas` cuando Farma desaparece unidades. El helper existe. Hasta que se enganche, un vencido puede seguir en Postgres como `en_stock` un tick más: el margen de 1 h cubre parte de esa ventana. Hueco declarado, no escondido.
- **Frío:** sacar un SKU frío de cámara degrada `expiresAt`. Por eso las frías se mueven a `packaging` al final de `fabricar`, y si el challenge falla se `_devolver_al_frio`.

---

## Sensibilidad al precio (±50 %)

El precio de venta del portal es el de `GET /farma-central/market/prices` en el momento de `validar_carrito` / checkout, no un valor fijo. El **costo** de insumo es el de Farma al comprar.

| Shock | Política concreta |
|---|---|
| Precio de **venta** del kit **+50 %** | No adelantar tandas. Seguir el umbral de 10. El margen mejora; producir de más inmoviliza `packaging` y riesgo de merma. |
| Precio de **venta** **−50 %** | Una tanda adicional (10 kits, redondeada a batch) **solo si** `libres("bodega")` o `libres("cold")` cubren la huella. Si la única holgura es `buffer`, **no**. |
| Costo de **insumo** +50 % | No comprar colchón. `calcular_requerimientos` ya deja un resto por redondeo de batch; ese resto es el único buffer de material. |
| Costo de insumo −50 % | Comprar el batch que `planificar` pida para la tanda actual, no “llenar la bodega”. El shared API (`API-AMOXI-500`) se compra cuando **cualquier** kit de la tanda lo necesita, no por kit.

No hay job que lea el mercado cada hora. Quien opera planta aplica la tabla. Si E2 exige autonomía 24 h, el lugar del if es `produccion.planificar`, no el portal.
