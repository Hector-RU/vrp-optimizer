"use strict";

const $ = (id) => document.getElementById(id);
const appState = {
  orders: [],
  vehicles: [],
  routes: [],
  screen: "dashboard",
  loaded: false,
  busy: false,
};
let charts = [],
  toastTimer,
  modalTrigger,
  mapController,
  mapSignature = "",
  mapVersion = 0;
const number = new Intl.NumberFormat("es-DO", { maximumFractionDigits: 1 });
const clock = (minutes) =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const depotId = () => appState.orders[0]?.id;
const deliveries = () => appState.orders.slice(1);
const vehicleName = (id) =>
  appState.vehicles.find((v) => v.id === id)?.name || `Vehículo #${id}`;

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let message = `Error ${response.status}. Inténtalo de nuevo.`;
    try {
      const body = await response.json();
      message = Array.isArray(body.detail)
        ? body.detail
            .map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`)
            .join(" · ")
        : body.detail || message;
    } catch {
      /* The server may return a non-JSON error. */
    }
    throw new Error(message);
  }
  return response.json();
}

async function allRecords(path) {
  const items = [];
  for (let skip = 0; ; skip += 500) {
    const page = await api(`${path}?skip=${skip}&limit=500`);
    items.push(...page);
    if (page.length < 500) return items;
  }
}

function showToast(message, error = false) {
  clearTimeout(toastTimer);
  $("toast-message").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").classList.remove("hidden");
  toastTimer = setTimeout(
    () => $("toast").classList.add("hidden"),
    error ? 7000 : 4000,
  );
}

function navigate(screen) {
  if (!["dashboard", "orders", "vehicles", "routing"].includes(screen))
    screen = "dashboard";
  appState.screen = screen;
  document
    .querySelectorAll(".view-section")
    .forEach((section) =>
      section.classList.toggle("hidden", section.id !== screen),
    );
  document.querySelectorAll(".nav-links a").forEach((link) => {
    const active = link.dataset.target === screen;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("current-screen").textContent = {
    dashboard: "Resumen",
    orders: "Pedidos",
    vehicles: "Vehículos",
    routing: "Rutas",
  }[screen];
  document.title = `${$("current-screen").textContent} · VRP Optimizer`;
  window.scrollTo({ top: 0, behavior: "auto" });
  if (screen === "routing") {
    refreshMap();
    requestAnimationFrame(() => $("map-iframe").contentWindow?.dispatchEvent(new Event("resize")));
  }
  if (screen === "dashboard") charts.forEach((chart) => chart.resize());
}

function updateButtons() {
  $("btn-generate-routes").disabled = appState.busy || !appState.loaded;
  $("btn-seed-data").disabled = appState.busy || !appState.loaded;
  $("export-routes").disabled = !appState.routes.length;
  $("new-order").disabled = appState.busy || !appState.loaded;
  $("new-vehicle").disabled = appState.busy || !appState.loaded;
  document
    .querySelectorAll("[data-action]")
    .forEach((button) => (button.disabled = appState.busy));
}

async function fetchDashboardData() {
  try {
    const [orders, vehicles, routes] = await Promise.all([
      allRecords("/orders"),
      allRecords("/vehicles"),
      api("/routes"),
    ]);
    Object.assign(appState, { orders, vehicles, routes, loaded: true });
    $("data-error").classList.add("hidden");
    $("connection-status").innerHTML =
      '<span class="status-dot"></span> Conectado';
    renderStats();
    renderOrders();
    renderVehicles();
    renderRoutes();
    renderAnalytics();
    if (!routes.length) resetMap();
    else if (appState.screen === "routing") refreshMap();
  } catch (error) {
    $("data-error").classList.remove("hidden");
    $("data-error").querySelector("span").textContent =
      `No se pudieron actualizar los datos. ${error.message}`;
    $("connection-status").textContent = "Sin conexión";
    appState.loaded = false;
  } finally {
    updateButtons();
  }
}

function renderStats() {
  const demand = deliveries().reduce((sum, o) => sum + o.demand, 0);
  const capacity = appState.vehicles.reduce((sum, v) => sum + v.capacity, 0);
  $("stat-orders").textContent = number.format(deliveries().length);
  $("stat-vehicles").textContent = number.format(appState.vehicles.length);
  $("stat-routes").textContent = number.format(appState.routes.length);
  $("stat-total-demand").textContent = number.format(demand);
  $("stat-total-capacity").textContent = number.format(capacity);
  $("stat-total-distance").textContent =
    `${number.format(appState.routes.reduce((sum, r) => sum + r.total_distance, 0))} km`;
  $("planning-status").textContent =
    demand > capacity
      ? "La demanda supera la capacidad disponible. Añade vehículos o ajusta los pedidos."
      : appState.routes.length
        ? "La planificación está lista. Consulta el mapa y exporta el detalle desde Rutas."
        : "Registra un depósito, añade entregas y vehículos; después genera tu planificación.";
  renderCharts();
}

function renderCharts() {
  charts.forEach((chart) => chart.destroy());
  charts = [];
  const sorted = [...deliveries()]
    .sort((a, b) => b.demand - a.demand)
    .slice(0, 10);
  const muted = getComputedStyle(document.documentElement)
    .getPropertyValue("--text-muted")
    .trim();
  const grid = getComputedStyle(document.documentElement)
    .getPropertyValue("--panel-border")
    .trim();
  const configs = [
    [
      "demandChart",
      "demand-empty",
      sorted.map((o) => o.customer_name),
      sorted.map((o) => o.demand),
      "Unidades",
      "#2563eb",
    ],
    [
      "routeMetricsChart",
      "routes-empty",
      appState.routes.map((r) => vehicleName(r.vehicle_id)),
      appState.routes.map((r) => r.total_distance),
      "Kilómetros",
      "#0d9488",
    ],
  ];
  configs.forEach(([id, emptyId, labels, data, label, color]) => {
    const available = data.length > 0 && typeof Chart !== "undefined";
    $(id).classList.toggle("hidden", !available);
    $(emptyId).classList.toggle("hidden", available);
    if (typeof Chart === "undefined" && data.length)
      $(emptyId).textContent =
        "El gráfico no está disponible. Consulta los datos en las tablas.";
    if (!available) return;
    charts.push(
      new Chart($(id), {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label,
              data,
              backgroundColor: color,
              borderRadius: 4,
              maxBarThickness: 30,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: { legend: { display: false } },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: grid },
              ticks: { color: muted, precision: 0 },
            },
            x: {
              grid: { display: false },
              ticks: { color: muted, maxRotation: 35, font: { size: 10 } },
            },
          },
        },
      }),
    );
  });
}

function emptyRow(columns, title, hint) {
  return `<tr><td colspan="${columns}" class="empty-cell"><strong>${title}</strong>${hint}</td></tr>`;
}

function actionButtons(type, id) {
  return `<div class="actions"><button class="icon-button" data-action="edit" data-type="${type}" data-id="${id}" aria-label="Editar ${type === "order" ? "pedido" : "vehículo"} ${id}" title="Editar"><i class="fa-solid fa-pen" aria-hidden="true"></i></button><button class="icon-button danger" data-action="delete" data-type="${type}" data-id="${id}" aria-label="Eliminar ${type === "order" ? "pedido" : "vehículo"} ${id}" title="Eliminar"><i class="fa-solid fa-trash" aria-hidden="true"></i></button></div>`;
}

function matches(item, key) {
  const query = $("global-search").value.trim().toLocaleLowerCase("es");
  return (
    item[key].toLocaleLowerCase("es").includes(query) ||
    String(item.id).includes(query)
  );
}

function renderOrders() {
  const orders = appState.orders.filter((o) => matches(o, "customer_name"));
  $("orders-count").textContent =
    `${orders.length} de ${appState.orders.length} registros`;
  document.querySelector("#orders-table tbody").innerHTML =
    orders
      .map(
        (o) =>
          `<tr><td class="cell-meta">#${o.id}</td><td><div class="cell-title">${escapeHtml(o.customer_name)}</div>${o.id === depotId() ? '<span class="badge">Depósito</span>' : '<span class="cell-meta">Entrega</span>'}</td><td class="cell-meta">${o.lat.toFixed(4)}, ${o.lng.toFixed(4)}</td><td>${number.format(o.demand)} u.</td><td>${clock(o.window_start)} – ${clock(o.window_end)}</td><td>${actionButtons("order", o.id)}</td></tr>`,
      )
      .join("") ||
    emptyRow(
      6,
      appState.orders.length ? "Sin coincidencias" : "Todavía no hay pedidos",
      appState.orders.length
        ? "Prueba con otro nombre o identificador."
        : "Crea primero el depósito con demanda 0; después añade las entregas.",
    );
}

