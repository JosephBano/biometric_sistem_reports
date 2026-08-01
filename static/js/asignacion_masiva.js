// Preview y ejecución de asignación masiva con filtros.
// Usa el API JSON `/api/asignacion-masiva/grupo-funcional` (ADR-0003 / Tarea 5.1).
(function () {
    const form = document.getElementById('form-asignacion-masiva');
    const previewBox = document.getElementById('preview-resultado');
    if (!form) return;

    function readPayload() {
        const fd = new FormData(form);
        return {
            grupo_funcional_id_destino: fd.get('grupo_funcional_id_destino'),
            plantilla_id: fd.get('plantilla_id') || null,
            fecha_inicio: fd.get('fecha_inicio'),
            fecha_fin: fd.get('fecha_fin') || null,
            modo: fd.get('modo_override')
                ? 'crear_override'
                : 'asignar_grupo_funcional',
            cerrar_legacy_en_fecha: fd.has('cerrar_legacy_en_fecha'),
            filtros: {
                grupo_id: fd.get('grupo_id') || null,
                tipo_persona_id: fd.get('tipo_persona_id') || null,
                categoria_id: fd.get('categoria_id') || null,
                sede_id: fd.get('sede_id') || null,
            },
        };
    }

    window.previewMasiva = function () {
        if (typeof apiCall !== 'function') return;
        const payload = readPayload();
        apiCall('/api/asignacion-masiva/grupo-funcional/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(data => {
            const body = document.getElementById('preview-body');
            if (!body) return;
            body.innerHTML = `
                <p><strong>${data.matched_count}</strong> personas
                   serán afectadas.</p>
                <details>
                    <summary>Ver primeros 50 IDs</summary>
                    <pre>${(data.affected_persona_ids || []).join('\n')}</pre>
                </details>`;
            if (previewBox) previewBox.style.display = 'block';
        })
        .catch(err => {
            if (typeof showError === 'function') {
                showError(err.message || 'Error en preview');
            }
        });
    };

    window.ejecutarMasiva = function () {
        if (typeof apiCall !== 'function') return;
        const payload = readPayload();
        payload.confirmar = document.getElementById('confirmar').checked;
        if (!payload.confirmar) {
            if (typeof showError === 'function') {
                showError('Marca la casilla de confirmación');
            }
            return;
        }
        apiCall('/api/asignacion-masiva/grupo-funcional', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(data => {
            const msg = `Ejecutado: ${data.membership_created_count} creados, `
                + `${data.skipped_count} skipped`;
            if (typeof showSuccess === 'function') showSuccess(msg);
            if (previewBox) previewBox.style.display = 'none';
        })
        .catch(err => {
            if (typeof showError === 'function') {
                showError(err.message || 'Error ejecutando');
            }
        });
    };
})();
