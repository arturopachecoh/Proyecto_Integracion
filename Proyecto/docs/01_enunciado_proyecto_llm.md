# 01 — Enunciado del proyecto IIC3103, reestructurado para un LLM

> Fuente principal: **Proyecto - Entrega 1.pdf** del curso IIC3103 — Taller de Integración, 2026-2.
>
> Objetivo de este archivo: conservar el contenido y los requisitos del enunciado, pero organizados de una manera más fácil de consumir por un agente de IA.  
> **Este archivo es la fuente de verdad de requisitos funcionales y de entrega.** No reemplazar requisitos por decisiones de arquitectura propias.

---

## 1. Naturaleza del proyecto

El proyecto dura todo el semestre y tiene **entregas acumulativas**.

El objetivo general es:

- automatizar la operación de un negocio realista;
- integrar múltiples sistemas heterogéneos;
- mantener la operación de forma autónoma;
- soportar recursos limitados;
- soportar información incompleta;
- soportar fallas de contrapartes;
- mantener trazabilidad completa y verificable.

El proyecto es práctico. Las decisiones de arquitectura tomadas al inicio se arrastran durante todo el semestre.

Las métricas oficiales se calculan sobre el **ambiente de producción**.

---

## 2. Rol del grupo

Cada grupo representa una **droguería o distribuidora farmacéutica**.

La distribuidora:

1. obtiene insumos;
2. recibe y almacena productos;
3. conserva productos en condiciones adecuadas;
4. acondiciona insumos en presentaciones vendibles;
5. arma kits clínicos;
6. vende kits;
7. despacha productos;
8. mantiene la trazabilidad completa de cada unidad que pasa por la operación.

---

## 3. Tipos de producto

Existen tres niveles principales.

### 3.1 Insumos

Ejemplos:

- principios activos;
- excipientes;
- materiales de empaque.

Se solicitan a **Farma Central**.

No se venden directamente.

### 3.2 Productos acondicionados

Ejemplos:

- blísteres;
- frascos;
- viales.

Se producen en el área de acondicionamiento utilizando insumos.

### 3.3 Kits clínicos

Son productos terminados y vendibles.

Se arman utilizando productos acondicionados.

---

## 4. Ejemplo obligatorio de referencia: KIT-RESP-ADULTO

El enunciado utiliza el kit:

`KIT-RESP-ADULTO`

Composición:

### BLI-AMOXI-500

Blíster de amoxicilina 500 mg x 10 comprimidos.

Por unidad:

- 12 x `API-AMOXI-500`
- 8 x `EXC-LACTOSA-DC`
- 1 x `LAM-BLISTER-PVC`

### BLI-IBUPRO-400

Blíster de ibuprofeno 400 mg x 20 comprimidos.

Por unidad:

- 10 x `API-IBUPRO-400`
- 6 x `EXC-LACTOSA-DC`
- 1 x `LAM-BLISTER-PVC`

### FRA-SALBUTA-120

Frasco de salbutamol jarabe 120 mL.

Por unidad:

- 4 x `API-SALBUTA`
- 8 x `EXC-JARABE-BASE`
- 1 x `FRA-VIDRIO-120`

Existen insumos compartidos entre productos acondicionados.

Esto es intencional y afecta la planificación del abastecimiento.

---

## 5. Propiedades de productos y unidades

Cada producto/unidad puede incluir:

- `SKU`: identifica el tipo de producto;
- `ID`: identifica una unidad específica;
- `ID de lote`: identifica un conjunto concreto de unidades producidas juntas;
- fecha de vencimiento;
- condición de conservación;
- ubicación;
- precio.

### Distinción importante: "lote"

Hay dos conceptos diferentes.

#### Tamaño de lote

Indica el múltiplo válido para realizar una solicitud.

Ejemplo:

si el tamaño de lote es 50, se puede pedir:

- 50;
- 100;
- 150;
- etc.

#### ID de lote

Identifica el conjunto concreto de unidades que fueron producidas juntas.

No confundir ambos conceptos.

El catálogo completo se puede consultar en:

`https://dev.proyecto.2026-2.tallerdeintegracion.cl/visualizer/products`

