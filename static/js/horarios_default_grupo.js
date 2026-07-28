// Defaults de grupo funcional: crear + cerrar.
// Usa la API JSON `/api/horarios-default-grupo` (ADR-0003 / Tarea 5.1).
(function () {
    const form = document.getElementById('form-default-grupo');
    const tbody = document.getElementById('tabla-defaults-grupo');
    if (!form) return;

    function populateSelects() {
        if (typeof apiCall !== 'function') return;
        // Cargar grupos funcionales.
        apiCall('/api/grupos-funcionales')
            .then(data => {
                const sel = form.querySelector('[name="grupo_funcional_id"]');
                if (!sel) return;
                sel.innerHTML = '<option value="">Seleccione…</option>' +
                    (data.grupos || []).map(g =>
                        `<option value="${g.id}">${g.nombre || g.codigo}</option>`
                    ).join('');
            })
            .catch(() => {});
    }

    function load() {
        populateSelects();
        if (typeof apiCall !== 'function') return;
        apiCall('/api/horarios-default-grupo')
            .then(data => render(data.defaults || []))
            .catch(() => {});
    }

    function render(defaults) {
        if (!defaults || defaults.length === 0) {
            tbody.innerHTML =
                '<tr><td colspan="6" class="text-center py-4 text-muted">' +
                'No hay defaults configurados.</td></tr>';
            return;
        }
        tbody.innerHTML = defaults.map(d => `
            <tr>
                <td>${d.grupo_funcional_nombre || d.codigo_gf || '—'}</td>
                <td>${d.nombre_plantilla || d.plantilla_id || '—'}</td>
                <td>${d.prioridad}</td>
                <td>${d.fecha_inicio || '—'}</td>
                <td>${d.fecha_fin || '—'}</td>
                <td><button class="btn btn-sm btn-outline-secondary"
                            onclick="cerrarDefault('${d.id}')">Cerrar</button></td>
            </tr>
        `).join('');
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (typeof apiCall !== 'function') return;
        const payload = Object.fromEntries(new FormData(form).entries());
        const prio = parseInt(payload.prioridad || 0, 10);
        payload.prioridad = isNaN(prio) ? 0 : prio;

        apiCall('/api/horarios-default-grupo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(() => {
            if (typeof showSuccess === 'function') showSuccess('Default creado');
            form.reset();
            load();
        })
        .catch(err => {
            if (typeof showError === 'function') {
                showError(err.message || 'Error');
            }
        });
    });

    window.cerrarDefault = function (id) {
        const today = new Date().toISOString().slice(0, 10);
        if (!confirm(`¿Cerrar este default a ${today}?`)) return;
        if (typeof apiCall !== 'function') return;
        apiCall('/api/horarios-default-grupo/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha_fin: today }),
        })
        .then(() => {
            if (typeof showSuccess === 'function') showSuccess('Default cerrado');
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
