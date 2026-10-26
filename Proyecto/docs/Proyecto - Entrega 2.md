

## **IIC3103 - Taller de Integración** 

Departamento Ciencia de la Computación Escuela de Ingeniería Pontificia Universidad Católica 



# **Proyecto — Entrega 2** 

Este documento describe los objetivos de la Entrega 2 del proyecto. **Complementa el enunciado de la Entrega 1, que sigue vigente** en todo lo que no se modifique aquí: contexto, productos, espacios de la distribuidora, procesos de abastecimiento, acondicionamiento, conservación, vencimiento y trazabilidad, y sistemas ya integrados (Farma Central, precios de mercado y pago). Sólo se describe lo nuevo. 

- **Ponderación:** 30% de la nota del proyecto. 

- **Período de evaluación:** desde el **martes 27 de octubre a las 10:00** hasta el **miércoles 28 de octubre a las 22:00** (36 horas, hora de Chile). 

- **Informe de diseño:** se sube a Canvas antes del término del período de evaluación. 

Las entregas son acumulativas: lo pedido en la Entrega 1 que no esté funcionando debe completarse para esta entrega. En particular, el visor de trazabilidad y el modelo de custodia son la base del retiro de lote descrito más abajo. 

# **Objetivos de la Entrega 2** 

Durante esta entrega la distribuidora pasa a operar de forma autónoma: recibe pedidos de clientes por tres canales distintos, los acepta o rechaza, acondiciona lo necesario y despacha dentro de plazo, mientras responde a un retiro de lote emitido por Farma Central en un momento que no conoce de antemano. 

1. Integrar el **sistema de órdenes de compra** y cumplir los pedidos recibidos por **sFTP** y **Pub/Sub** . 

2. Integrar el **canal de mensajería** , donde los pedidos llegan escritos en lenguaje natural. 

3. Responder el **retiro de lote** emitido durante el período de evaluación. 

4. Mantener el sistema **en operación continua** durante todo el período. 

5. Documentar el diseño de lo anterior en un **informe breve** . 

Todos los ítems se evalúan sobre el ambiente de producción, durante el período de evaluación. 

## **Pedidos de clientes** 

A partir de esta entrega, farmacias, clínicas y hospitales le compran kits clínicos a cada distribuidora. Cada pedido es una **orden de compra (OC)** registrada en el sistema de órdenes de compra, con un cliente, un kit clínico (SKU), una cantidad y una fecha y hora máxima de entrega. 

Los pedidos llegan por tres canales: 

|**Canal**|**Cómo llega**|**Qué trae**|
|---|---|---|
|**sFTP**|Archivos XML en una casilla sFTP<br>propia del grupo.|El ID de la OC. El detalle se consulta<br>en el sistema de órdenes.|
|**Pub/Sub**|Mensajes en un tópico de Google<br>Cloud Pub/Sub propio del grupo.|El ID de la OC. El detalle se consulta<br>en el sistema de órdenes.|
|**Mensajería**|Un webhook que Farma Central envía<br>al servidor del grupo.|Un texto libre escrito por el cliente, sin<br>OC asociada. Si es un pedido, el grupo<br>lo registra y la OC se crea en ese<br>momento.|



Como referencia para planificar el abastecimiento, cada distribuidora recibirá en producción del orden de **8 órdenes de compra por hora** entre sFTP y Pub/Sub, y del orden de **3 mensajes por hora** por mensajería, en su mayoría pedidos. Cada pedido es de uno o dos kits. Las OC de sFTP y Pub/Sub tienen un plazo aproximado de **2 horas** desde su creación; los pedidos por mensajería indican su plazo en el texto. Los volúmenes reales pueden variar, ya que los valores anteriores corresponden a valores esperados. 

### **Ciclo de vida de una orden de compra** 

1. La OC se crea en estado creada y se notifica al grupo por el canal correspondiente. En mensajería, la OC se crea cuando el grupo registra el mensaje como pedido (ver más abajo), y desde ahí sigue este mismo flujo. 

