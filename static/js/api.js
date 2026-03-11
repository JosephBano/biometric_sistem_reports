// static/js/api.js

function apiCall(url, options = {}) {
    return fetch(url, options)
        .then(response => {
            if (response.status === 401) {
                window.location.href = '/login';
                throw new Error('Sesión expirada. Redirigiendo a acceso...');
            }
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error || 'Error en la solicitud');
                }).catch(() => {
                    throw new Error(`Error HTTP: ${response.status}`);
                });
            }
            return response.json();
        });
}

function showSuccess(msg) {
    const alert = document.getElementById('global-success-alert');
    if(alert) {
        document.getElementById('global-success-msg').textContent = msg;
        alert.style.display = 'block';
        setTimeout(() => alert.style.display = 'none', 5000);
    }
}

function showError(msg) {
    const alert = document.getElementById('global-error-alert');
    if(alert) {
        document.getElementById('global-error-msg').textContent = msg;
        alert.style.display = 'block';
    }
}

function checkPendingJustifications() {
    // Para simplificar, obtenemos todas las justificaciones del mes para ver si hay pendientes
    // Si la DB soporta estado, esto sirve para el badge rojo.
    // Actualmente 'estado' es parte del rediseño.
}
