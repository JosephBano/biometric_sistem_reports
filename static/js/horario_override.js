// Override (horario personalizado) por persona.
// Usa la API JSON `/api/horarios-override` (ADR-0003 / Tarea 5.1).
(function () {
    const form = document.getElementById('form-override');
    const tbody = document.getElementById('tabla-overrides');
    if (!form) return;

    function load() {
        if (typeof apiCall !== 'function') return;
        apiCall('/api/horarios-override')
            .then(data => render(data.overrides || []))
            .catch(() => {});
    }

    function render(overrides) {
        if (!overrides || overrides.length === 0) {
            tbody.innerHTML =
                '<tr><td colspan="6" class="text-center py-4 text-muted">' +
                'No hay personalizados.</td></tr>';
            return;
        }
        tbody.innerHTML = overrides.map(o => `
            <tr>
                <td>${o.persona_id || '—'}</td>
                <td>${o.nombre_plantilla || o.plantilla_id || '—'}</td>
                <td>${o.fecha_inicio || '—'}</td>
                <td>${o.fecha_fin || '—'}</td>
                <td>${o.notas || '—'}</td>
                <td><button class="btn btn-sm btn-outline-secondary"
                            onclick="cerrarOverride('${o.id}')">Cerrar</button></td>
            </tr>
        `).join('');
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (typeof apiCall !== 'function') return;
        const payload = Object.fromEntries(new FormData(form).entries());
        apiCall('/api/horarios-override', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(() => {
            if (typeof showSuccess === 'function') showSuccess('Override creado');
            form.reset();
            load();
        })
        .catch(err => {
            if (typeof showError === 'function') {
                showError(err.message || 'Error');
            }
        });
    });

    window.cerrarOverride = function (id) {
        const today = new Date().toISOString().slice(0, 10);
        if (!confirm(`¿Cerrar este override a ${today}?`)) return;
        if (typeof apiCall !== 'function') return;
        apiCall('/api/horarios-override/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha_fin: today }),
        })
        .then(() => {
            if (typeof showSuccess === 'function') showSuccess('Override cerrado');
            load();
        })
        .catch(err => {
            if (typeof showError === 'function') {
                showError(err.message || 'Error');
            }
        });
    };

    load();
})();