function renderVehicles() {
  const vehicles = appState.vehicles.filter((v) => matches(v, "name"));
  $("vehicles-count").textContent =
    `${vehicles.length} de ${appState.vehicles.length} vehículos`;
  document.querySelector("#vehicles-table tbody").innerHTML =
    vehicles
      .map(
        (v) =>
          `<tr><td class="cell-meta">#${v.id}</td><td class="cell-title">${escapeHtml(v.name)}</td><td>${number.format(v.capacity)} unidades</td><td>${actionButtons("vehicle", v.id)}</td></tr>`,
      )
      .join("") ||
    emptyRow(
      4,
      appState.vehicles.length
        ? "Sin coincidencias"
        : "Tu flota está por llegar",
      appState.vehicles.length
        ? "Prueba con otro nombre o identificador."
        : "Añade un vehículo y define su capacidad para comenzar.",
    );
}

function renderRoutes() {
  document.querySelector("#routes-table tbody").innerHTML =
    appState.routes
      .map((r) => {
        const sequence = JSON.parse(r.route_sequence).map(
          (id) =>
            appState.orders.find((o) => o.id === id)?.customer_name || `#${id}`,
        );
        return `<tr><td class="cell-meta">#${r.id}</td><td class="cell-title">${escapeHtml(vehicleName(r.vehicle_id))}</td><td class="route-sequence cell-meta">${sequence.map(escapeHtml).join(" → ")}</td><td>${number.format(r.total_distance)} km</td><td>${number.format(r.total_time)} min</td></tr>`;
      })
      .join("") ||
    emptyRow(
      5,
      "Aún no hay una planificación",
      "Genera rutas para consultar las entregas asignadas a cada vehículo.",
    );
}