2. El grupo consulta el detalle de la OC y decide si la acepta o la rechaza, con el servicio de actualización de estado. Una OC que no se responde nunca pasa a estado cumplida, aunque se haya completado el despacho de productos. 

3. Si el grupo la acepta, debe despachar las unidades antes del vencimiento de la OC: mover cada unidad al sector de despacho y despacharla con POST /farma-central/dispatch, indicando el ID de la unidad y el ID de la OC. Se puede despachar en varias partes. 

4. Cuando se despacha la cantidad completa antes del vencimiento, la OC pasa a cumplida. Si vence antes, pasa a vencida y no se paga, aunque se haya despachado una parte. 



<!-- Start of picture text -->
se despacha la cantidad<br>completa antes del vencimiento<br>el grupo la acepta aceptada vence antesel despacho de completar<br>llega por sFTP 0 Pub/Sub, vence sin respuesta vencida<br>ose registra desde<br>sa mensae creada |__elgrupolarechaza<br>el cliente la anula rechazada<br>™ anulada |<br><!-- End of picture text -->

_Estados de una orden de compra y sus transiciones._ 

Los estados con doble borde son finales: una OC que llega a ellos ya no cambia de estado. Toda OC nace en creada —las de mensajería, cuando el grupo registra el mensaje como pedido— y sólo el grupo puede aceptarla o rechazarla. Cualquier OC en creada o aceptada pasa a vencida al llegar su fecha de vencimiento sin haberse cumplido. El estado anulada existe en el sistema, pero en esta entrega los clientes no anulan pedidos. 

Cada despacho debe quedar registrado en el modelo de custodia de la Entrega 1: qué unidades, de qué ID de lote, a qué cliente y en qué OC. Es lo que responde la pregunta 3 de trazabilidad y lo que se necesita para el retiro de lote. 

### **Sistema de órdenes de compra** 

Es una API WEB que permite consultar una OC por su ID y actualizar su estado. No permite consultas masivas: sólo se puede obtener una orden a la vez, por su ID. Para esta entrega se usan los servicios de autenticación, obtener orden de compra y actualizar estado. 

Documentación: <u>https://dev.proyecto.2026-2.tallerdeintegracion.cl/ordenes-compra/docs</u> 

### **Canal sFTP** 

Cada grupo tiene una casilla en el servidor sFTP del curso, con credenciales propias por ambiente que se enviarán a cada grupo. En la casilla aparecerán archivos XML, cada uno con el ID de una OC. El grupo debe revisar la casilla periódicamente, obtener el detalle de cada OC en el sistema de órdenes y aceptarla o rechazarla. El Anexo 1 muestra el formato de los archivos e información importante para realizar la conexión. 

### **Canal Pub/Sub** 

Cada OC de este canal se publica como un mensaje en el tópico del grupo: 

<mark>projects/taller-integracion-310700/topics/[AMBIENTE].proyecto.2026-2.grupo[X]</mark> 

Donde [AMBIENTE] es dev o prod y [X] es el número de grupo. Cada grupo crea su propia suscripción, push o pull, con las credenciales que entrega el servicio "Obtener llave Pub/Sub" del sistema de órdenes. El Anexo 2 muestra cómo hacerlo. 

## **Canal de mensajería: pedidos en lenguaje natural** 

Las farmacias pequeñas no se integran por sFTP ni por Pub/Sub: escriben sus pedidos por una plataforma de mensajería, como lo harían por WhatsApp. Farma Central opera esa plataforma y entrega cada mensaje al servidor de la distribuidora mediante un **webhook** , del mismo modo en que lo hacen las plataformas de mensajería comerciales. 

La plataforma de mensajería es un sistema distinto del de órdenes de compra, con su propia API: recibe y entrega los mensajes, registra la respuesta del grupo a cada uno y, cuando el grupo registra un mensaje como pedido, crea la OC correspondiente en el sistema de órdenes. 

