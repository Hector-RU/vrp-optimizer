// DOM Elements
const navLinks = document.querySelectorAll('.nav-links a');
const sections = document.querySelectorAll('.view-section');
const btnGenerateRoutes = document.getElementById('btn-generate-routes');
const btnSeedData = document.getElementById('btn-seed-data');
const mapOverlay = document.getElementById('map-overlay');
const mapIframe = document.getElementById('map-iframe');

// State Setup
let appState = {
    orders: [],
    vehicles: [],
    routes: []
};

// Navigation Interactivity
navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const target = link.getAttribute('data-target');

        // Update Links
        navLinks.forEach(l => l.classList.remove('active'));
        link.classList.add('active');

        // Update Sections
        sections.forEach(sec => {
            sec.classList.add('hidden');
            if (sec.id === target) {
                sec.classList.remove('hidden');
            }
        });

        if (target === 'routing' && appState.routes.length > 0) {
            refreshMapIframe();
        }
    });
});

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function toggleModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.toggle('hidden');
}

function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    document.getElementById('toast-message').textContent = message;

    if (isError) {
        toast.style.background = '#ef4444';
    } else {
        toast.style.background = '#10b981';
    }

    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('show'), 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.classList.add('hidden'), 300);
    }, 3000);
}

function setLoading(button, loading) {
    if (loading) {
        button.disabled = true;
        button.dataset.originalText = button.innerHTML;
        button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    } else {
        button.disabled = false;
        button.innerHTML = button.dataset.originalText || button.innerHTML;
    }
}

// API Calls & Render
async function fetchDashboardData() {
    try {
        const [ordersRes, vehiclesRes, routesRes] = await Promise.all([
            fetch('/api/orders'),
            fetch('/api/vehicles'),
            fetch('/api/routes')
        ]);

        appState.orders = await ordersRes.json();
        appState.vehicles = await vehiclesRes.json();
        appState.routes = await routesRes.json();

        renderStats();
        renderOrders();
        renderVehicles();
        renderRoutes();

        if (appState.routes.length > 0) {
            refreshMapIframe();
        }

    } catch (e) {
        console.error("Error fetching data", e);
        showToast("Error de conexión con la API", true);
    }
}

let demandChartInstance = null;
let routeMetricsChartInstance = null;

function renderStats() {
    document.getElementById('stat-orders').textContent = appState.orders.length;
    document.getElementById('stat-vehicles').textContent = appState.vehicles.length;
    document.getElementById('stat-routes').textContent = appState.routes.length;

    // Quick Stats Calculation
    const totalDemand = appState.orders.reduce((sum, o) => sum + o.demand, 0);
    const totalCapacity = appState.vehicles.reduce((sum, v) => sum + v.capacity, 0);
    const totalDistance = appState.routes.reduce((sum, r) => sum + r.total_distance, 0);

    document.getElementById('stat-total-demand').textContent = totalDemand;
    document.getElementById('stat-total-capacity').textContent = totalCapacity;
    document.getElementById('stat-total-distance').textContent = totalDistance.toFixed(2) + ' km';

    renderCharts();
}

