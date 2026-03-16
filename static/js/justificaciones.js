let offcanvasJustificacion = null;
let tomSelectJustPersona = null;
let _horariosJust = []; // Cache de horarios para calcular almuerzo_min del permiso
let justificacionEditandoId = null;

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
    justificacionEditandoId = null;
    document.getElementById('offcanvasJustificacionLabel').textContent = 'Nueva Justificación';
    const btnSubmit = document.querySelector('#offcanvas-justificacion .offcanvas-footer .btn-primary');
    if (btnSubmit) {
        btnSubmit.textContent = 'Crear y Aprobar';
        btnSubmit.setAttribute('onclick', 'agregarJustificacion()');
    }

    apiCall('/api/horarios')
        .then(data => {
            _horariosJust = data.horarios || [];
            tomSelectJustPersona.clear();
            tomSelectJustPersona.clearOptions();
            _horariosJust.forEach(h => {
                tomSelectJustPersona.addOption({ value: h.id_usuario, text: `${h.id_usuario} — ${h.nombre}` });
            });
        });

    cambioTipoJustificacion();
    offcanvasJustificacion.show();
}

/** Retorna almuerzo_min del empleado seleccionado, o 0 si no tiene. */
function _getAlmuerzoMinPersona() {
    const id = tomSelectJustPersona ? tomSelectJustPersona.getValue() : null;
    if (!id) return 0;
    const h = _horariosJust.find(x => String(x.id_usuario) === String(id));
    return h ? (parseInt(h.almuerzo_min) || 0) : 0;
}

/** Calcula y actualiza el texto "Permiso neto estimado" en tiempo real. */
function actualizarPermisoNeto() {
    const tipo = document.getElementById('just-tipo').value;
    if (tipo !== 'permiso') return;

    const hSalida  = document.getElementById('just-hora_permitida').value;
    const hRetorno = document.getElementById('just-hora_retorno_permiso').value;
    const incluyeAlm = document.getElementById('just-incluye_almuerzo').checked;
    const netoInfo = document.getElementById('permiso-neto-info');
    const netoValor = document.getElementById('permiso-neto-valor');

    if (!hSalida || !hRetorno) { netoInfo.style.display = 'none'; return; }

    const [hs, ms] = hSalida.split(':').map(Number);
    const [hr, mr] = hRetorno.split(':').map(Number);
    let totalMin = (hr * 60 + mr) - (hs * 60 + ms);

    if (totalMin <= 0) { netoInfo.style.display = 'none'; return; }

    let netoMin = totalMin;
    if (incluyeAlm) {
        const almMin = _getAlmuerzoMinPersona();
        netoMin = Math.max(0, totalMin - almMin);
    }

    const h = Math.floor(netoMin / 60);
    const m = netoMin % 60;
    netoValor.textContent = h > 0 ? `${h}h ${m.toString().padStart(2,'0')}m` : `${m}m`;
    netoInfo.style.display = 'block';
}

/**
 * Función global requerida por base.html para actualizar si fuera necesario
 */
window.checkPendingJustifications = function() {
    apiCall('/api/estado-sync')
        .then(data => {
            const badge = document.querySelector('.nav-link[href*="justificaciones"] .badge');
            if (badge) {
                if (data.justificaciones_pendientes > 0) {
                    badge.textContent = data.justificaciones_pendientes;
                    badge.style.display = 'block';
                } else {
                    badge.style.display = 'none';
                }
            }
        });
};

function toggleCamposRecuperacion() {
    const chk = document.getElementById('just-recuperable');
    const campos = document.getElementById('campos-recuperacion');
    if (chk && campos) {
        campos.style.display = chk.checked ? 'flex' : 'none';
    }
}

