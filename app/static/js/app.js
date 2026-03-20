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
function toggleModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.toggle('hidden');
}

function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    document.getElementById('toast-message').textContent = message;

    // Changing color according to status
    if (isError) {
        toast.style.background = '#ef4444'; // red
    } else {
        toast.style.background = '#10b981'; // green
    }

    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('show'), 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.classList.add('hidden'), 300);
    }, 3000);
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

function renderStats() {
    document.getElementById('stat-orders').textContent = appState.orders.length;
    document.getElementById('stat-vehicles').textContent = appState.vehicles.length;
    document.getElementById('stat-routes').textContent = appState.routes.length;
}

function renderOrders() {
    const tbody = document.querySelector('#orders-table tbody');
    tbody.innerHTML = '';
    appState.orders.forEach(o => {
        tbody.innerHTML += `
            <tr>
                <td>#${o.id}</td>
                <td>${o.customer_name}</td>
                <td>${o.lat.toFixed(4)}, ${o.lng.toFixed(4)}</td>
                <td>${o.lat.toFixed(4)}, ${o.lng.toFixed(4)}</td>
                <td>${o.demand}</td>
                <td>${o.window_start} - ${o.window_end}</td>
                <td>
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
                <td>${v.name}</td>
                <td>${v.capacity} u.</td>
                <td>
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
        const res = await fetch('/api/orders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res.ok) {
            showToast("Pedido guardado exitosamente");
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
        const res = await fetch('/api/vehicles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res.ok) {
            showToast("Vehículo guardado exitosamente");
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

// On Load
document.addEventListener('DOMContentLoaded', fetchDashboardData);