---

## 6. Espacios físicos de la distribuidora

La distribuidora tiene distintos espacios.

### 6.1 Recepción / check-in

Lugar donde llegan productos desde Farma Central u otras distribuidoras.

No es refrigerado.

### 6.2 Bodega principal

Almacenamiento principal.

No es refrigerado.

### 6.3 Cámara de frío

Almacenamiento refrigerado.

Tiene capacidad limitada.

### 6.4 Bodega externa

También llamada pulmón o buffer.

Características:

- capacidad adicional;
- sin límite de capacidad;
- refrigerada;
- mantiene cadena de frío;
- tiene costo por hora.

### 6.5 Área de acondicionamiento

Lugar donde se producen productos acondicionados y kits.

No es refrigerada.

### 6.6 Área de cuarentena

Lugar para productos que deben bloquearse o retirarse.

Se utiliza desde Entrega 2, pero el diseño de Entrega 1 debe considerar su futura existencia.

### 6.7 Despacho / check-out

Lugar desde donde los productos salen hacia clientes.

No es refrigerado.

---

## 7. Pedidos

En Entrega 1:

- los pedidos nacen solamente desde el portal de venta creado por el grupo;
- el volumen depende de las propias pruebas del grupo.

Desde Entrega 2:

- existirán órdenes de compra externas;
- cada pedido tendrá plazos de cumplimiento.

La arquitectura de Entrega 1 debería permitir incorporar nuevos canales posteriormente.

---

# 8. Procesos principales

## 8.1 Abastecimiento

Flujo general:

1. La distribuidora decide abastecerse.
2. Envía una solicitud a Farma Central.
3. Debe indicar:
   - SKU;
   - cantidad.
4. La cantidad debe ser múltiplo del tamaño de lote.
5. Farma Central responde con una fecha/hora estimada de recepción.
6. El espacio queda ocupado/reservado desde la solicitud.
7. Farma Central utiliza primero el espacio disponible de recepción.
8. El excedente se asigna a bodega externa.
9. La solicitud no se rechaza por falta de espacio.
10. La bodega externa comienza a generar costo incluso si los productos aún están en tránsito.
11. Cuando llega el momento de recepción:
    - los insumos pasan a estar disponibles;
    - reciben un ID de lote.
12. Si el producto requiere frío y llega a recepción:
    - debe moverse a la cámara de frío;
    - de lo contrario empieza a degradarse.
13. Si llegó a bodega externa:
    - mantiene cadena de frío;
    - sigue generando costo.

El grupo debe decidir:

- cuándo comprar;
- cuánto comprar;
- cuánto stock mantener;
- cuándo aceptar costo de bodega externa;
- cómo minimizar vencimiento y merma.

---

## 8.2 Acondicionamiento

Flujo general:

1. El grupo decide cuándo producir.
2. Cada producto posee una fórmula maestra.
3. Todos los insumos necesarios deben estar en el área de acondicionamiento.
4. La cantidad a producir debe respetar el tamaño de lote.
5. Antes de fabricar hay que obtener y resolver un desafío de producción.
6. Con el desafío resuelto se envía la solicitud de fabricación.
7. Farma Central entrega una hora de recepción del resultado.
8. El producto resultante aparece:
   - en acondicionamiento; o
   - en bodega externa,
   según espacio disponible.
9. El producto generado recibe un **nuevo ID de lote**.

Ejemplo:

`BLI-AMOXI-500`

Si el tamaño de lote es 3 y cada unidad usa:

- 12 x API;
- 8 x excipiente;
- 1 x lámina;

entonces para producir el lote se necesitan:

- 36 x `API-AMOXI-500`;
- 24 x `EXC-LACTOSA-DC`;
- 3 x `LAM-BLISTER-PVC`.

---

## 8.3 Validación de producción / Proof of Work

Antes de fabricar es obligatorio resolver un desafío de prueba de trabajo.

### Flujo

1. Pedir desafío:

`POST /farma-central/fabrication/challenge`

Se envían SKU y cantidad.

La respuesta contiene al menos:

- `challengeId`;
- `prefix`;
- `difficulty`;
- `expiresAt`.

