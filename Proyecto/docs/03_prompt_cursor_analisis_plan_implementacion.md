# 03 — Prompt maestro para Cursor: analizar repo, planificar y preparar Entrega 1

## Rol

Actúa como arquitecto/a de software y senior engineer responsable de preparar este repositorio para la **Entrega 1 de IIC3103 — Taller de Integración**.

Tu prioridad no es reescribir el proyecto.

Tu prioridad es:

1. entender lo que existe;
2. conservar el trabajo útil;
3. identificar gaps respecto al enunciado;
4. proponer un plan;
5. mejorar arquitectura de forma incremental;
6. preparar una implementación sólida;
7. evitar cualquier impacto sobre infraestructura real de la universidad.

---

# 1. Documentos obligatorios

Antes de tocar código, lee completamente:

```text
01_enunciado_proyecto_llm.md
02_arquitectura_decisiones_entrega1.md
```

Regla de precedencia:

```text
01 = requisitos oficiales
02 = propuesta técnica
repo actual = realidad existente
```

Si existe conflicto:

1. gana el requisito oficial;
2. después se prioriza preservar código existente;
3. la arquitectura propuesta se adapta a la realidad.

No cambies requisitos del enunciado para hacerlos coincidir con el código.

---

# 2. Modo inicial: análisis / planning

Comienza en **planning mode**.

No empieces refactors grandes inmediatamente.

Primero entrega una comprensión detallada del repositorio.

---

# 3. Herramientas MCP obligatorias

Utiliza, si están disponibles en Cursor:

- MCP **Codebase Memory**;
- MCP **Graphyfy / Graphify** o el nombre equivalente disponible en el entorno.

Objetivo:

- entender arquitectura;
- crear mapa de módulos;
- detectar dependencias;
- detectar puntos de entrada;
- encontrar modelos;
- identificar lógica compartida;
- entender flujo frontend/backend;
- localizar integraciones;
- entender persistencia;
- detectar deuda técnica.

## Si alguno no está disponible

No inventes resultados.

Indica:

```text
MCP X no disponible
```

y utiliza:

- búsqueda del repo;
- árbol de archivos;
- análisis de imports;
- búsquedas semánticas;
- grep/ripgrep;
- historial Git;
- package manifests;
- configuración.

---

# 4. Antes de modificar Git

Ejecuta/inspecciona:

```text
git status
git branch
git log reciente
```

Identifica:

- branch actual;
- archivos modificados;
- trabajo no commiteado;
- commits recientes del compañero.

### Seguridad

Si existen cambios no commiteados:

- NO descartarlos;
- NO resetear;
- NO hacer checkout destructivo;
- NO hacer stash automáticamente.

Repórtalos primero.

---

# 5. Nueva branch

Cuando sea seguro y luego del análisis inicial, crea una branch:

```text
feat/entrega1-integration-base
```

Si ya existe, usa una variante clara.

No sobrescribas branches.

No hagas force push.

No hagas push remoto salvo que el usuario lo solicite explícitamente.

---

# 6. Analizar el trabajo del compañero

Debes estudiar el código existente y responder:

## Frontend

- framework;
- versión;
- estructura;
- rutas;
- componentes;
- estado;
- estilos;
- librerías de UI;
- librería de iconos;
- llamadas al backend;
- carrito actual;
- portal actual;
- trazabilidad actual.

## Backend

- lenguaje;
- framework;
- entrypoint;
- módulos;
- endpoints;
- modelos;
- acceso a BD;
- migraciones;
- integraciones;
- jobs;
- PoW;
- trazabilidad;
- errores;
- configuración.

## Base de datos

- motor;
- schema;
- tablas;
- migraciones;
- relaciones;
- índices;
- datos persistidos;
- modelo de lotes;
- modelo de unidades;
- eventos de custodia.

## Infraestructura

- Docker;
- compose;
- Nginx;
- scripts;
- env;
- deployment;
- CI;
- systemd;
- process manager.

---

# 7. No asumir migración tecnológica

Aunque exista preferencia por:

- Next.js;
- React;
- TypeScript;
- Node.js;

NO migres automáticamente el backend Python.

Primero determina:

```text
cuánto funciona
qué integra
qué valor tiene
cuánto costaría migrar
qué riesgo introduce
```

Si Python ya contiene trabajo valioso:

**presérvalo para E1.**

La migración a Node/TypeScript sólo se propone si existe una justificación técnica fuerte.

---

# 8. Arquitectura objetivo preferida

Priorizar:

```text
Nginx
  |
  +-- Next.js frontend
  |
  +-- Backend API modular
          |
          +-- PostgreSQL
          +-- Farma Central adapter
          +-- Checkout adapter
          +-- worker / jobs / PoW
```

No crear una proliferación de microservicios.

La separación front/backend es suficiente.

El backend debe ser modular internamente.