Documentación: <u>https://dev.proyecto.2026-2.tallerdeintegracion.cl/messaging/docs</u> 

Como en cualquier canal de este tipo, no todo lo que llega es un pedido: entre los mensajes se cuelan otras solicitudes, pedidos de ayuda y preguntas por el estado de pedidos anteriores. El grupo debe distinguirlos, y sólo los pedidos se convierten en órdenes de compra. 

Este canal obliga a integrar un componente cuya salida no es determinista: un modelo de lenguaje o LLM, dentro de un flujo que compromete a la distribuidora con un cliente. Comprometerse con un pedido mal interpretado es peor que descartarlo. 

### **Recepción del mensaje** 

Cada grupo debe exponer el siguiente servicio en su servidor: 

<mark>POST https://choripanX.ing.uc.cl/api/messaging</mark> 

Cuerpo del mensaje: 

<mark>{ "messageId": "msg_01JB7Q2F4R8S", "sender": { "name": "Farmacia Los Aromos", "phone": "+56 9 5555 0123" }, "text": "Hola, buenas tardes. Les escribe Rosa de la Farmacia Los Aromos. Necesito dos kits respiratorios para adulto, los que traen amoxicilina, para hoy antes de las 7 de la tarde. Gracias!", "receivedAt": "2026-10-27T16:05:00Z" }</mark> 

Reglas de la entrega: 

- **Autenticación.** Cada request trae el encabezado Authorization: Bearer <token>, con un token OIDC firmado por Google para la cuenta de servicio de la plataforma de mensajería, cuya dirección se publicará en la documentación de la plataforma de mensajería. El grupo debe verificar la firma del token, su emisor, su audiencia —que es la URL exacta del servicio— y su vigencia, y rechazar con 401 lo que no cumpla. 

- **Confirmación.** Una respuesta 2xx en menos de 15 segundos confirma la recepción. Cualquier otra respuesta, o ninguna, hace que la plataforma reintente el envío más tarde, con esperas crecientes, durante un tiempo acotado. Un mensaje que agota los reintentos se pierde. 

- **Duplicados.** La entrega es "al menos una vez": un mismo mensaje puede llegar más de una vez, incluso después de haber respondido 2xx. El campo messageId identifica el mensaje. 

- **Tiempo de respuesta.** Interpretar un texto con un modelo de lenguaje puede tardar más de 15 segundos. Se recomienda confirmar la recepción de inmediato y procesar el mensaje después. 

### **Interpretación del mensaje** 

Los mensajes no traen una orden de compra asociada. Para cada mensaje, el grupo debe decidir primero si es un pedido y, si lo es, interpretar del texto tres datos: 

- **Kit clínico (SKU):** el texto puede nombrar el kit por su uso, por sus componentes, por un principio activo o con palabras del cliente ("el de la diabetes", "los que traen amoxicilina"). 

- **Cantidad:** puede venir en palabras ("dos", "un par", "media docena"). 

- **Fecha y hora de entrega:** puede ser relativa al momento en que se escribió el mensaje ("para hoy antes de las 7", "en tres horas", "mañana a primera hora"). Se interpreta en hora de Chile, a partir de receivedAt. 

Algunos pedidos **no se pueden cumplir tal como están escritos** : son ambiguos entre dos kits, piden algo que no es un kit clínico del catálogo, piden una cantidad que no se especifica, o piden un plazo que ya pasó. Lo correcto en esos casos, igual que con los mensajes que no son pedidos, es descartarlos. 

Para el ejemplo anterior, la interpretación correcta es: 

- <mark>{ "sku": "KIT-RESP-ADULTO", "quantity": 2, "deliveryDate": "2026-10-27T22:00:00Z" }</mark> 

Es importante procesar correctamente que “hoy” se calcula en base al parámetro receivedAt. En este caso, tiene el valor de "2026-10-27T16:05:00Z". 

Un mensaje como el siguiente no es un pedido y debe descartarse: 

