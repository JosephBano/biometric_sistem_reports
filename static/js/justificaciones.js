let offcanvasJustificacion = null;
let tomSelectJustPersona = null;

document.addEventListener('DOMContentLoaded', () => {
    // Basic date setup
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const lastDay = new Date(y, now.getMonth() + 1, 0).getDate();
    document.getElementById('filtro-fecha-inicio').value = `${y}-${m}-01`;
    document.getElementById('filtro-fecha-fin').value = `${y}-${m}-${String(lastDay).padStart(2, '0')}`;
    document.getElementById('just-fecha').value = `${y}-${m}-${String(now.getDate()).padStart(2, '0')}`;

    offcanvasJustificacion = new bootstrap.Offcanvas(document.getElementById('offcanvas-justificacion'));

    tomSelectJustPersona = new TomSelect('#just-persona-id', {
        placeholder: 'Buscar persona...',
        allowEmptyOption: true,
        maxOptions: 200,
        create: false,
    });

    cargarJustificaciones();
});

function abrirOffcanvasJustificacion() {
    // Load people for select specifically from horarios because justificaciones need someone with schedule
    apiCall('/horarios')
        .then(data => {
            tomSelectJustPersona.clear();
            tomSelectJustPersona.clearOptions();
            if(data.horarios) {
                data.horarios.forEach(h => {
                    // Valor será ID, y el text será el nombre completo.
                    tomSelectJustPersona.addOption({ value: h.id_usuario, text: `${h.id_usuario} — ${h.nombre}` });
                });
            }
        });

    cambioTipoJustificacion();
    offcanvasJustificacion.show();
}

function cambioTipoJustificacion() {
    const tipo = document.getElementById('just-tipo').value;
    const container = document.getElementById('dynamic-fields-container');
    const dHora = document.getElementById('df-hora_permitida');
    const dDuracion = document.getElementById('df-duracion_permitida');
    const dMedia = document.getElementById('df-media_jornada');

    // Reset visibility
    dHora.style.display = 'none';
    dDuracion.style.display = 'none';
    dMedia.style.display = 'none';
    container.style.display = 'none';

    // Para la Sección C, esto será activo. Por ahora mostramos los campos pero advertimos si backend falla.
    if(tipo === 'tardanza' || tipo === 'salida_anticipada') {
        container.style.display = 'block';
        dHora.style.display = 'block';
    } else if (tipo === 'almuerzo') {
        container.style.display = 'block';
        dDuracion.style.display = 'block';
    } else if (tipo === 'ausencia') {
        container.style.display = 'block';
        dMedia.style.display = 'block';
    }
}

function cargarJustificaciones() {
    const fi = document.getElementById('filtro-fecha-inicio').value;
    const ff = document.getElementById('filtro-fecha-fin').value;
    let url = '/justificaciones';
    if(fi && ff) url += `?fecha_inicio=${fi}&fecha_fin=${ff}`;
    
    apiCall(url)
        .then(data => {
            const tbody = document.getElementById('just-lista');
            if(!tbody) return;

            if (!data.justificaciones || data.justificaciones.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">No se encontraron justificaciones para este período.</td></tr>';
                return;
            }

            const badges = {
                'ausencia': '<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25 px-2">Ausencia</span>',
                'tardanza': '<span class="badge bg-warning bg-opacity-10 text-dark border border-warning border-opacity-25 px-2">Tardanza</span>',
                'almuerzo': '<span class="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25 px-2">Almuerzo</span>',
                'incompleto': '<span class="badge bg-secondary bg-opacity-10 text-secondary border border-secondary border-opacity-25 px-2">Incompleto</span>',
                'salida_anticipada': '<span class="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25 px-2">Salida Ant.</span>'
            };

            const html = data.justificaciones.map(j => {
                const b = badges[j.tipo] || `<span class="badge bg-secondary">${j.tipo}</span>`;
                return `
                    <tr>
                        <td class="fw-semibold text-nowrap">${j.fecha}</td>
                        <td>${j.nombre || ''} <small class="text-muted">(ID: ${j.id_usuario})</small></td>
                        <td>${b}</td>
                        <td class="text-truncate" style="max-width: 250px;" title="${j.motivo || ''}">${j.motivo || '<em class="text-muted pl-2">Sin motivo</em>'}</td>
                        <td>${j.aprobado_por || '<span class="text-muted">—</span>'}</td>
                        <td class="text-end">
                            <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="eliminarJustificacion(${j.id})" title="Eliminar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">delete</span></button>
                        </td>
                    </tr>
                `;
            }).join("");
            tbody.innerHTML = html;
        });
}

function agregarJustificacion() {
    const payload = {
        fecha: document.getElementById('just-fecha').value,
        tipo: document.getElementById('just-tipo').value,
        motivo: document.getElementById('just-motivo').value.trim(),
        aprobado_por: document.getElementById('just-aprobado_por').value.trim()
    };
    
    const idUsuario = tomSelectJustPersona.getValue();
    if (!idUsuario) return showError('Debe seleccionar una persona.');
    const option = tomSelectJustPersona.options[idUsuario];
    if(!option) return showError('Opcion de persona invalida');
    
    payload.id_usuario = idUsuario;
    payload.nombre = option.text.split(' — ')[1].trim();

    if (!payload.fecha || !payload.tipo) {
        return showError('Fecha, Persona y Tipo son campos requeridos.');
    }
    
    apiCall('/justificaciones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(() => {
        offcanvasJustificacion.hide();
        document.getElementById('just-motivo').value = '';
        document.getElementById('just-aprobado_por').value = '';
        cargarJustificaciones();
        showSuccess('Justificación agregada correctamente.');
    })
    .catch(err => showError(`Error creando justificación: ${err.message}`));
}

function eliminarJustificacion(jid) {
    if (!confirm(`¿Eliminar la justificación ID ${jid}?`)) return;
    apiCall(`/justificaciones/${jid}`, { method: 'DELETE' })
        .then(() => {
            cargarJustificaciones();
            showSuccess('Justificación eliminada.');
        })
        .catch(err => showError(err.message));
}