function renderCharts() {
    const isLightMode = document.documentElement.classList.contains('light-mode');
    const gridColor = isLightMode ? 'rgba(0, 0, 0, 0.1)' : 'rgba(255, 255, 255, 0.1)';
    const borderColor = isLightMode ? '#ffffff' : '#1e293b';

    if (demandChartInstance) demandChartInstance.destroy();

    const sortedOrders = [...appState.orders].sort((a, b) => b.demand - a.demand).slice(0, 10);
    const demandLabels = sortedOrders.map(o => escapeHtml(o.customer_name));
    const demandData = sortedOrders.map(o => o.demand);

    const ctxDemand = document.getElementById('demandChart').getContext('2d');
    demandChartInstance = new Chart(ctxDemand, {
        type: 'bar',
        data: {
            labels: demandLabels,
            datasets: [{
                label: 'Demanda (Unidades)',
                data: demandData,
                backgroundColor: 'rgba(59, 130, 246, 0.7)',
                borderColor: '#3b82f6',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true, grid: { color: gridColor } },
                x: { grid: { display: false } }
            }
        }
    });

    // 2. Route Metrics Chart
    if (routeMetricsChartInstance) routeMetricsChartInstance.destroy();
    
    const ctxRoutes = document.getElementById('routeMetricsChart').getContext('2d');
    
    if (appState.routes.length === 0) {
        // Show empty placeholder or empty chart
        routeMetricsChartInstance = new Chart(ctxRoutes, {
            type: 'doughnut',
            data: {
                labels: ['Sin Rutas'],
                datasets: [{ data: [1], backgroundColor: ['#334155'] }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
        });
        return;
    }

    const routeLabels = appState.routes.map(r => `Veh. #${r.vehicle_id}`);
    const routeDistances = appState.routes.map(r => r.total_distance);

    routeMetricsChartInstance = new Chart(ctxRoutes, {
        type: 'polarArea',
        data: {
            labels: routeLabels,
            datasets: [{
                label: 'Distancia (km)',
                data: routeDistances,
                backgroundColor: [
                    'rgba(59, 130, 246, 0.7)',
                    'rgba(16, 185, 129, 0.7)',
                    'rgba(245, 158, 11, 0.7)',
                    'rgba(139, 92, 246, 0.7)',
                    'rgba(236, 72, 153, 0.7)'
                ],
                borderWidth: 1,
                borderColor: borderColor
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right' }
            },
            scales: {
                r: { grid: { color: gridColor } }
            }
        }
    });
}

function renderOrders() {
    const tbody = document.querySelector('#orders-table tbody');
    tbody.innerHTML = '';
    appState.orders.forEach(o => {
        tbody.innerHTML += `
            <tr>
                <td>#${o.id}</td>
                <td>${escapeHtml(o.customer_name)}</td>
                <td>${o.lat.toFixed(4)}, ${o.lng.toFixed(4)}</td>
                <td>${o.demand}</td>
                <td>${o.window_start} - ${o.window_end}</td>
                <td>
                    <button class="btn btn-primary" style="padding: 6px 10px; background: #3b82f6;" onclick="editOrder(${o.id})">
                        <i class="fa-solid fa-edit"></i>
                    </button>
                    <button class="btn btn-primary" style="padding: 6px 10px; background: #ef4444;" onclick="deleteOrder(${o.id})">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
    });
}

function renderVehicles() {
    const tbody = document.querySelector('#vehicles-table tbody');
    tbody.innerHTML = '';
    appState.vehicles.forEach(v => {
        tbody.innerHTML += `
            <tr>
                <td>#${v.id}</td>
                <td>${escapeHtml(v.name)}</td>
                <td>${v.capacity} u.</td>
                <td>
                    <button class="btn btn-primary" style="padding: 6px 10px; background: #3b82f6;" onclick="editVehicle(${v.id})">
                        <i class="fa-solid fa-edit"></i>
                    </button>
                    <button class="btn btn-primary" style="padding: 6px 10px; background: #ef4444;" onclick="deleteVehicle(${v.id})">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
    });
}

async function deleteOrder(id) {
    if (!confirm('¿Estás seguro de eliminar este pedido?')) return;
    try {
        const res = await fetch(`/api/orders/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showToast("Pedido eliminado");
            fetchDashboardData();
        } else {
            showToast("Error al eliminar", true);
        }
    } catch (e) {
        showToast("Error de conexión", true);
    }
}

async function deleteVehicle(id) {
    if (!confirm('¿Estás seguro de eliminar este vehículo?')) return;
    try {
        const res = await fetch(`/api/vehicles/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showToast("Vehículo eliminado");
            fetchDashboardData();
        } else {
            showToast("Error al eliminar", true);
        }
    } catch (e) {
        showToast("Error de conexión", true);
    }
}

function editOrder(id) {
    const order = appState.orders.find(o => o.id === id);
    if (!order) return;

    const form = document.getElementById('form-order');
    document.getElementById('modal-order-title').textContent = "Editar Pedido #" + id;
    document.getElementById('btn-order-submit').textContent = "Actualizar Pedido";
    
    form.elements['id'].value = order.id;
    form.elements['customer_name'].value = order.customer_name;
    form.elements['lat'].value = order.lat;
    form.elements['lng'].value = order.lng;
    form.elements['demand'].value = order.demand;
    form.elements['window_start'].value = order.window_start;
    form.elements['window_end'].value = order.window_end;

    toggleModal('modal-order');
}

function editVehicle(id) {
    const vehicle = appState.vehicles.find(v => v.id === id);
    if (!vehicle) return;

    const form = document.getElementById('form-vehicle');
    document.getElementById('modal-vehicle-title').textContent = "Editar Vehículo #" + id;
    document.getElementById('btn-vehicle-submit').textContent = "Actualizar Vehículo";

    form.elements['id'].value = vehicle.id;
    form.elements['name'].value = vehicle.name;
    form.elements['capacity'].value = vehicle.capacity;

    toggleModal('modal-vehicle');
}

function prepareNewOrder() {
    const form = document.getElementById('form-order');
    form.reset();
    document.getElementById('order-id').value = "";
    document.getElementById('modal-order-title').textContent = "Registrar Nuevo Pedido";
    document.getElementById('btn-order-submit').textContent = "Guardar Pedido";
    toggleModal('modal-order');
}

function prepareNewVehicle() {
    const form = document.getElementById('form-vehicle');
    form.reset();
    document.getElementById('vehicle-id').value = "";
    document.getElementById('modal-vehicle-title').textContent = "Añadir Vehículo";
    document.getElementById('btn-vehicle-submit').textContent = "Guardar Vehículo";
    toggleModal('modal-vehicle');
}

function renderRoutes() {
    const tbody = document.querySelector('#routes-table tbody');
    tbody.innerHTML = '';

    // Sort array elements correctly due to JSON strings if they returned as strings or lists
    appState.routes.forEach(r => {
        let seq = typeof r.route_sequence === 'string' ? JSON.parse(r.route_sequence) : r.route_sequence;

        tbody.innerHTML += `
            <tr>
                <td>#${r.id}</td>
                <td>Vehículo #${r.vehicle_id}</td>
                <td style="max-width:250px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    ${seq.join(' ➔ ')}
                </td>
                <td>${parseFloat(r.total_distance).toFixed(2)} km</td>
                <td>${parseFloat(r.total_time).toFixed(2)} min</td>
            </tr>
            `;
    });
}

function refreshMapIframe() {
    mapIframe.src = `/api/routes/map?t=${new Date().getTime()}`;
    mapOverlay.classList.add('hide');
}

// Form logic
document.getElementById('form-order').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());

    // Typecastings
    data.lat = parseFloat(data.lat);
    data.lng = parseFloat(data.lng);
    data.demand = parseInt(data.demand);
    data.window_start = parseInt(data.window_start);
    data.window_end = parseInt(data.window_end);

    try {
        const id = data.id;
        delete data.id; // Don't send ID in body for create, and keep it separate for update path if needed

        const url = id ? `/api/orders/${id}` : '/api/orders';
        const method = id ? 'PUT' : 'POST';

        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res.ok) {
            showToast(id ? "Pedido actualizado" : "Pedido guardado exitosamente");
            toggleModal('modal-order');
            e.target.reset();
            fetchDashboardData();
        }
    } catch (e) {
        showToast("Error al guardar pedido", true);
    }
});

