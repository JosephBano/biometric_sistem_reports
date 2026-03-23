// static/js/api.js

/**
 * Helper centralizado para llamadas al backend (Sección D.2)
 */
const API = {
    async get(path) {
        const res = await fetch(path);
        if (res.status === 401) { window.location.href = '/login'; return; }
        if (!res.ok) throw await res.json();
        return res.json();
    },
    async post(path, body) {
        const res = await fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (res.status === 401) { window.location.href = '/login'; return; }
        if (!res.ok) throw await res.json();
        return res.json();
    },
    async delete(path) {
        const res = await fetch(path, { method: 'DELETE' });
        if (res.status === 401) { window.location.href = '/login'; return; }
        if (!res.ok) throw await res.json();
        return res.json();
    },
    async patch(path, body) {
        const res = await fetch(path, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (res.status === 401) { window.location.href = '/login'; return; }
        if (!res.ok) throw await res.json();
        return res.json();
    }
};

// Funciones para legacy compatibility o helpers directos
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
    if (typeof showToast === 'function') {
        showToast(msg, 'success');
    } else {
        alert(msg);
    }
}

function showError(msg) {
    if (typeof showToast === 'function') {
        showToast(msg, 'danger');
    } else {
        alert("ERROR: " + msg);
    }
}