2. Resolver localmente.

Se debe encontrar un `nonce`.

3. Solicitar la producción:

`POST /farma-central/products`

Se envían:

- SKU;
- cantidad;
- `challengeId`;
- `nonce`.

### Regla exacta

El nonce es válido cuando:

```text
leadingZeroBits(
  sha256_hex(prefix + ":" + nonce)
) >= difficulty
```

Detalles relevantes:

- se hashea exactamente `prefix + ":" + nonce`;
- se usa SHA-256;
- se analiza el hash hexadecimal;
- la dificultad se expresa en **bits**, no en caracteres hexadecimales;
- el nonce se envía como string;
- el challenge es de un solo uso;
- el challenge expira;
- no se pueden precalcular soluciones.

El enunciado incluye implementaciones de referencia en Python y Node.js.

### Restricción operativa

Resolver el PoW consume CPU.

El mismo servidor también debe ejecutar:

- portal;
- backend;
- base de datos;
- procesos automáticos.

Un solver mal aislado puede afectar la disponibilidad de la aplicación.

---

## 8.4 Conservación y cadena de frío

Únicos espacios refrigerados:

- cámara de frío;
- bodega externa.

No refrigerados:

- recepción;
- bodega principal;
- acondicionamiento;
- despacho.

Reglas:

- un producto refrigerado fuera de frío pierde vida útil;
- por cada minuto de exposición, se adelanta su vencimiento en un 1% de su vida útil nominal;
- la exposición es acumulativa;
- volver al frío no reinicia la exposición;
- `expiresAt` refleja el vencimiento efectivo;
- el sistema no avisa automáticamente que un producto se está degradando;
- el grupo debe detectar y reaccionar.

Casos especialmente relevantes:

- para acondicionar un producto frío, debe pasar por un área no refrigerada;
- un producto frío recién producido puede aparecer fuera de cámara de frío.

---

## 8.5 Vencimiento

Una unidad vencida:

- no puede usarse para acondicionar;
- no puede venderse;
- se descarta automáticamente;
- deja de ocupar espacio.

Los productos acondicionados tienen vencimientos independientes de los insumos.

Producir demasiado temprano puede generar merma.

---

## 8.6 Trazabilidad y custodia

El sistema del grupo debe poder reconstruir el recorrido completo de cualquier unidad.

Debe responder como mínimo estas cuatro preguntas:

1. ¿Qué unidades del lote X están actualmente en inventario y dónde están?
2. ¿En qué productos acondicionados se consumieron unidades del lote X y qué lotes se generaron?
3. ¿A qué clientes se entregaron unidades del lote X, cuándo y en qué pedido?
4. ¿De qué lotes de insumo se produjo el lote X y de dónde provenían esos lotes?

Farma Central registra ciertas transferencias entre distribuidoras, pero **no conserva el historial interno del grupo**.

El grupo debe diseñar:

- qué guardar;
- cuándo guardarlo;
- con qué estructura;
- cómo consultar genealogía hacia arriba y hacia abajo.

### Preparación para entregas futuras

Farma Central emitirá retiros de lote (`recall`).

Frente a un recall se deberá poder:

- encontrar unidades afectadas;
- bloquearlas;
- moverlas a cuarentena;
- identificar productos derivados;
- identificar clientes afectados;
- responder dentro de una ventana acotada.

---

## 8.7 Venta B2C

Cada grupo debe implementar un portal de venta.

Los clientes pueden:

- visualizar kits;
- conocer stock;
- conocer precio;
- agregar productos al carro;
- pagar;
- recibir confirmación.

El precio de venta debe coincidir con el precio vigente del sistema de mercado.

Una venta completada debe registrar:

- pedido;
- pago;
- comprador;
- unidades específicas despachadas;
- trazabilidad/custodia.

---

## 8.8 Canales futuros

En futuras entregas existirán otros canales:

- transferencia de archivos;
- colas de mensajes;
- lenguaje natural;
- otros sistemas.

El diseño de E1 debería facilitar su incorporación.

---

# 9. Sistemas externos

## 9.1 Farma Central

Es el sistema central/ERP del ejercicio.

Administra:

- almacenamiento;
- espacios;
- conservación;
- vencimientos;
- acondicionamiento;
- precios;
- transferencias entre distribuidoras.

Documentación:

`https://dev.proyecto.2026-2.tallerdeintegracion.cl/farma-central/docs`

---

## 9.2 Sistema de precios

El precio fluctúa por oferta y demanda agregada.

El grupo:

- no controla el precio;
- no puede vender a un precio diferente;
- debe consultar el precio vigente.

Existe también historial de precios.

---

## 9.3 Sistema de pago

Es una pasarela de pago.

Permite:

- crear transacción;
- obtener URL de pago;
- redirigir al cliente;
- consultar estado;
- recibir confirmación.

Documentación:

`https://dev.proyecto.2026-2.tallerdeintegracion.cl/checkout/docs/`

---

## 9.4 Sistemas futuros

Posteriormente se incorporarán:

- sistema de órdenes de compra;
- canal de lenguaje natural;
- sistema de retiro de lotes;
- sistema de facturación.

---

# 10. Ambientes

Existen dos ambientes.

## DEV

Uso:

- experimentos;
- pruebas;
- desarrollo.

No afecta métricas oficiales.

## PROD

Uso:

- operación evaluada;
- acciones con consecuencias;
- métricas oficiales.

DEV y PROD tienen:

- URLs diferentes;
- credenciales diferentes.

La aplicación debería cambiar de entorno mediante configuración, por ejemplo variables de entorno.

---

# 11. Entregas del semestre

## Entrega 1

Fecha indicada en el enunciado:

**miércoles 7 de octubre, 18:00**

Ponderación:

**25%**

Objetivos:

- diseño de solución;
- modelo de custodia;
- integración con Farma Central;
- acondicionamiento de kits;
- portal de venta;
- pago en línea;
- portal de trazabilidad.

## Entrega 2

Fecha:

**martes 27 y miércoles 28 de octubre**

Ponderación:

**30%**

Objetivos tentativos:

- órdenes de compra;
- pedidos en lenguaje natural;
- retiro de lote;
- operación continua durante 24–48 horas.

## Entrega 3

Fecha:

**miércoles 18 a viernes 20 de noviembre**

Ponderación:

**45%**

Objetivos tentativos:

- nuevas integraciones;
- facturación;
- escasez inducida;
- retiros de lote sin aviso;
- objetivos de negocio;
- operación continua durante 48–72 horas.

Las entregas son acumulativas.

Lo incompleto en una entrega debe completarse posteriormente.

---

# 12. Entrega 1 — requisitos detallados

## 12.1 Diseño de la solución

Se debe entregar un informe PDF en Canvas.

### A. Diagramas de secuencia

Como mínimo un diagrama por flujo:

#### Abastecimiento

Instanciado específicamente con:

`API-AMOXI-500`

Debe incluir:

- decisión de abastecer;
- cantidad;
- tamaño de lote;
- solicitud;
- recepción;
- almacenamiento;
- destino.

#### Acondicionamiento

Debe mostrar:

1. producción de un lote de `BLI-AMOXI-500`;
2. armado posterior de `KIT-RESP-ADULTO`.

Debe incluir:

- insumos concretos;
- cantidades;
- tamaños de lote;
- movimientos;
- challenge;
- resolución PoW;
- producción;
- disponibilidad final.

#### Venta

Debe mostrar:

- pedido de `KIT-RESP-ADULTO`;
- portal;
- carro;
- backend;
- pago;
- resultado;
- registro del pedido;
- unidades concretas;
- custodia;
- despacho.

Los diagramas **no deben ser genéricos**.

---

### B. Tres decisiones principales de arquitectura

Para cada decisión se debe explicar:

- qué se decidió;
- por qué;
- qué se gana;
- qué se pierde;
- trade-offs.

Ejemplos de áreas válidas:

- patrón de integración;
- administración del estado;
- sincronía vs asincronía;
- arquitectura de procesos;
- persistencia.

---

### C. Estrategia de abastecimiento y producción

Debe contener criterios concretos.

#### Umbrales de reposición

Definir:

- cuándo reponer;
- con qué stock se activa la reposición.