function cambioTipoJustificacion() {
    const tipo = document.getElementById('just-tipo').value;
    const container = document.getElementById('dynamic-fields-container');
    const dHora = document.getElementById('df-hora_permitida');
    const dRetorno = document.getElementById('df-hora_retorno_permiso');
    const dDuracion = document.getElementById('df-duracion_permitida');
    const dMedia = document.getElementById('df-media_jornada');
    const dRecuperable = document.getElementById('df-recuperable');
    const panelBreaks = document.getElementById('panel-categorizacion-breaks');

    const dIncluyeAlm = document.getElementById('df-incluye_almuerzo');

    // Reset visibility
    dHora.style.display = 'none';
    dRetorno.style.display = 'none';
    dDuracion.style.display = 'none';
    dMedia.style.display = 'none';
    if (dRecuperable) dRecuperable.style.display = 'none';
    dIncluyeAlm.style.display = 'none';
    container.style.display = 'none';
    panelBreaks.style.display = 'none';
    document.getElementById('permiso-neto-info').style.display = 'none';

    if (tipo === 'tardanza' || tipo === 'salida_anticipada') {
        container.style.display = 'block';
        dHora.style.display = 'block';
        if (dRecuperable && tipo === 'tardanza') dRecuperable.style.display = 'block';
    } else if (tipo === 'almuerzo') {
        container.style.display = 'block';
        dDuracion.style.display = 'block';
    } else if (tipo === 'ausencia') {
        container.style.display = 'block';
        dMedia.style.display = 'block';
    } else if (tipo === 'incompleto') {
        panelBreaks.style.display = 'block';
    } else if (tipo === 'permiso') {
        container.style.display = 'block';
        dHora.style.display = 'block';
        dRetorno.style.display = 'block';
        dIncluyeAlm.style.display = 'block';
        if (dRecuperable) dRecuperable.style.display = 'block';
        actualizarPermisoNeto();
    }
}