document.getElementById('form-vehicle').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    data.capacity = parseInt(data.capacity);

    try {
        const id = data.id;
        delete data.id;

        const url = id ? `/api/vehicles/${id}` : '/api/vehicles';
        const method = id ? 'PUT' : 'POST';

        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res.ok) {
            showToast(id ? "Vehículo actualizado" : "Vehículo guardado exitosamente");
            toggleModal('modal-vehicle');
            e.target.reset();
            fetchDashboardData();
        }
    } catch (e) {
        showToast("Error al guardar vehículo", true);
    }
});

btnGenerateRoutes.addEventListener('click', async () => {
    btnGenerateRoutes.classList.add('opacity-50', 'cursor-not-allowed');
    btnGenerateRoutes.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Ejecutando...';

    try {
        const res = await fetch('/api/routes/generate', { method: 'POST' });
        const json = await res.json();

        if (res.ok) {
            showToast("Rutas optimizadas correctamente!");
            fetchDashboardData();
            setTimeout(() => { refreshMapIframe(); }, 500);
        } else {
            showToast(json.detail || "Error al enrutar. ¿Existen pedidos y vehículos?", true);
        }
    } catch (e) {
        showToast("Error interno del servidor", true);
    } finally {
        btnGenerateRoutes.innerHTML = '<i class="fa-solid fa-microchip"></i> Ejecutar VRP Solver';
        btnGenerateRoutes.classList.remove('opacity-50', 'cursor-not-allowed');
    }
});

if (btnSeedData) {
    btnSeedData.addEventListener('click', async () => {
        if (!confirm('Esto borrará todos los datos actuales e inyectará datos de Dominicana. ¿Continuar?')) return;

        btnSeedData.disabled = true;
        btnSeedData.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sembrando...';

        try {
            const res = await fetch('/api/seed', { method: 'POST' });
            if (res.ok) {
                showToast("Datos inyectados exitosamente");
                await fetchDashboardData();
            } else {
                showToast("Error al inyectar datos", true);
            }
        } catch (e) {
            showToast("Error de conexión", true);
        } finally {
            btnSeedData.innerHTML = '<i class="fa-solid fa-seedling"></i> Inyectar Datos DR';
            btnSeedData.disabled = false;
        }
    });
}

// Theme Logic
const themeToggleBtn = document.getElementById('theme-toggle');
if (themeToggleBtn) {
    const currentTheme = localStorage.getItem('theme');
    if (currentTheme === 'light') {
        document.documentElement.classList.add('light-mode');
        themeToggleBtn.innerHTML = '<i class="fa-solid fa-sun"></i>';
    }

    themeToggleBtn.addEventListener('click', () => {
        document.documentElement.classList.toggle('light-mode');
        const isLight = document.documentElement.classList.contains('light-mode');
        
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
        themeToggleBtn.innerHTML = isLight ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
        
        if (appState.orders.length > 0) {
            renderCharts();
        }
    });
}

// On Load
document.addEventListener('DOMContentLoaded', fetchDashboardData);