#### Cantidades de compra

Definir:

- cuánto pedir;
- por SKU;
- respetando tamaños de lote.

#### Bodega externa

Definir:

- cuándo aceptar su costo;
- cuándo evitarla.

#### Vencimiento

Definir:

- cómo reducir merma;
- en qué orden consumir stock.

#### Sensibilidad al precio

Definir una reacción concreta si el precio:

- sube 50%;
- baja 50%.

No basta una declaración genérica.

---

### D. Modelo de custodia y trazabilidad

Es un entregable central.

Debe documentar:

#### Qué se registra y cuándo

Registrar eventos asociados a:

- recepción;
- movimiento entre espacios;
- consumo;
- generación de producto;
- venta;
- despacho.

#### Modelo de datos

Debe ser concreto.

Debe representar la relación entre:

- lotes consumidos;
- lotes generados.

Esta relación puede ser muchos-a-muchos.

#### Respuesta a las cuatro preguntas de trazabilidad

Para cada pregunta del punto 8.6 se debe indicar:

- consulta;
- procedimiento;
- mecanismo.

#### Fallas

Se debe explicar cómo evitar situaciones como:

- producto físicamente entregado;
- pero venta/custodia registrada a medias.

---

# 13. Configuración del servidor

Cada grupo recibe un servidor.

URL:

`https://distribuidorX.ing.uc.cl`

`X` es el número del grupo.

Requisitos:

- servidor web;
- HTTPS;
- portal de venta publicado;
- portal de trazabilidad publicado;
- base de datos instalada;
- persistencia disponible.

---

# 14. Acondicionamiento mínimo exigido

Antes de la entrega, en **PROD**, el grupo debe haber acondicionado:

**al menos 30 unidades de cada tipo de kit clínico disponible.**

Para hacerlo:

1. abastecer insumos;
2. mover materiales;
3. respetar conservación;
4. resolver PoW;
5. producir productos intermedios;
6. producir kits.

No es obligatorio que esos 30 kits sigan disponibles al momento de evaluar.

Basta que hayan sido producidos en PROD antes de la fecha límite.

---

# 15. Portal de venta

Debe estar disponible en la URL del grupo.

## 15.1 Catálogo

Mostrar todos los kits.

Por kit:

- nombre;
- imagen si existe;
- precio vigente;
- stock disponible.

### Precio

No puede ser un valor fijo.

Debe corresponder al precio vigente del sistema de precios.

### Stock

Debe reflejar inventario real.

Debe excluir:

- vencidos;
- inutilizados.

---

## 15.2 Carro de compras

Debe permitir:

- agregar productos;
- seleccionar cantidad;
- limitar cantidad al stock;
- mostrar resumen;
- modificar cantidades;
- eliminar productos;
- mostrar total.

---

## 15.3 Proceso de compra

Al confirmar:

1. crear transacción de pago;
2. enviar monto;
3. enviar URLs para cada resultado;
4. recibir URL de la pasarela;
5. redirigir usuario;
6. manejar:
   - éxito;
   - cancelación;
   - error.
7. recibir confirmación;
8. actualizar pedido;
9. registrar custodia;
10. asociar unidades específicas al comprador y transacción.

### Error simulado

En Entrega 1 el sistema de pago genera errores aleatorios aproximadamente en un **20%** de las transacciones.

El flujo debe manejarlo.

---

# 16. Visor de trazabilidad

Ruta requerida:

`https://distribuidorX.ing.uc.cl/trazabilidad`

Debe aceptar lote:

- mediante parámetro en la URL;
- mediante campo de búsqueda.

Para un lote debe mostrar:

## Datos del lote

- SKU;
- cantidad;
- vencimiento efectivo;
- condición de conservación;
- espacios donde están sus unidades.

## Aguas arriba

Mostrar recursivamente:

- lotes consumidos que lo generaron;
- cantidades;
- procedencia;
- hasta llegar a Farma Central u otra distribuidora.

## Aguas abajo

Mostrar recursivamente:

- lotes derivados;
- productos generados;
- entregas;
- clientes;
- orden;
- cantidad.

## Origen

Indicar si el lote fue:

- producido por el grupo;
- recibido de otra distribuidora;
- recibido de Farma Central.

### Rendimiento

No se evalúa principalmente la estética.

Se evalúa:

- completitud;
- correctitud;
- tiempo de respuesta razonable.

No debería ser necesario cargar o recorrer todo el historial para cada consulta.

---

# 17. Forma de entrega

## Código

Todo el código debe estar versionado en el repositorio GitHub asignado.

Debe estar actualizado al momento de la entrega.

## Informe

El informe de diseño se sube a Canvas como PDF.

---

# 18. Declaración de uso de inteligencia artificial

El uso de IA está permitido.

El informe debe declarar:

- herramientas/modelos utilizados;
- tareas asignadas;
- estrategia para verificar correctitud y calidad.

El equipo docente puede pedir a cualquier integrante explicar oralmente cualquier parte del código o diseño.

No comprender lo entregado puede afectar la evaluación y puede constituir un problema de integridad académica.

---

# 19. Evaluación

Cada entrega tiene:

## Nota grupal

Considera:

- calidad técnica;
- funcionamiento;
- nivel de completitud;
- objetivos de negocio.

## Nota individual

Considera:

- coevaluación;
- explicación oral individual.

Para aprobar el curso:

- nota individual >= 4,0;
- nota del proyecto >= 4,0.

---

# 20. Infraestructura entregada por el curso

Servidor:

- sistema operativo indicado en el enunciado: Ubuntu 26.04;
- 2 cores;
- 2 GB RAM;
- 30 GB almacenamiento.

Puertos abiertos:

- 22 SSH;
- 80 HTTP;
- 443 HTTPS.

El servidor no incluye dependencias de la aplicación.

El grupo puede instalar software con permisos elevados.

---

# 21. Acceso SSH

Formato:

```bash
ssh username@url
```

El curso entrega:

- usuario;
- contraseña.

Reglas:

- no cambiar configuración SSH innecesariamente;
- está expresamente prohibido cambiar la contraseña del usuario entregado.

---

# 22. Firewall

Existe firewall externo.

`ufw` de Ubuntu no debe modificarse.

No seguir pasos de tutoriales que activen o cambien `ufw`.

Modificarlo puede bloquear el acceso.

---

# 23. Servidor web

El enunciado recomienda usar un servidor web/reverse proxy.

Alternativas mencionadas:

- Nginx;
- Apache;
- Traefik;
- Caddy.

Los tutoriales del curso se basan principalmente en Nginx.

Responsabilidades esperadas:

- HTTPS;
- certificados;
- robustez;
- manejo de múltiples requests;
- recuperación ante fallas del proceso de aplicación.

---

# 24. HTTPS

Todos los servicios deben exponerse mediante HTTPS.

El enunciado recomienda:

- Let's Encrypt;
- Certbot;
- Nginx o Apache.

Requisitos ya disponibles:

- usuario con sudo;
- SSH;
- puertos 80/443;
- URL pública.

El certificado de Let's Encrypt tiene duración de 90 días.

El documento indica que para el período del curso no sería necesario preocuparse por renovación automática si se configura a tiempo.

---

# 25. Rúbrica

El PDF entregado **no contiene la rúbrica detallada con puntos por criterio**.

Indica expresamente que:

> la rúbrica de evaluación con criterios detallados y ponderaciones se publicará posteriormente.

Por lo tanto:

- no inventar porcentajes internos;
- no asumir puntaje por requisito;
- utilizar los requisitos de este documento como checklist hasta disponer de la rúbrica oficial.

---

# 26. Regla de interpretación para un LLM

Cuando un agente utilice este archivo:

1. tratar este documento como requisitos oficiales reestructurados;
2. no cambiar requisitos por preferencias de implementación;
3. distinguir siempre:
   - requisito oficial;
   - recomendación técnica;
   - inferencia;
4. ante una contradicción con otro documento de arquitectura:
   - gana este archivo para requisitos;
5. no inventar endpoints que no estén documentados;
6. consultar Swagger/docs oficiales para contratos exactos;
7. no ejecutar acciones en DEV/PROD sin autorización explícita del usuario.
