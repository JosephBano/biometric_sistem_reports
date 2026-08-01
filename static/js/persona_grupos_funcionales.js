// Asigna personas a grupos funcionales con vigencia.
// Usa el API JSON `/api/personas/<id>/grupos-funcionales`
// (ADR-0003 / Tarea 5.1).
(function () {
    const form = document.getElementById('form-pgf');
    if (!form) return;

    function load() {
        if (typeof apiCall !== 'function') return;
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

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (typeof apiCall !== 'function') return;
        const fd = new FormData(form);
        const payload = Object.fromEntries(fd.entries());
        payload.es_principal = fd.has('es_principal');
        // El endpoint requiere persona_id en URL; la vista debe
        // inyectarlo. Aquí asumimos una sola persona de la vista.
        const personaId = (typeof CURRENT_PERSONA_ID !== 'undefined')
            ? CURRENT_PERSONA_ID
            : fd.get('persona_id');
        if (!personaId) {
            if (typeof showError === 'function') {
                showError('No se puede determinar la persona actual.');
            }
            return;
        }
        apiCall('/api/personas/' + personaId + '/grupos-funcionales', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(() => {
            if (typeof showSuccess === 'function') showSuccess('Asignación creada');
            form.reset();
        })
        .catch(err => {
            if (typeof showError === 'function') {
                showError(err.message || 'Error');
            }
        });
    });

    load();
})();
