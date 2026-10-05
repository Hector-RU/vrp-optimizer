# Revisión del proyecto

Se revisaron la API, persistencia, validación, optimizador, modelo ETA, mapas y las cuatro pantallas.

| Antes | Después | Motivo |
| --- | --- | --- |
| Pantallas con estilos, espaciados y acciones inconsistentes | Componentes compartidos, temas claro/oscuro y diseño adaptable | Una presentación coherente y legible |
| Formularios sin errores visibles y sin navegación modal por teclado | Validación visible, foco contenido y cierre con Escape | Evitar fallos silenciosos y facilitar el acceso |
| Optimizar vehículo y filtrar sin operaciones reales | Selector de capas funcional en el mapa; retirada de simulaciones | Mostrar únicamente acciones implementadas |
| Búsqueda duplicada, sin estados vacíos | Un mismo renderizado para búsqueda y carga | Resultados consistentes |
| Mapas solicitados repetidamente en segundo plano | Carga al abrir Rutas, reutilización y reintento | Reducir solicitudes y presentar fallos |
| Pedidos omitidos por el optimizador | Todas las entregas obligatorias o respuesta de inviabilidad | No presentar un plan incompleto como exitoso |
| La estrategia inicial no encontraba un plan para la demostración completa | Inserción paralela como estrategia predeterminada | Asignar las 20 entregas con capacidad y ventanas horarias |
| Traslado de paradas sin restricciones ni métricas actualizadas | Validación de capacidad y horarios y recálculo antes de guardar | Mantener la integridad de la planificación |
| Caché vial que reordenaba segmentos | Ensamblado por orden de paradas | Evitar líneas incorrectas en el mapa |
| Pruebas sobre test.db y archivos temporales versionados | SQLite en memoria y reglas para artefactos locales | Pruebas independientes y repositorio limpio |

La distancia optimizada sigue siendo una aproximación geográfica, y el ETA usa datos sintéticos o estimación lineal. La aplicación local no incluye seguimiento GPS ni tráfico en tiempo real. Consulta README.md para ejecución, configuración y límites.