---

# 9. Next.js

Si el frontend existente ya es Next.js:

- conservarlo;
- mejorar organización;
- no recrearlo.

Si no es Next.js:

- evaluar costo de migración;
- no migrar sólo por preferencia;
- proponer migración únicamente si es realista.

Preferencias:

- React;
- TypeScript;
- App Router si ya está presente;
- componentes reutilizables;
- tipado compartido cuando sea razonable.

---

# 10. Iconos

Identifica qué librería ya existe.

Si existe `react-icons`:

- conservarla.

No añadir otra librería para lograr lo mismo.

Si no hay ninguna:

- escoger una sola;
- justificarla;
- mantener consistencia.

---

# 11. Gap analysis contra el enunciado

Construye una matriz con estas columnas:

```text
Requisito oficial
Estado actual
Archivo/módulo
Qué funciona
Qué falta
Riesgo
Cambio mínimo recomendado
Prioridad
```

Debe cubrir como mínimo:

- diseño/arquitectura;
- Farma Central;
- abastecimiento;
- PoW;
- acondicionamiento;
- 30 kits de cada tipo;
- cadena de frío;
- vencimiento;
- custodia;
- genealogía;
- portal de venta;
- stock;
- precio;
- carrito;
- pagos;
- estados de pago;
- registro de unidades vendidas;
- visor de trazabilidad;
- upstream;
- downstream;
- servidor;
- HTTPS;
- BD;
- preparación E2.

---

# 12. Base de datos: análisis obligatorio

Determina si el modelo actual puede responder estas cuatro preguntas:

1. ¿Qué unidades del lote X están en inventario y dónde?
2. ¿Qué lotes se generaron consumiendo el lote X?
3. ¿Qué lotes originaron el lote X?
4. ¿A qué clientes se entregaron unidades del lote X?

Si alguna no puede responderse eficientemente:

proponer cambios.

---

# 13. Relación N:M entre lotes

Verifica específicamente si existe una representación de:

```text
parent_lot
child_lot
quantity
```

que permita N:M.

Si solamente existe:

```text
lot.parent_id
```

marcarlo como problema.

Proponer tabla intermedia o equivalente.

---

# 14. Modelo sugerido

No lo implementes ciegamente.

Compáralo con la BD existente:

```text
lots
units
lot_relations
custody_events
orders
order_items
order_units
payments
outbox_events
```

Reutilizar equivalentes existentes.

No crear tablas duplicadas con distintos nombres para el mismo concepto.

---

# 15. Migraciones

Si hacen falta cambios de BD:

- crear migraciones;
- no editar destructivamente una migración ya aplicada;
- evitar pérdida de datos;
- documentar rollback;
- no aplicar migraciones al servidor UC.

En esta fase:

```text
preparar migración != ejecutarla remotamente
```

---

# 16. Custodia

Modelar eventos para:

- recepción;
- movimiento;
- consumo;
- producción;
- reserva;
- venta;
- despacho;
- vencimiento;
- cuarentena futura.

El sistema debe poder reconstruir historia.

---

# 17. Consistencia

Busca puntos donde una caída pueda dejar estado parcial.

Ejemplos:

- pago confirmado pero pedido no actualizado;
- unidad marcada vendida pero sin cliente;
- lote derivado sin relación con padres;
- despacho sin evento de custodia.

Proponer:

- transacciones;
- idempotencia;
- outbox;
- estados intermedios.

No añadir infraestructura compleja si una transacción de PostgreSQL basta.

---

# 18. Integraciones externas

Centralizar Farma Central y Checkout.

No dejar llamadas HTTP distribuidas arbitrariamente.

Crear/normalizar:

```text
FarmaCentralClient
CheckoutClient
```

o equivalentes.

Definir interfaces.

Preparar mocks.

---

# 19. MUY IMPORTANTE — no tocar infraestructura real

En esta fase está estrictamente prohibido ejecutar acciones contra:

- Farma Central DEV;
- Farma Central PROD;
- Checkout de la universidad;
- servidor `distribuidorX.ing.uc.cl`;
- base de datos remota;
- Nginx remoto.

No ejecutar:

- compras;
- movimientos;
- fabricación;
- challenges;
- PoW real;
- pagos;
- callbacks;
- producción;
- despliegues.

No hacer pruebas remotas.

No hacer smoke tests remotos.

No hacer requests "sólo para ver".

---

# 20. No usar credenciales reales

No imprimir.

No copiar.

No mover.

No versionar.

No cambiar credenciales existentes.

Si encuentras secretos versionados:

- no los repitas en la respuesta;
- márcalo como riesgo;
- propone remediación.

---

# 21. Modo seguro para integraciones

La aplicación debe poder trabajar localmente sin llamar sistemas reales.

Preferencia:

```text
INTEGRATION_MODE=mock
```

o equivalente.