function renderAnalytics() {
  const routes = appState.routes.map((r) => {
    const stops = JSON.parse(r.route_sequence).filter((id) => id !== depotId());
    const demand = stops.reduce(
      (sum, id) =>
        sum + (appState.orders.find((o) => o.id === id)?.demand || 0),
      0,
    );
    const capacity =
      appState.vehicles.find((v) => v.id === r.vehicle_id)?.capacity || 0;
    return {
      ...r,
      stops: stops.length,
      demand,
      capacity,
      usage: capacity ? (demand / capacity) * 100 : 0,
    };
  });
  $("route-stats-container").innerHTML = routes.length
    ? `<div class="stats-grid">${[
        ["fa-truck", "Vehículos asignados", routes.length, "tx-blue"],
        [
          "fa-location-dot",
          "Entregas planificadas",
          routes.reduce((sum, r) => sum + r.stops, 0),
          "tx-green",
        ],
        [
          "fa-clock",
          "Duración total estimada",
          `${number.format(routes.reduce((sum, r) => sum + r.total_time, 0) / 60)} h`,
          "tx-purple",
        ],
      ]
        .map(
          ([icon, label, value, color]) =>
            `<div class="stat-card glass style-card"><div class="icon-wrap ${color}"><i class="fa-solid ${icon}" aria-hidden="true"></i></div><div class="stat-info"><h3>${label}</h3><p>${value}</p></div></div>`,
        )
        .join("")}</div>`
    : "";
  $("capacity-analysis-container").innerHTML =
    routes
      .map(
        (r) =>
          `<div class="vehicle-card"><div class="vehicle-header"><span>${escapeHtml(vehicleName(r.vehicle_id))}</span><span class="badge">${r.stops} paradas</span></div><div class="detail-row"><span>Carga asignada</span><span class="detail-value">${r.demand} / ${r.capacity} u.</span></div><div class="progress-bar" role="progressbar" aria-label="Carga de ${escapeHtml(vehicleName(r.vehicle_id))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(r.usage)}"><div class="progress-fill" style="width:${Math.min(100, r.usage)}%"></div></div><div class="detail-row"><span>${number.format(r.usage)}% utilizado</span><span>${number.format(r.total_distance)} km</span></div></div>`,
      )
      .join("") ||
    '<p class="empty-panel">Las asignaciones aparecerán al generar las rutas.</p>';
}

