let syncJobInterval = null;
let _biometricPersonCount = 0;

document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchDispositivos();
    const interval = setInterval(() => { fetchStatus(); fetchDispositivos(); }, 30000);
    fetchEstadoHorarios();
});

// ── Estado global (estadísticas agregadas) ─────────────────────────────────
function fetchStatus() {
    apiCall('/api/estado-sync')
        .then(data => {
            _biometricPersonCount = data.personas_en_db || 0;
            updateAggregateStats(data);
            fetchEstadoHorarios();
        })
        .catch(() => {});
}

function updateAggregateStats(data) {
    const el = id => document.getElementById(id);

    if (el('status-total')) el('status-total').textContent = (data.total_registros || 0).toLocaleString('es');
    if (el('status-personas')) el('status-personas').textContent = data.personas_en_db || 0;

    if (el('status-ultima-sync')) {
        if (data.ultima_sync) {
            const ts = new Date(data.ultima_sync.fecha_sync);
            el('status-ultima-sync').textContent =
                ts.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) +
                ' (+' + data.ultima_sync.registros_nuevos + ')';
        } else {
            el('status-ultima-sync').textContent = 'Nunca';
        }
    }

    const capMax = data.capacidad_maxima || 80000;
    const capOcupada = data.registros_en_dispositivo || 0;
    const pct = data.porcentaje_ocupado || 0;

    if (el('status-capacidad-ocupada')) el('status-capacidad-ocupada').textContent = capOcupada.toLocaleString('es');
    if (el('status-capacidad-max')) el('status-capacidad-max').textContent = capMax.toLocaleString('es');
    if (el('status-capacidad-pct')) el('status-capacidad-pct').textContent = pct + '%';

    const bar = el('status-capacidad-bar');
    if (bar) {
        bar.style.width = pct + '%';
        bar.className = 'progress-bar';
        if (pct >= 85) bar.className += ' bg-danger';
        else if (pct >= 75) bar.className += ' bg-warning';
        else if (pct >= 60) bar.className += ' bg-info';
        else bar.className += ' bg-success';
    }

    const divWarning = el('status-capacidad-warning');
    const spanDias = el('status-capacidad-dias');
    if (divWarning && spanDias) {
        if (pct >= 60) {
            divWarning.classList.remove('d-none');
            spanDias.textContent = data.dias_para_llenado || 0;
        } else {
            divWarning.classList.add('d-none');
        }
    }
}

// ── Listado de dispositivos (por dispositivo) ──────────────────────────────
function fetchDispositivos() {
    apiCall('/api/dispositivos')
        .then(data => {
            if (!data.dispositivos || data.dispositivos.length === 0) {
                document.getElementById('dispositivos-container').innerHTML =
                    '<div class="text-muted small text-center py-3">No hay dispositivos registrados. ' +
                    '<a href="/admin/dispositivos">Agregar uno</a>.</div>';
                return;
            }
            renderDispositivos(data.dispositivos);
        })
        .catch(() => {
            const c = document.getElementById('dispositivos-container');
            if (c) c.innerHTML = '<div class="text-muted small py-2">No disponible.</div>';
        });
}

function renderDispositivos(dispositivos) {
    const container = document.getElementById('dispositivos-container');
    if (!container) return;

    container.innerHTML = dispositivos.map((d, i) => {
        const e = d.sync_estado || {};
        const online = e.accesible;
        const dotClass = online === true ? 'dot-green' : (online === false ? 'dot-red' : 'dot-gray');
        const dotTitle = online === true ? 'En línea' : (online === false ? 'Sin conexión' : 'Estado desconocido');
        const driver = (d.driver || 'zk').toUpperCase();
        const badgeColor = (d.driver || 'zk') === 'hikvision' ? 'info' : 'primary';
        const lastSync = e.ultima_sync
            ? new Date(e.ultima_sync).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
            : 'Sin sync';
        const borderClass = i < dispositivos.length - 1 ? 'border-bottom' : '';

        return `<div class="d-flex align-items-center gap-2 py-2 ${borderClass}" style="font-size:0.85rem;">
            <span class="status-dot ${dotClass} flex-shrink-0" title="${dotTitle}"></span>
            <span class="fw-semibold flex-grow-1 text-truncate" style="max-width:130px;" title="${d.nombre}">${d.nombre}</span>
            <span class="text-muted" style="font-size:0.72rem;">${d.ip}:${d.puerto}</span>
            <span class="badge bg-${badgeColor} bg-opacity-10 text-${badgeColor} border border-${badgeColor} border-opacity-25 fw-normal" style="font-size:0.7rem;">${driver}</span>
            <span class="text-muted d-none d-lg-inline" style="font-size:0.72rem;" title="Última sync">${lastSync}</span>
            <button class="btn btn-outline-secondary btn-sm py-0 px-1 flex-shrink-0" style="font-size:0.7rem;"
                onclick="iniciarSyncDispositivo('${d.id}')" title="Sincronizar este dispositivo">
                <span class="material-symbols-outlined" style="font-size:0.85rem;vertical-align:-2px;">sync</span>
            </button>
        </div>`;
    }).join('');
}

function iniciarSyncDispositivo(id) {
    apiCall('/api/dispositivos/' + id + '/sync', { method: 'POST' })
        .then(() => {
            showSuccess('Sincronización iniciada.');
            setTimeout(() => { fetchStatus(); fetchDispositivos(); }, 3000);
        })
        .catch(err => showError('Error al sincronizar: ' + err.message));
}