<mark>"text": "Hola, ¿me pueden confirmar si ya despacharon lo que les pedí ayer? Gracias"</mark> 

### **Registrar o descartar** 

Cada mensaje se responde una sola vez, con el siguiente servicio de la plataforma de mensajería. Para registrar un pedido se declara la interpretación: 

<mark>POST /messaging/messages/{messageId}/response { "status": "order", "interpretation": { "sku": "KIT-RESP-ADULTO", "quantity": 2, "deliveryDate": "2026-10-27T22:00:00Z" } }</mark> 

Para descartar —un mensaje que no es un pedido, o un pedido ambiguo o imposible de cumplir— se envía "status": "discarded" y un campo reason con texto libre. Un mensaje que no se responde cuenta como mal resuelto. 

Cada mensaje debe responderse dentro de los **30 minutos** siguientes a receivedAt. Pasado ese plazo, el servicio rechaza la respuesta y el mensaje cuenta como no respondido. 

Al registrar un pedido, la plataforma de mensajería crea la OC en el sistema de órdenes de compra, en estado creada —con canal mensajeria, el nombre del remitente como cliente y los datos declarados— y responde su ID en el campo orderId. Registrar un mensaje es la única forma de crear una OC de este canal: cada OC queda asociada al mensaje que la originó, y la evaluación compara esa OC con lo que pedía ese mensaje. Desde ahí la OC sigue el flujo de cualquier otra: el grupo la acepta o la rechaza en el sistema de órdenes según su capacidad, la despacha con POST /farma-central/dispatch y vence en la deliveryDate declarada. Así quedan separadas dos decisiones distintas: qué pidió el cliente, que se declara al responder el mensaje, y si la distribuidora toma el pedido, que se decide al aceptar o rechazar la OC. 

#### **Ni la plataforma de mensajería ni el sistema de órdenes indican si la interpretación es** 

**correcta** : la OC avanza según lo que el grupo declaró. La evaluación, en cambio, compara contra lo que el cliente pidió realmente. Un pedido cuenta como cumplido si, antes de la fecha y hora que pidió el cliente, se despachó al menos la cantidad que pidió del kit que pidió. Si se despachó otro kit, menos unidades o fuera de plazo, el pedido no cuenta como cumplido. 

Una interpretación equivocada se descuenta además en el ítem de interpretación, aunque el pedido haya quedado cumplido. 

Se podrá realizar el seguimiento de estas métricas en el portal del grupo. 

### **Uso de modelos de lenguaje** 

Cada grupo elige cómo interpretar los pedidos. Para facilitarlo, el equipo docente pone a disposición un **gateway de modelos de lenguaje** , basado en <u>Lite-LLM. El Gateway expone una API</u> compatible con la API de OpenAI, con una clave por grupo y un presupuesto diario de uso. 

<mark>URL Gateway por publicar</mark> 

Los modelos disponibles y el presupuesto se informan en la documentación del gateway. Su uso es opcional: cada grupo puede usar otro proveedor, a su costo. 

Al diseñar el canal conviene considerar, al menos: 

- Validar la salida del modelo contra el catálogo y contra las reglas del negocio antes de registrar un pedido. Que el modelo responda un SKU no significa que ese SKU exista o sea un kit. 

- Qué hacer cuando el modelo no está seguro, cuando no responde, o cuando se agota el presupuesto. 

- Registrar qué texto se interpretó, qué respondió el modelo y qué decidió el sistema, para poder revisar después cada decisión. 

## **Retiro de lote** 

Durante el período de evaluación, Farma Central emitirá **varios retiros de lote (recall)** , en momentos que el grupo no conoce de antemano, cada uno sobre un lote que pasó por la distribuidora del grupo. Las unidades del lote retirado no pueden seguir comercializándose, y tampoco los productos que se hayan acondicionado a partir de ellas. Desde que se emite cada retiro, el grupo tiene **30 minutos** para responder. El puntaje se obtiene del retiro mejor respondido: basta con responder uno correctamente. 