function resetMap() {
  mapVersion++;
  mapController?.abort();
  mapSignature = "";
  $("map-iframe").removeAttribute("srcdoc");
  $("map-iframe").src = "about:blank";
  $("map-overlay").classList.remove("hide");
  $("map-overlay").innerHTML =
    '<i class="fa-solid fa-map-location-dot" aria-hidden="true"></i><strong>Tu próxima ruta empieza aquí</strong><p>Genera una planificación para visualizar las entregas en el mapa.</p>';
}

function syncMapTheme() {
  const root = $("map-iframe").contentDocument?.documentElement;
  if (!root) return;
  const styles = getComputedStyle(document.documentElement);
  for (const token of ["--panel-bg", "--panel-border", "--text-main", "--text-muted", "--primary", "--soft", "--font-family"]) {
    root.style.setProperty(token, styles.getPropertyValue(token));
  }
  root.classList.toggle("dark-mode", document.documentElement.classList.contains("dark-mode"));
}

async function refreshMap() {
  if (!appState.routes.length) return;
  const signature = JSON.stringify(appState.routes);
  if (signature === mapSignature) return;
  mapController?.abort();
  mapController = new AbortController();
  const version = ++mapVersion;
  mapSignature = signature;
  $("map-overlay").classList.remove("hide");
  $("map-overlay").innerHTML =
    '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i><strong>Preparando el mapa</strong><p>Consultando el trazado de las rutas…</p>';
  try {
    const response = await fetch("/api/routes/map", {
      signal: mapController.signal,
    });
    if (!response.ok) throw new Error("No se pudo preparar el mapa.");
    const html = await response.text();
    if (version !== mapVersion) return;
    $("map-iframe").onload = () => {
      if (version === mapVersion) {
        syncMapTheme();
        $("map-overlay").classList.add("hide");
        if (appState.screen === "routing") $("map-iframe").contentWindow?.dispatchEvent(new Event("resize"));
      }
    };
    $("map-iframe").srcdoc = html;
  } catch (error) {
    if (error.name === "AbortError" || version !== mapVersion) return;
    mapSignature = "";
    $("map-overlay").innerHTML =
      '<strong>No se pudo cargar el mapa</strong><p>El detalle de las rutas sigue disponible en la tabla.</p><button class="btn btn-secondary" id="retry-map">Reintentar</button>';
    $("retry-map").addEventListener("click", refreshMap);
  }
}