// ── Horarios ───────────────────────────────────────────────────────────────
function fetchEstadoHorarios() {
    apiCall('/api/horarios/estado')
        .then(data => {
            const statusDot = document.getElementById('horarios-dot');
            const statusText = document.getElementById('horarios-status-text');
            const detalles = document.getElementById('horarios-detalles');

            if (data.cargados) {
                statusDot.className = 'status-dot dot-green';
                statusText.innerHTML = `${data.total} personas configuradas`;

                detalles.style.display = 'block';
                document.getElementById('stat-semana').textContent = `${data.con_semana} sem`;
                document.getElementById('stat-mes').textContent = `${data.con_mes} mes`;
                document.getElementById('stat-almuerzo').textContent = `${data.con_almuerzo} con almuerzo`;

                if (_biometricPersonCount > 0) {
                    const cobertura = Math.min(100, Math.round((data.total / _biometricPersonCount) * 100));
                    let statCobertura = document.getElementById('stat-cobertura');
                    if (!statCobertura) {
                        const container = document.querySelector('#horarios-detalles .d-flex');
                        statCobertura = document.createElement('span');
                        statCobertura.id = 'stat-cobertura';
                        statCobertura.className = 'badge bg-primary bg-opacity-10 text-primary fw-bold border border-primary border-opacity-25';
                        container.appendChild(statCobertura);
                    }
                    statCobertura.textContent = `${cobertura}% cobertura`;
                    statCobertura.title = `${data.total} de ${_biometricPersonCount} personas del biométrico tienen horario.`;
                }
                if (data.actualizado_en) {
                    const ts = new Date(data.actualizado_en);
                    document.getElementById('stat-actualizado').textContent =
                        ts.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }) + ' ' +
                        ts.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
                }
            } else {
                statusDot.className = 'status-dot dot-red';
                statusText.innerHTML = 'Falta cargar el archivo de horarios';
                detalles.style.display = 'none';
            }
        });
}

// ── Sincronizar todos ──────────────────────────────────────────────────────
function iniciarSync() {
    document.getElementById('sync-progress').style.display = 'block';
    document.getElementById('btn-sync').disabled = true;
    updateSyncUI({ estado: 'conectando' });

    apiCall('/api/sincronizar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    })
        .then(data => {
            pollSyncJob(data.job_id);
        })
        .catch(err => {
            showError('Error iniciando sincronización: ' + err.message);
            resetSyncUI();
        });
}

function pollSyncJob(jobId) {
    if (syncJobInterval) clearInterval(syncJobInterval);
    syncJobInterval = setInterval(() => {
        apiCall('/api/sync-status/' + jobId)
            .then(data => {
                updateSyncUI(data);
                if (data.estado === 'completado') {
                    clearInterval(syncJobInterval);
                    resetSyncUI();
                    fetchStatus();
                    fetchDispositivos();
                    showSuccess('Sincronización completada. ' + data.registros_nuevos + ' registro(s) nuevos guardados.');
                } else if (data.estado === 'error') {
                    clearInterval(syncJobInterval);
                    resetSyncUI();
                    showError('Error en sincronización: ' + (data.detalle || 'Error desconocido'));
                }
            });
    }, 2000);
}

function updateSyncUI(data) {
    const mensajes = {
        conectando: 'Conectando al dispositivo...',
        obteniendo_usuarios: 'Obteniendo lista de usuarios...',
        descargando_marcaciones: 'Descargando marcaciones del dispositivo (puede tardar)...',
        procesando: 'Procesando y filtrando marcaciones...',
        completado: 'Completado',
        error: 'Error',
    };
    document.getElementById('sync-progress-text').textContent = mensajes[data.estado] || data.estado;

    let pct = 5;
    if (data.estado === 'procesando' && data.total_dispositivo > 0) {
        pct = Math.round((data.registros_procesados / data.total_dispositivo) * 100);
        document.getElementById('sync-progress-detail').textContent =
            data.registros_procesados.toLocaleString('es') + ' / ' +
            data.total_dispositivo.toLocaleString('es') + ' registros procesados';
    } else if (data.estado === 'completado') {
        pct = 100;
        document.getElementById('sync-progress-detail').textContent = '';
    } else if (data.estado === 'obteniendo_usuarios') {
        pct = 10;
    } else if (data.estado === 'descargando_marcaciones') {
        pct = 30;
    }
    document.getElementById('sync-progress-bar').style.width = pct + '%';
}

function resetSyncUI() {
    document.getElementById('sync-progress').style.display = 'none';
    document.getElementById('btn-sync').disabled = false;
    document.getElementById('sync-progress-bar').style.width = '0%';
    document.getElementById('sync-progress-detail').textContent = '';
}

// ── Limpiar log del dispositivo ─────────────────────────────────────────────
function mostrarConfirmLimpiar() {
    document.getElementById('confirm-limpiar').style.display = 'block';
    document.getElementById('btn-limpiar').style.display = 'none';
}

function cancelarLimpiar() {
    document.getElementById('confirm-limpiar').style.display = 'none';
    document.getElementById('btn-limpiar').style.display = 'inline-block';
    document.getElementById('limpiar-password').value = '';
    document.getElementById('limpiar-error').style.display = 'none';
}

function ejecutarLimpiar() {
    const pwd = document.getElementById('limpiar-password').value;
    const errObj = document.getElementById('limpiar-error');
    errObj.style.display = 'none';

    apiCall('/api/limpiar-dispositivo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmar: true, password: pwd })
    })
        .then(data => {
            showSuccess('Dispositivo limpiado correctamente. Borrados ' + data.registros_borrados + ' registros.');
            cancelarLimpiar();
            fetchStatus();
            fetchDispositivos();
        })
        .catch(err => {
            errObj.textContent = err.message;
            errObj.style.display = 'block';
        });
}