### **Aviso del retiro** 

Farma Central avisa el retiro con un webhook al servidor del grupo, con las mismas reglas de autenticación, confirmación y duplicados del canal de mensajería: 

<mark>POST https://choripanX.ing.uc.cl/api/recalls { "recallId": "rcl_6721a0b3", "batch": "L-EXCLACTOSA-261026-3B9C", "sku": "EXC-LACTOSA-DC", "reason": "Contaminación detectada por el proveedor", "issuedAt": "2026-10-28T14:12:00Z", "deadline": "2026-10-28T14:42:00Z" }</mark> 

Si el webhook no llega, por ejemplo porque el servidor estaba caído, los retiros activos también se pueden consultar en GET /farma-central/recalls. El plazo corre desde issuedAt, se haya recibido o no el aviso. 

### **Qué debe hacer el grupo dentro del plazo** 

1. **Aislar el stock afectado.** Mover al área de cuarentena todas las unidades en stock del lote retirado y de los lotes que se generaron a partir de él, recursivamente. El área de cuarentena es de sólo entrada: una unidad que entra no puede volver a moverse, ni consumirse, ni venderse. Esas unidades tampoco pueden seguir apareciendo como disponibles en el portal de venta. 

2. **Notificar a cada cliente afectado.** Por cada OC en la que se despacharon unidades afectadas, enviar una notificación con POST /farmacentral/recalls/{recallId}/notifications, indicando la OC, el cliente y las unidades despachadas. 

3. **Reportar a Farma Central.** Enviar con POST /farma-central/recalls/{recallId}/report el resultado de la investigación: unidades afectadas en stock y el espacio en que estaban, lotes derivados del lote retirado, y entregas a clientes con las unidades afectadas. Se puede reenviar: vale el último reporte recibido dentro del plazo. 

El reporte responde exactamente las preguntas 1, 2 y 3 de trazabilidad de la Entrega 1. Los formatos de la notificación y del reporte están en la documentación de Farma Central. Farma Central no valida en línea el contenido: responde que lo recibió, pero no si es correcto. 

_Reportar de más también se evalúa. Una unidad que no pertenece al lote retirado ni a sus derivados, reportada o puesta en cuarentena, cuenta como error._ 

### **Registro de retiros en el portal** 

El portal web del grupo debe incluir, en https://choripanX.ing.uc.cl/recalls, un listado de todos los retiros recibidos. Al ingresar al detalle de un retiro se deben mostrar los productos retirados de circulación, indicando el SKU y el ID de cada producto. Puede implementarse como parte del visor de trazabilidad. 

### **Retiros de lote en el ambiente de desarrollo** 

En el ambiente de desarrollo, cada grupo puede gatillar retiros de lote de prueba desde su portal de grupo, cuantas veces quiera. Farma Central elige el lote y emite el retiro como lo hará en producción. Una vez vencido el plazo, el portal muestra la respuesta correcta para comparar con lo que el grupo reportó. En producción no hay retiros de prueba: todos los que se emitan se evalúan. 

## **Evaluación** 

### **Operación continua** 