function openModal(type, id) {
  if (appState.busy) return;
  modalTrigger = document.activeElement;
  const form = $(`form-${type}`);
  form.reset();
  $(`${type}-error`).textContent = "";
  form.elements.id.value = "";
  const record = id
    ? (type === "order" ? appState.orders : appState.vehicles).find(
        (item) => item.id === id,
      )
    : null;
  if (record)
    Object.entries(record).forEach(([key, value]) => {
      if (form.elements[key]) form.elements[key].value = value;
    });
  $(`modal-${type}-title`).textContent = record
    ? `Editar ${type === "order" ? "pedido" : "vehículo"} #${id}`
    : type === "order"
      ? "Nuevo pedido"
      : "Añadir vehículo";
  $(`modal-${type}`).classList.remove("hidden");
  document.querySelector(".app-container").inert = true;
  document.body.style.overflow = "hidden";
  form.querySelector('input:not([type="hidden"])').focus();
}

function closeModal(id) {
  if (appState.busy) return;
  $(id).classList.add("hidden");
  document.querySelector(".app-container").inert = false;
  document.body.style.overflow = "";
  modalTrigger?.focus();
}

async function saveRecord(event, type) {
  event.preventDefault();
  if (appState.busy) return;
  const form = event.target,
    data = Object.fromEntries(new FormData(form));
  const id = data.id;
  delete data.id;
  Object.keys(data).forEach((key) => {
    data[key] = ["customer_name", "name"].includes(key)
      ? data[key].trim()
      : Number(data[key]);
  });
  if (!(data.customer_name || data.name)) {
    $(`${type}-error`).textContent = "Escribe un nombre válido.";
    return;
  }
  if (type === "order" && data.window_start > data.window_end) {
    $("order-error").textContent =
      "El fin de la ventana debe ser igual o posterior al inicio.";
    return;
  }
  appState.busy = true;
  updateButtons();
  const button = form.querySelector('[type="submit"]'),
    text = button.textContent;
  button.disabled = true;
  button.textContent = "Guardando…";
  try {
    await api(
      `/${type === "order" ? "orders" : "vehicles"}${id ? `/${id}` : ""}`,
      {
        method: id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      },
    );
    appState.busy = false;
    closeModal(`modal-${type}`);
    showToast(
      `${type === "order" ? "Pedido" : "Vehículo"} guardado. Genera rutas para actualizar la planificación.`,
    );
    await fetchDashboardData();
  } catch (error) {
    $(`${type}-error`).textContent = error.message;
  } finally {
    appState.busy = false;
    button.disabled = false;
    button.textContent = text;
    updateButtons();
  }
}

