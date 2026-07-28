// Catálogo de grupos funcionales: lista + crear + desactivar.
// Usa la API JSON `/api/grupos-funcionales` (ADR-0003 / Tarea 5.1).
(function () {
    const tbody = document.getElementById('tabla-grupos-funcionales');
    if (!tbody) return;

    function render(grupos) {
        if (!grupos || grupos.length === 0) {
            tbody.innerHTML =
                '<tr><td colspan="6" class="text-center py-4 text-muted">' +
                'No hay grupos funcionales creados.</td></tr>';
            return;
        }
        tbody.innerHTML = grupos.map(g => `
            <tr>
                <td><code>${g.codigo || g.nombre}</code></td>
                <td>${g.nombre || ''}</td>
                <td>${g.orden ?? 0}</td>
                <td>${g.activo
                    ? '<span class="badge bg-success">Activo</span>'
                    : '<span class="badge bg-secondary">Inactivo</span>'}</td>
                <td>${g.activo
                    ? `<button class="btn btn-sm btn-outline-secondary"
                              onclick="desactivar('${g.id}')">Desactivar</button>`
                    : ''}</td>
            </tr>
        `).join('');
    }

    function load() {
        if (typeof apiCall !== 'function') return;
        apiCall('/api/grupos-funcionales')
            .then(data => render(data.grupos || []))
            .catch(err => {
                if (typeof showError === 'function') {
                    showError(err.message || 'Error cargando grupos');
                }
            });
    }

    const form = document.getElementById('form-nuevo-grupo');
    if (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const fd = new FormData(form);
            const payload = Object.fromEntries(fd.entries());
            if (typeof apiCall !== 'function') return;
            apiCall('/api/grupos-funcionales', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            .then(() => {
                if (typeof showSuccess === 'function') showSuccess('Grupo creado');
                form.reset();
                const modal = bootstrap.Modal.getInstance(
                    document.getElementById('modalNuevoGrupo')
                );
                if (modal) modal.hide();
                load();
            })
            .catch(err => {
                if (typeof showError === 'function') {
                    showError(err.message || 'Error creando grupo');
                }
            });
        });
    }

    window.desactivar = function (id) {
        if (!confirm('¿Desactivar este grupo funcional?')) return;
        if (typeof apiCall !== 'function') return;
        apiCall('/api/grupos-funcionales/' + id, { method: 'DELETE' })
            .then(() => {
                if (typeof showSuccess === 'function') showSuccess('Grupo desactivado');
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