function cargarJustificaciones() {
    const fi = document.getElementById('filtro-fecha-inicio').value;
    const ff = document.getElementById('filtro-fecha-fin').value;
    let url = '/api/justificaciones';
    if(fi && ff) url += `?fecha_inicio=${fi}&fecha_fin=${ff}`;
    
    apiCall(url)
        .then(data => {
            const tbody = document.getElementById('just-lista');
            if(!tbody) return;

            if (!data.justificaciones || data.justificaciones.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No se encontraron justificaciones para este período.</td></tr>';
                return;
            }

            const badges = {
                'ausencia': '<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25 px-2">Ausencia</span>',
                'tardanza': '<span class="badge bg-warning bg-opacity-10 text-dark border border-warning border-opacity-25 px-2">Tardanza</span>',
                'almuerzo': '<span class="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25 px-2">Almuerzo</span>',
                'incompleto': '<span class="badge bg-secondary bg-opacity-10 text-secondary border border-secondary border-opacity-25 px-2">Incompleto</span>',
                'salida_anticipada': '<span class="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25 px-2">Salida Ant.</span>'
            };

            const statusBadges = {
                'pendiente': '<span class="badge rounded-pill bg-danger border border-danger border-opacity-50 text-white px-2">Pendiente</span>',
                'aprobada': '<span class="badge rounded-pill bg-success bg-opacity-10 text-success border border-success border-opacity-25 px-2">Aprobada</span>',
                'rechazada': '<span class="badge rounded-pill bg-secondary bg-opacity-10 text-secondary border border-secondary border-opacity-25 px-2">Rechazada</span>'
            };

            const html = data.justificaciones.map(j => {
                const b = badges[j.tipo] || `<span class="badge bg-secondary">${j.tipo}</span>`;
                const sb = statusBadges[j.estado] || `<span class="badge bg-secondary">${j.estado}</span>`;
                
                let rules = [];
                if (j.hora_permitida) rules.push(`Hora: ${j.hora_permitida}`);
                if (j.duracion_permitida_min) rules.push(`Límite: ${j.duracion_permitida_min}m`);
                let rulesStr = rules.length > 0 ? ` <small class="text-primary fw-bold">[${rules.join(', ')}]</small>` : '';
                
                return `
                    <tr>
                        <td class="fw-semibold text-nowrap">${j.fecha}</td>
                        <td>${j.nombre || ''} <small class="text-muted">(ID: ${j.id_usuario})</small></td>
                        <td>${b}</td>
                        <td class="text-truncate" style="max-width: 200px;" title="${j.motivo || ''}">${j.motivo || '<em class="text-muted pl-2">Sin motivo</em>'}${rulesStr}</td>
                        <td>${j.aprobado_por || '<span class="text-muted">—</span>'}</td>
                        <td>${sb}</td>
                        <td class="text-end">
                            <div class="d-flex gap-1 justify-content-end">
                            ${j.estado === 'pendiente' ? `
                                <button class="btn btn-sm btn-success py-0 px-2" onclick="cambiarEstadoJustificacion(${j.id}, 'aprobada')" title="Aprobar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">check_circle</span></button>
                                <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="cambiarEstadoJustificacion(${j.id}, 'rechazada')" title="Rechazar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">cancel</span></button>
                            ` : ''}
                                <button class="btn btn-sm btn-outline-primary py-0 px-2" onclick="abrirEditarJustificacion(${j.id})" title="Editar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">edit</span></button>
                                <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="eliminarJustificacion(${j.id})" title="Eliminar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">delete</span></button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");
            tbody.innerHTML = html;
        })
        .catch(err => {
            const tbody = document.getElementById('just-lista');
            if(tbody) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">Error al cargar datos: ${err.message}</td></tr>`;
            }
        });
}

function cambiarEstadoJustificacion(jid, nuevoEstado) {
    apiCall(`/api/justificaciones/${jid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ estado: nuevoEstado })
    })
    .then(() => {
        cargarJustificaciones();
        showSuccess(`Justificación ${nuevoEstado} correctamente.`);
        if(window.checkPendingJustifications) window.checkPendingJustifications();
    })
    .catch(err => showError(err.message));
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
    
    const hPermitida = document.getElementById('just-hora_permitida').value;
    const hRetorno = document.getElementById('just-hora_retorno_permiso').value;
    const durPermitida = document.getElementById('just-duracion_permitida').value;
    const isMedia = document.getElementById('just-media_jornada').checked;
    
    if (hPermitida && (payload.tipo === 'tardanza' || payload.tipo === 'salida_anticipada' || payload.tipo === 'permiso')) {
        payload.hora_permitida = hPermitida;
    }
    
    if (hRetorno && payload.tipo === 'permiso') {
        payload.hora_retorno_permiso = hRetorno;
    }

    if (payload.tipo === 'permiso') {
        payload.incluye_almuerzo = document.getElementById('just-incluye_almuerzo').checked;
    }

    if (durPermitida && payload.tipo === 'almuerzo') {
        payload.duracion_permitida_min = durPermitida;
    }
    
    if (isMedia && payload.tipo === 'ausencia') {
        payload.motivo = "(Media Jornada) " + payload.motivo;
    }

    const isRecuperable = document.getElementById('just-recuperable') ? document.getElementById('just-recuperable').checked : false;
    if (isRecuperable && (payload.tipo === 'tardanza' || payload.tipo === 'permiso')) {
        payload.recuperable = true;
        payload.fecha_recuperacion = document.getElementById('just-fecha_recuperacion').value;
        payload.hora_recuperacion = document.getElementById('just-hora_recuperacion').value;
    }
    
    apiCall('/api/justificaciones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(() => {
        offcanvasJustificacion.hide();
        document.getElementById('just-motivo').value = '';
        document.getElementById('just-aprobado_por').value = '';
        document.getElementById('just-hora_permitida').value = '';
        document.getElementById('just-hora_retorno_permiso').value = '';
        document.getElementById('just-duracion_permitida').value = '';
        document.getElementById('just-media_jornada').checked = false;
        document.getElementById('just-incluye_almuerzo').checked = false;
        if(document.getElementById('just-recuperable')) document.getElementById('just-recuperable').checked = false;
        if(document.getElementById('just-fecha_recuperacion')) document.getElementById('just-fecha_recuperacion').value = '';
        if(document.getElementById('just-hora_recuperacion')) document.getElementById('just-hora_recuperacion').value = '';
        if(typeof toggleCamposRecuperacion === 'function') toggleCamposRecuperacion();
        document.getElementById('permiso-neto-info').style.display = 'none';
        cargarJustificaciones();
        showSuccess('Justificación agregada correctamente.');
    })
    .catch(err => showError(`Error creando justificación: ${err.message}`));
}

function eliminarJustificacion(jid) {
    if (!confirm(`¿Eliminar la justificación ID ${jid}?`)) return;
    apiCall(`/api/justificaciones/${jid}`, { method: 'DELETE' })
        .then(() => {
            cargarJustificaciones();
            showSuccess('Justificación eliminada.');
        })
        .catch(err => showError(err.message));
}

function categorizarBreak() {
    const idUsuario = tomSelectJustPersona.getValue();
    const fecha = document.getElementById('just-fecha').value;
    const hIni = document.getElementById('cat-hora-ini').value;
    const hFin = document.getElementById('cat-hora-fin').value;
    const tipo = document.getElementById('cat-tipo').value;
    const motivo = document.getElementById('just-motivo').value;

    if (!idUsuario || !fecha || !hIni || !hFin || !tipo) {
        return showError('Todos los campos de categorización son requeridos.');
    }

    apiCall('/api/categorizar-break', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            id_usuario: idUsuario,
            fecha: fecha,
            hora_inicio: hIni,
            hora_fin: hFin,
            categoria: tipo,
            motivo: motivo
        })
    })
    .then(() => {
        showSuccess('Categorización guardada. Se aplicará en el próximo análisis.');
        offcanvasJustificacion.hide();
    })
    .catch(err => showError(`Error al categorizar: ${err.message}`));
}

function abrirEditarJustificacion(jid) {
    justificacionEditandoId = jid;
    document.getElementById('offcanvasJustificacionLabel').textContent = 'Editar Justificación';
    const btnSubmit = document.querySelector('#offcanvas-justificacion .offcanvas-footer .btn-primary');
    if (btnSubmit) {
        btnSubmit.textContent = 'Guardar Cambios';
        btnSubmit.setAttribute('onclick', 'guardarCambiosJustificacion()');
    }

    // Cargar Catálogo de personas primero (o ya está cargado si se abrió antes)
    apiCall('/api/horarios')
        .then(data => {
            _horariosJust = data.horarios || [];
            tomSelectJustPersona.clearOptions();
            _horariosJust.forEach(h => {
                tomSelectJustPersona.addOption({ value: h.id_usuario, text: `${h.id_usuario} — ${h.nombre}` });
            });
            return apiCall(`/api/justificaciones/${jid}`);
        })
        .then(data => {
            const j = data.justificacion;
            tomSelectJustPersona.setValue(j.id_usuario);
            document.getElementById('just-fecha').value = j.fecha;
            document.getElementById('just-tipo').value = j.tipo;
            document.getElementById('just-motivo').value = j.motivo || '';
            document.getElementById('just-aprobado_por').value = j.aprobado_por || '';

            document.getElementById('just-hora_permitida').value = j.hora_permitida || '';
            document.getElementById('just-hora_retorno_permiso').value = j.hora_retorno_permiso || '';
            document.getElementById('just-incluye_almuerzo').checked = j.incluye_almuerzo === 1;
            document.getElementById('just-duracion_permitida').value = j.duracion_permitida_min || '';

            if (document.getElementById('just-recuperable')) {
                document.getElementById('just-recuperable').checked = j.recuperable === 1;
                document.getElementById('just-fecha_recuperacion').value = j.fecha_recuperacion || '';
                document.getElementById('just-hora_recuperacion').value = j.hora_recuperacion || '';
                toggleCamposRecuperacion();
            }

            cambioTipoJustificacion();
            offcanvasJustificacion.show();
        })
        .catch(err => showError(`Error al cargar datos: ${err.message}`));
}

function guardarCambiosJustificacion() {
    if (!justificacionEditandoId) return;

    const payload = {
        fecha: document.getElementById('just-fecha').value,
        tipo: document.getElementById('just-tipo').value,
        motivo: document.getElementById('just-motivo').value.trim(),
        aprobado_por: document.getElementById('just-aprobado_por').value.trim()
    };

    const hPermitida = document.getElementById('just-hora_permitida').value;
    const hRetorno = document.getElementById('just-hora_retorno_permiso').value;
    const durPermitida = document.getElementById('just-duracion_permitida').value;

    if (hPermitida && (payload.tipo === 'tardanza' || payload.tipo === 'salida_anticipada' || payload.tipo === 'permiso')) {
        payload.hora_permitida = hPermitida;
    } else {
        payload.hora_permitida = null;
    }
    
    if (hRetorno && payload.tipo === 'permiso') {
        payload.hora_retorno_permiso = hRetorno;
    } else {
        payload.hora_retorno_permiso = null;
    }

    if (payload.tipo === 'permiso') {
        payload.incluye_almuerzo = document.getElementById('just-incluye_almuerzo').checked;
    }

    if (durPermitida && payload.tipo === 'almuerzo') {
        payload.duracion_permitida_min = durPermitida;
    } else {
         payload.duracion_permitida_min = null;
    }

    const isRecuperable = document.getElementById('just-recuperable') ? document.getElementById('just-recuperable').checked : false;
    if (isRecuperable && (payload.tipo === 'tardanza' || payload.tipo === 'permiso')) {
        payload.recuperable = true;
        payload.fecha_recuperacion = document.getElementById('just-fecha_recuperacion').value;
        payload.hora_recuperacion = document.getElementById('just-hora_recuperacion').value;
    } else {
        payload.recuperable = false;
        payload.fecha_recuperacion = null;
        payload.hora_recuperacion = null;
    }

    apiCall(`/api/justificaciones/${justificacionEditandoId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(() => {
        offcanvasJustificacion.hide();
        cargarJustificaciones();
        showSuccess('Justificación actualizada correctamente.');
    })
    .catch(err => showError(`Error actualizando: ${err.message}`));
}