El sistema debe operar de forma autónoma y estar disponible durante todo el período de evaluación. Como métrica, el equipo docente consultará cada 5 minutos el portal de venta (https://choripanX.ing.uc.cl) y el visor de trazabilidad (https://choripanX.ing.uc.cl/trazabilidad). Una consulta cuenta como disponible si responde exitosamente en menos de 10 segundos. 

### **Informe de diseño** 

Un informe breve, de no más de 6 páginas sin contar diagramas, que documente las decisiones de esta entrega. Debe incluir: 

1. **Canal de mensajería.** Un diagrama de secuencia instanciado en el mensaje de ejemplo de este enunciado, desde que llega el webhook hasta que el mensaje queda respondido y, si es un pedido, su OC queda aceptada o rechazada. 

2. **Retiro de lote.** Un diagrama de secuencia desde que llega el aviso hasta que se envía el reporte, indicando qué consultas del modelo de custodia se usan y por qué terminan dentro de los 30 minutos. 

3. **Salida no determinista.** Cómo se valida lo que responde el modelo de lenguaje antes de comprometerse con un cliente, y qué hace el sistema cuando el modelo duda, falla o se agota el presupuesto. 

4. **Duplicados y reintentos.** Cómo se garantiza que un mensaje repetido —por mensajería, por Pub/Sub o un archivo sFTP leído dos veces— no genere una aceptación o un despacho doble. 

5. **Cambios al modelo de custodia.** Qué se modificó respecto del diseño de la Entrega 1 y por qué. 

### **Rúbrica** 

La nota grupal de la entrega se calcula sobre 100 puntos, con nota = 1 + 6 × puntaje / 100. Las métricas de cumplimiento son proporcionales: con el 80% o más se obtiene el puntaje completo del ítem, y bajo ese valor, la fracción correspondiente. 

A continuación, la rúbrica preliminar para la evaluación de esta entrega. Se publicará la versión final antes del inicio del período de evaluación. 

Los ítems de retiro se calculan sobre el retiro mejor respondido del período. 

|**Ítem**|**Cómo se mide**|**Puntos**|
|---|---|---|
|**OC por sFTP**|Porcentaje de OC cumplidas sobre las recibidas por<br>el canal durante el período.|17,5|
|**OC por Pub/Sub**|Porcentaje de OC cumplidas sobre las recibidas por<br>el canal durante el período.|17,5|



|**Ítem**|**Cómo se mide**|**Puntos**|
|---|---|---|
|**Mensajería: cumplimiento**|Porcentaje de pedidos cumplidos —el kit que el<br>cliente pidió, al menos en la cantidad que pidió,<br>dentro del plazo que pidió— sobre los pedidos<br>recibidos que se podían cumplir.|10|
|**Mensajería: interpretación**|Porcentaje de mensajes resueltos correctamente:<br>pedidos registrados con SKU, cantidad y fecha de<br>entrega correctos (la fecha, con 15 minutos de<br>tolerancia), y descartados los pedidos que no se<br>podían cumplir y los mensajes que no eran pedidos.<br>Un mensaje sin respuesta cuenta como error.<br>Rechazar la OC de un pedido bien registrado no<br>afecta este ítem.|10|
|**Retiro: reporte**|Cobertura del reporte sobre las unidades en stock,<br>los lotes derivados y las entregas afectadas,<br>descontando lo reportado de más.|8|
|**Retiro: registro en el portal**|Listado de retiros recibidos en /recalls, con el detalle<br>de los productos retirados (SKU e ID).|2|
|**Retiro: notificaciones**|OC afectadas notificadas correctamente,<br>descontando las notificadas de más.|5|
|**Retiro: cuarentena**|Unidades afectadas en el área de cuarentena al<br>vencer el plazo, descontando las movidas de más.|5|
|**Retiro: tiempo**|Reporte recibido dentro de los 30 minutos.|3|
|**Operación continua**|Porcentaje de consultas exitosas al portal y al visor<br>de trazabilidad durante el período, con meta 90%.|10|
|**Informe de diseño**|Doce puntos, repartidos en partes iguales entre los<br>cinco contenidos pedidos.|12|
|**Total**||**100**|



Descuentos: −5 puntos si el informe no incluye la declaración de uso de inteligencia artificial, y −5 puntos si el repositorio no está actualizado al inicio del período de evaluación. 

### **Forma de entrega** 

- **Código fuente:** versionado en el repositorio del grupo en GitHub y actualizado al inicio del período de evaluación. 

- **Informe de diseño:** en PDF, en la tarea correspondiente de Canvas, antes del término del período de evaluación. 

### **Declaración de uso de inteligencia artificial** 

Igual que en la Entrega 1, el informe debe incluir una sección que declare: 

- Qué herramientas o modelos se utilizaron, incluidos los que forman parte del sistema, como el que interpreta los pedidos por mensajería. 

- Qué tareas específicas se les asignó. 

- Qué estrategia empleó el grupo para verificar la correctitud y la calidad de los resultados entregados por la IA. 

El equipo docente podrá solicitar a cualquier integrante una explicación oral de cualquier parte del código o del diseño entregado, de forma dirigida o aleatoria, como parte integral de la evaluación. No comprender íntegramente el contenido entregado, o entregar información falsa o inexistente, constituye una falta a la integridad académica. 

## **Calendario de disponibilidad** 

Los sistemas y servicios nuevos de esta entrega se habilitan de forma escalonada, según el siguiente calendario. Cualquier cambio en estas fechas se avisará por Canvas. 

|**Fecha**|**Qué queda disponible para los grupos**|
|---|---|
|**Lunes 12 de octubre**|Publicación de este enunciado.|
|**Jueves 15 de octubre**|Pedidos por sFTP y Pub/Sub en el ambiente de desarrollo: casillas sFTP, con<br>su contraseña en el portal de grupo, tópicos de Pub/Sub y órdenes de compra<br>con el volumen y los plazos de esta entrega.|
|**Lunes 19 de octubre**|En el ambiente de desarrollo:<br>• Canal de mensajería: envío de mensajes al webhook del grupo y API de<br>mensajería, con su documentación.<br>• Retiros de lote: aviso al webhook del grupo, servicios de Farma Central para<br>consultar retiros, notificar y reportar, con su documentación, y simulación de<br>retiros desde el portal de grupo.<br>• Gateway de LLM: URL, modelos disponibles y clave de cada grupo.|
|**Jueves 22 de octubre**|Versión final de la rúbrica.<br>Seguimiento de las métricas de mensajería en el portal de grupo.|
|**Lunes 26 de octubre**|Ambiente de producción habilitado para configuración: credenciales y<br>servicios de producción, incluida la clave de producción del gateway, para<br>que cada grupo configure y pruebe sus integraciones.<br>Todavía no se envían pedidos, mensajes ni retiros.|
|**Martes 27 de octubre,**<br>**10:00**|Inicio del período de evaluación.<br>Comienzan a llegar en producción las órdenes de compra, los mensajes y los<br>retiros de lote.|
|**Miércoles 28 de**<br>**octubre, 22:00**|Término del período de evaluación y plazo de entrega del informe de diseño.|



# **Anexos** 

## **1. Conexión a la casilla sFTP** 

sFTP (SSH File Transfer Protocol) es un protocolo de transferencia de archivos que funciona sobre SSH, por lo que la comunicación va cifrada. Cada grupo tiene una casilla por ambiente, con estos datos: 

- **Servidor:** choripan10.ing.uc.cl, puerto 22. 

- **Usuario:** grupoX_desarrollo o grupoX_produccion, según el ambiente, donde X es el número de grupo. 

- **Contraseña:** disponible en el portal de grupo. 

Cada archivo de la casilla corresponde a una orden de compra y tiene este formato: 

<mark><?xml version="1.0" encoding="UTF-8"?> <order> <id>{ID}</id> <sku>{SKU}</sku> <qty>{CANTIDAD}</qty> </order></mark> 

Donde {ID} es el ID de la OC en el sistema de órdenes de compra. Antes de aceptar, consulte siempre el detalle de la OC en ese sistema: es la fuente oficial del pedido. 

Dos cosas a considerar: 

1. **El servidor no avisa.** Un sFTP es un sistema de archivos: no notifica cuando llega un archivo nuevo, así que hay que revisar la casilla periódicamente. 

2. **Archivos ya procesados.** La casilla puede seguir mostrando archivos que ya se leyeron. Cada grupo debe llevar registro de qué archivos y qué OC ya procesó, para no aceptar ni despachar dos veces la misma orden. 

_Cierre siempre las sesiones. Cada usuario —es decir, cada grupo y ambiente— tiene un número limitado de sesiones sFTP simultáneas. Una sesión que no se cierra, por ejemplo porque el proceso falló antes de desconectarse o porque se abre una conexión nueva en cada revisión sin cerrar la anterior, sigue ocupando un cupo. Al llegar al límite, el servidor rechaza las conexiones nuevas: los pedidos siguen llegando a la casilla, pero el grupo no puede acceder a ella para leerlos hasta que esas sesiones terminen. Cierre la conexión también cuando ocurre un error._ 

## **2. Suscripción a Pub/Sub** 

Para crear una suscripción se necesita: 

1. El nombre del tópico, que incluye el ID del proyecto: projects/taller-integracion310700/topics/[AMBIENTE].proyecto.2026-2.grupo[X]. 

2. El nombre de la suscripción, también con el ID del proyecto: projects/tallerintegracion-310700/subscriptions/[NOMBRE], donde [NOMBRE] no lleva espacios ni símbolos. 

3. Las credenciales, que entrega el servicio "Obtener llave Pub/Sub" (GET /ordenescompra/pubsub/key). La llave de desarrollo es distinta de la de producción, y cada una sólo puede crear suscripciones en el tópico de su ambiente. 

Ejemplo en Node.js de una suscripción push para el grupo 1 en desarrollo: 

<mark>// npm i @google-cloud/pubsub const {PubSub} = require('@google-cloud/pubsub'); const pubSubClient = new PubSub({ projectId: 'taller-integracion-310700',   // fijo para dev y prod keyFilename: 'keys/dev/grupo1.json'       // credenciales del ambiente }); async function main() { const topic = 'projects/taller-integracion-310700/topics/dev.proyecto.2026-2.grupo1'; const subscription = 'projects/taller-integracion-310700/subscriptions/grupo1-dev'; await pubSubClient.topic(topic).createSubscription(subscription, { pushConfig: { pushEndpoint: 'https://choripan1.ing.uc.cl/api/pubsub/orders' } }); }</mark> 

<mark>main().catch(console.error);</mark> 

En una suscripción push, cada mensaje llega con el contenido codificado en base64 en message.data. También se pueden usar suscripciones pull, en las que el grupo consulta periódicamente los mensajes pendientes. Documentación: <u>https://cloud.google.com/pubsub/docs/subscriber</u> 

## **3. Verificación de un token OIDC de Google** 

Ejemplo en Node.js con la librería oficial de Google: 

<mark>// npm i google-auth-library const {OAuth2Client} = require('google-auth-library'); const client = new OAuth2Client();</mark> 

<mark>async function verificar(req, audiencia, cuentaEsperada) { const token = (req.headers.authorization || '').replace(/^Bearer /, ''); const ticket = await client.verifyIdToken({ idToken: token, audience: audiencia }); const payload = ticket.getPayload();   // verifica firma, emisor y vigencia if (payload.email !== cuentaEsperada || !payload.email_verified) {</mark> 

- <mark>throw new Error('remitente no autorizado'); } }</mark> 

En Python existe la función equivalente google.oauth2.id_token.verify_oauth2_token, de la librería google-auth. 

## **Declaración de uso de Inteligencia Artificial** 

Este enunciado se elaboró con apoyo de herramientas de inteligencia artificial. 

- Herramientas utilizadas: Claude, de Anthropic. 

- Tareas asignadas: revisión de los enunciados de semestres anteriores y del código fuente del simulador, propuesta de alcance, redacción y revisión del enunciado. 

- Actividades de verificación 

   - Las afirmaciones sobre el comportamiento de los sistemas se contrastaron contra el código fuente del simulador. 

   - El equipo docente revisó, editó y estructuró el texto final. 

El contenido de este enunciado es responsabilidad del equipo docente, con independencia de las herramientas usadas para redactarlo. 

## **Versiones del documento** 

- Versión 1: 11/10/2026 — versión inicial del documento. 