async function deleteRecord(type, id) {
  if (appState.busy) return;
  const label = type === "order" ? "pedido" : "vehículo";
  if (
    !confirm(
      `¿Eliminar este ${label}? La planificación actual quedará invalidada.`,
    )
  )
    return;
  appState.busy = true;
  updateButtons();
  try {
    await api(`/${type === "order" ? "orders" : "vehicles"}/${id}`, {
      method: "DELETE",
    });
    await fetchDashboardData();
    showToast(`${label === "pedido" ? "Pedido" : "Vehículo"} eliminado.`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    appState.busy = false;
    updateButtons();
  }
}

async function runAction(kind) {
  if (appState.busy) return;
  if (
    kind === "seed" &&
    !confirm(
      "La demostración reemplazará todos los pedidos, vehículos y rutas actuales con datos de República Dominicana. ¿Continuar?",
    )
  )
    return;
  if (
    kind !== "seed" &&
    (appState.orders.length < 2 ||
      !appState.vehicles.length ||
      appState.orders[0].demand !== 0)
  ) {
    showToast(
      "Registra primero un depósito con demanda 0, al menos una entrega y un vehículo.",
      true,
    );
    return;
  }
  appState.busy = true;
  updateButtons();
  const button = $(kind === "seed" ? "btn-seed-data" : "btn-generate-routes"),
    html = button.innerHTML;
  button.innerHTML = `<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> ${kind === "seed" ? "Cargando…" : "Planificando…"}`;
  try {
    await api(kind === "seed" ? "/seed" : "/routes/generate", {
      method: "POST",
    });
    resetMap();
    await fetchDashboardData();
    showToast(
      kind === "seed"
        ? "Demostración cargada. Ya puedes generar rutas."
        : "Planificación lista. Todas las entregas están asignadas.",
    );
  } catch (error) {
    showToast(error.message, true);
  } finally {
    appState.busy = false;
    button.innerHTML = html;
    updateButtons();
  }
}

function exportRoutes() {
  if (!appState.routes.length) return;
  const link = document.createElement("a");
  link.href = "/api/routes/export";
  link.download = "planificacion-rutas.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function applyTheme(dark) {
  document.documentElement.classList.toggle("dark-mode", dark);
  syncMapTheme();
  $("theme-toggle").innerHTML =
    `<i class="fa-solid ${dark ? "fa-sun" : "fa-moon"}" aria-hidden="true"></i>`;
  $("theme-toggle").setAttribute(
    "aria-label",
    `Cambiar a tema ${dark ? "claro" : "oscuro"}`,
  );
  if (appState.loaded) renderCharts();
}

document
  .querySelectorAll(".nav-links a")
  .forEach((link) =>
    link.addEventListener("click", () => navigate(link.dataset.target)),
  );
window.addEventListener("hashchange", () => {
  const screen = location.hash.slice(1);
  if (["dashboard", "orders", "vehicles", "routing"].includes(screen)) navigate(screen);
});
$("global-search").addEventListener("input", () => {
  renderOrders();
  renderVehicles();
  updateButtons();
  if (
    !["orders", "vehicles"].includes(appState.screen) &&
    $("global-search").value.trim()
  ) {
    location.hash = "orders";
    navigate("orders");
  }
});
$("new-order").addEventListener("click", () => openModal("order"));
$("new-vehicle").addEventListener("click", () => openModal("vehicle"));
document
  .querySelectorAll("[data-close]")
  .forEach((button) =>
    button.addEventListener("click", () => closeModal(button.dataset.close)),
  );
document.querySelectorAll(".modal-backdrop").forEach((backdrop) =>
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) closeModal(backdrop.id);
  }),
);
document.addEventListener("keydown", (event) => {
  const modal = document.querySelector(".modal-backdrop:not(.hidden)");
  if (!modal) return;
  if (event.key === "Escape") closeModal(modal.id);
  if (event.key === "Tab") {
    const elements = [
      ...modal.querySelectorAll(
        'button:not(:disabled), input:not([type="hidden"]):not(:disabled)',
      ),
    ];
    const first = elements[0],
      last = elements.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === last) {
      first.focus();
      event.preventDefault();
    }
  }
});
document.querySelectorAll("#orders-table, #vehicles-table").forEach((table) =>
  table.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button || button.disabled) return;
    const id = Number(button.dataset.id);
    if (button.dataset.action === "edit") openModal(button.dataset.type, id);
    else deleteRecord(button.dataset.type, id);
  }),
);
$("form-order").addEventListener("submit", (event) =>
  saveRecord(event, "order"),
);
$("form-vehicle").addEventListener("submit", (event) =>
  saveRecord(event, "vehicle"),
);
$("btn-generate-routes").addEventListener("click", () => runAction("generate"));
$("btn-seed-data").addEventListener("click", () => runAction("seed"));
$("retry-data").addEventListener("click", fetchDashboardData);
$("export-routes").addEventListener("click", exportRoutes);
$("theme-toggle").addEventListener("click", () => {
  const dark = !document.documentElement.classList.contains("dark-mode");
  applyTheme(dark);
  try {
    localStorage.setItem("theme", dark ? "dark" : "light");
  } catch {
    /* Theme works without storage. */
  }
});
try {
  applyTheme(localStorage.getItem("theme") === "dark");
} catch {
  applyTheme(false);
}
updateButtons();
navigate(location.hash.slice(1));
fetchDashboardData();