Crear:

```text
MockFarmaCentralClient
MockCheckoutClient
```

si todavía no existen y si esto encaja con la arquitectura actual.

El modo seguro debe ser el default para desarrollo durante esta fase.

---

# 22. Tests

No ejecutar tests que contacten infraestructura real.

Por defecto:

- no e2e;
- no integration tests;
- no remote smoke tests.

No ejecutar una suite sin revisar primero si tiene efectos externos.

Se permite solamente validación puramente local como:

- lint;
- typecheck;
- build;
- análisis estático;

si está garantizado que no realiza requests.

Tests unitarios con mocks:

- sólo si están claramente aislados;
- idealmente después de informar qué se va a ejecutar.

---

# 23. Proof of Work

Analiza si existe.

Si existe:

- revisar algoritmo;
- revisar aislamiento;
- revisar consumo CPU.

Si no existe:

planificar worker aislado.

No solicitar challenge real.

No ejecutar PoW real.

Puedes implementar el solver con datos sintéticos/locales si hace falta, pero no ejecutarlo contra la universidad.

---

# 24. Worker / async

Identificar operaciones que no deberían bloquear HTTP:

- PoW;
- espera de fabricación;
- reconciliación;
- outbox;
- reservas expiradas;
- futuras reposiciones.

Priorizar solución simple.

No introducir Kafka/Redis/RabbitMQ salvo que exista una necesidad real y el repo ya lo justifique.

PostgreSQL + worker simple puede ser suficiente.

---

# 25. Portal de venta — UX

Debes analizar la experiencia actual.

Antes de rediseñar:

1. inspeccionar páginas existentes;
2. identificar qué se puede conservar;
3. revisar buenas prácticas actuales de:
   - catálogo;
   - carrito;
   - checkout;
   - estados de pago;
   - errores;
   - stock.

Si tienes acceso a búsqueda web:

- puedes investigar patrones UX modernos;
- no copies diseños completos;
- utiliza principios y patrones.

El objetivo es una UI:

- clara;
- profesional;
- rápida;
- fácil de entender;
- consistente.

---

# 26. Catálogo

Debe mostrar claramente:

- kit;
- nombre;
- imagen si existe;
- precio;
- stock;
- CTA.

No mostrar datos internos innecesarios.

Diseñar:

- loading;
- error;
- empty;
- out of stock.

---

# 27. Carrito

Debe permitir:

- agregar;
- modificar;
- eliminar;
- ver total.

Antes de checkout:

- revalidar precio;
- revalidar stock.

En esta fase hacerlo mediante mocks/local state si la integración real está deshabilitada.

---

# 28. Checkout UX

Preparar estados:

```text
pending
success
cancelled
error
```

Recordar:

- Entrega 1 simula aproximadamente 20% de error.

La UI debe tratar error como estado esperado.

---

# 29. Visor de trazabilidad — UX

Diseñar para comprensión.

Debe incluir:

- buscador;
- resumen del lote;
- origen;
- ubicaciones;
- upstream;
- downstream;
- entregas;
- clientes.

Representación recomendada:

```text
ancestros -> lote consultado -> descendientes
```

Puede ser:

- árbol;
- grafo;
- columnas conectadas;
- timeline + relaciones.

Elegir el patrón que mejor encaje con el código existente.

---

# 30. Performance del visor

No recorrer toda la BD en memoria.

Revisar:

- índices;
- recursive CTE;
- queries;
- paginación si aplica;
- profundidad.

Documentar complejidad y riesgos.

---

# 31. Experiencia visual

No sobrecargar con "look de dashboard IA".

Preferencia:

- layout limpio;
- tipografía legible;
- jerarquía clara;
- cards consistentes;
- estados semánticos;
- iconos coherentes.

La estética no debe sacrificar tiempo de implementación crítica.

---

# 32. Accesibilidad

Revisar al menos:

- navegación por teclado;
- labels;
- contraste;
- focus states;
- feedback de acciones;
- mensajes de error entendibles;
- botones disabled;
- no depender sólo del color.

---

# 33. Plan de mejora

Crear un plan por fases.

Cada tarea debe indicar:

```text
Objetivo
Archivos afectados
Qué reutiliza
Qué modifica
Dependencias
Riesgo
Criterio de terminado
```

Clasificar:

```text
P0 crítico
P1 necesario
P2 mejora
P3 futuro
```

---

# 34. P0 sugerido

Sin asumir que estén faltando:

- modelo de trazabilidad;
- modelo de lotes;
- relación N:M;
- persistencia;
- adaptadores de integraciones;
- portal funcional;
- visor funcional;
- consistencia del pago;
- aislamiento PoW;
- configuración segura.

---

# 35. Crear documentación interna

En la nueva branch, después del análisis, crear o actualizar:

```text
docs/
  current-state.md
  gap-analysis.md
  architecture.md
  implementation-plan.md
```

No duplicar documentación si el repo ya tiene archivos equivalentes.

---

# 36. Cursor rules / skills / agentes

Después de comprender el repo, evaluar si conviene crear reglas persistentes.

Si el entorno soporta Cursor Rules, crear reglas pequeñas y útiles.

Ejemplos:

```text
.cursor/rules/
  project-architecture.mdc
  university-integration-safety.mdc
  traceability-model.mdc
```

Contenido esperado:

## `project-architecture`

- separación front/backend;
- no reescribir sin análisis;
- convenciones;
- estructura.

## `university-integration-safety`

Regla fuerte:

```text
NO CALL UNIVERSITY SERVICES WITHOUT EXPLICIT USER APPROVAL
```

Debe cubrir:

- Farma;
- Checkout;
- server;
- remote DB;
- deploy.

## `traceability-model`

- relación N:M;
- eventos;
- custodia;
- consultas upstream/downstream.

Si Cursor dispone de Skills/Agents personalizados:

- puedes crear skills especializados;
- solamente si aportan valor real;
- documentar propósito;
- no crear diez agentes innecesarios.

Ejemplos posibles:

- `traceability-auditor`;
- `integration-safety`;
- `delivery-requirements-checker`.

Si el soporte exacto de skills cambia según versión:

- detectar capacidades del entorno;
- no inventar formatos.

---

# 37. No sobreescribir configuración del compañero

Antes de:

- cambiar formatter;
- cambiar linter;
- cambiar package manager;
- cambiar ORM;
- cambiar framework;
- cambiar DB;

explicar por qué.

Preferir compatibilidad.

---

# 38. Dependencias

Antes de añadir una dependencia:

1. revisar si ya existe solución equivalente;
2. revisar tamaño/impacto;
3. justificar.

Evitar dependencias grandes para problemas pequeños.

---

# 39. Resultado esperado del planning mode

Antes de implementar, entrega:

## A. Resumen del estado actual

Máximo 1–2 páginas equivalentes.

## B. Arquitectura actual

Diagrama Mermaid.

## C. Gap analysis

Tabla completa.

## D. Decisiones

Lista:

```text
conservar
refactorizar
reemplazar
crear
```

con motivo.

## E. Modelo de datos propuesto

Solamente cambios necesarios.

## F. Plan de implementación

Ordenado por prioridad.

## G. Riesgos

Incluyendo:

- fecha;
- migración;
- servidor;
- integración;
- PoW;
- BD;
- trabajo ya existente.

---

# 40. Después del plan

No empieces una reescritura masiva.

Después de que el plan quede claro:

implementar incrementalmente.

Orden recomendado:

```text
1. estructura/configuración
2. dominio/BD
3. custodia
4. adapters/mocks
5. trazabilidad
6. portal
7. worker/PoW
8. documentación de deploy
```

---

# 41. Deployment

Preparar archivos necesarios.

Ejemplos:

- Nginx config de ejemplo;
- systemd unit de ejemplo;
- `.env.example`;
- script de build;
- instrucciones.

Pero:

**NO ejecutar deployment.**

No conectarte por SSH.

No tocar el servidor.

---

# 42. Universidad como destino final

La arquitectura debe quedar preparada para desplegar posteriormente en:

```text
https://distribuidorX.ing.uc.cl
```

mediante:

- Nginx;
- HTTPS;
- aplicación;
- PostgreSQL;
- procesos locales.

No diseñar una solución que dependa obligatoriamente de Vercel para funcionar en evaluación.

---

# 43. Restricción de recursos

Diseñar para aproximadamente:

```text
2 CPU
2 GB RAM
30 GB disk
```

Evitar:

- múltiples servidores pesados;
- muchos runtimes;
- microservicios innecesarios;
- workers concurrentes sin límites.

---

# 44. Criterio para detenerse

Si para continuar necesitas:

- credenciales;
- llamar API universitaria;
- ejecutar producción;
- modificar servidor;
- confirmar un endpoint no documentado;
- destruir datos;
- descartar código del compañero;

**detente y pregunta al usuario.**

No adivines.

---

# 45. Criterio de calidad

La solución final debe ser:

```text
reutilizable
modular
trazable
consistente
simple
segura
explicable
extensible
```

No busques impresionar con complejidad.

Busca que un integrante del grupo pueda defender cada decisión frente al profesor.

---

# 46. Primera acción requerida

Ahora:

1. lee `01_enunciado_proyecto_llm.md`;
2. lee `02_arquitectura_decisiones_entrega1.md`;
3. usa Codebase Memory;
4. usa Graphyfy/Graphify;
5. inspecciona Git;
6. analiza repo completo;
7. produce el plan;
8. NO llames servicios de la universidad;
9. NO despliegues;
10. NO ejecutes flujos reales.
