let syncJobInterval = null;
let _biometricPersonCount = 0;

document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    setInterval(fetchStatus, 30000);
    fetchEstadoHorarios();
});

function fetchStatus() {
    apiCall('/api/estado-sync')
        .then(data => {
            _biometricPersonCount = data.personas_en_db || 0;
            updateStatusBar(data);
            fetchEstadoHorarios(); 
        })
        .catch(() => updateStatusBar(null));
}

function updateStatusBar(data) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-device-text');

    if (!data) {
        dot.className = 'status-dot dot-gray';
        text.textContent = 'No se pudo obtener el estado';
        return;
    }

    if (data.dispositivo_accesible) {
        dot.className = 'status-dot dot-green';
        text.textContent = 'Dispositivo en línea (192.168.7.129)';
    } else {
        dot.className = 'status-dot dot-red';
        text.textContent = 'Dispositivo no accesible — modo offline';
    }

    document.getElementById('status-total').textContent = (data.total_registros || 0).toLocaleString('es');
    document.getElementById('status-personas').textContent = data.personas_en_db || 0;

    if (data.ultima_sync) {
        const ts = new Date(data.ultima_sync.fecha_sync);
        document.getElementById('status-ultima-sync').textContent = ts.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) + ' (+' + data.ultima_sync.registros_nuevos + ')';
    } else {
        document.getElementById('status-ultima-sync').textContent = 'Nunca';
    }
}

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
                
                // Cálculo de cobertura
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
                    document.getElementById('stat-actualizado').textContent = ts.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }) + ' ' + ts.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
                }
            } else {
                statusDot.className = 'status-dot dot-red';
                statusText.innerHTML = 'Falta cargar el archivo de horarios';
                detalles.style.display = 'none';
            }
        });
}

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
                    showSuccess(
                        'Sincronización completada. ' +
                        data.registros_nuevos + ' registro(s) nuevos guardados.'
                    );
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
        showSuccess('Dispositivo limpiado correctamente. Bórrados ' + data.registros_borrados + ' registros.');
        cancelarLimpiar();
        fetchStatus();
    })
    .catch(err => {
        errObj.textContent = err.message;
        errObj.style.display = 'block';
    });
}
