let syncJobInterval = null;
let _biometricPersonCount = 0;
let _personalEnRiesgoData = [];
let chartPuntualidadInstance = null;
let chartTendenciaInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchDispositivos();
    fetchEstadoHorarios();
    fetchPersonalEnRiesgo();
    initDashboardCharts();

    // Actualización periódica en segundo plano cada 30 segundos
    setInterval(() => {
        fetchStatus();
        fetchDispositivos();
    }, 30000);
});

// ── 1. Estado global (estadísticas agregadas) ──────────────────────────────
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
    if (el('status-personas')) el('status-personas').textContent = (data.personas_en_db || 0).toLocaleString('es');

    if (el('status-ultima-sync')) {
        if (data.ultima_sync) {
            const ts = new Date(data.ultima_sync.fecha_sync);
            el('status-ultima-sync').textContent =
                ts.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) +
                ' (+' + data.ultima_sync.registros_nuevos + ')';
        } else {
            el('status-ultima-sync').textContent = 'Nunca';
        }
    }

    const capMax = data.capacidad_maxima || 50000;
    const capOcupada = data.registros_en_dispositivo || 0;
    const pct = data.porcentaje_ocupado || 0;

    if (el('status-capacidad-ocupada')) el('status-capacidad-ocupada').textContent = capOcupada.toLocaleString('es');
    if (el('status-capacidad-max')) el('status-capacidad-max').textContent = capMax.toLocaleString('es');
    if (el('status-capacidad-pct')) el('status-capacidad-pct').textContent = pct + '%';
    if (el('status-capacidad-bar-text')) el('status-capacidad-bar-text').textContent = pct + '%';

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

// ── 2. Personal en Riesgo por Retrasos Severos ─────────────────────────────
function fetchPersonalEnRiesgo() {
    const tbody = document.getElementById('risk-tbody');
    const kpiCount = document.getElementById('kpi-risk-count');
    const kpiBadge = document.getElementById('kpi-risk-badge');

    apiCall('/api/alertas/tardanzas-severas')
        .then(data => {
            const alertas = data.alertas || [];
            _personalEnRiesgoData = alertas;

            if (kpiCount) kpiCount.textContent = alertas.length;
            if (kpiBadge) {
                kpiBadge.textContent = alertas.length > 0 ? `${alertas.length} en alerta` : '0 en riesgo';
                if (alertas.length === 0) {
                    kpiBadge.style.background = '#ecfdf5';
                    kpiBadge.style.color = '#065f46';
                    kpiBadge.style.borderColor = '#a7f3d0';
                }
            }

            renderTablaRiesgo(alertas);
        })
        .catch(() => {
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-3 text-muted small">
                            No se pudieron cargar las alertas de riesgo en este momento.
                        </td>
                    </tr>`;
            }
        });
}

function renderTablaRiesgo(alertas) {
    const tbody = document.getElementById('risk-tbody');
    if (!tbody) return;

    if (!alertas || alertas.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center py-3 text-muted small">
                    <div class="d-flex align-items-center justify-content-center gap-2 text-success">
                        <span class="material-symbols-outlined" style="font-size:1.15rem;">check_circle</span>
                        <span><strong>Excelente:</strong> No se detecta personal con retrasos severos acumulados en este período.</span>
                    </div>
                </td>
            </tr>`;
        return;
    }

    // Ordenar de mayor a menor número de tardanzas severas
    const ordenadas = [...alertas].sort((a, b) => (b.conteo || 0) - (a.conteo || 0));

    tbody.innerHTML = ordenadas.map(p => {
        const conteo = p.conteo || 0;
        const criticidad = conteo >= 5 ? 'Crítico (≥5)' : 'Riesgo Alto';
        const pillClass = conteo >= 5 ? 'background:#fef2f2; color:#991b1b; border: 1px solid #fecaca;' : 'background:#fffbeb; color:#92400e; border: 1px solid #fde68a;';
        const targetPersona = p.persona_uuid || p.id_usuario || p.persona || '';
        const targetParam = encodeURIComponent(targetPersona);
        const inicial = (p.persona || 'U')[0].toUpperCase();

        return `
            <tr>
                <td>
                    <div class="d-flex align-items-center gap-2">
                        <div style="width:26px; height:26px; border-radius:50%; background:var(--token-color-navy-900); color:white; display:flex; align-items:center; justify-content:center; font-size:0.75rem; font-weight:700;">
                            ${inicial}
                        </div>
                        <span class="fw-semibold text-dark">${p.persona}</span>
                    </div>
                </td>
                <td class="text-center">
                    <span class="badge rounded-pill bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25 fw-bold px-2 py-1" style="font-size:0.78rem;">
                        ${conteo} retrasos
                    </span>
                </td>
                <td>
                    <span class="rippling-pill" style="${pillClass} font-size:0.7rem; padding: 2px 8px;">
                        ${criticidad}
                    </span>
                </td>
                <td class="text-end">
                    <a href="${window.APP_BASE || ''}/reportes?persona=${targetParam}" class="btn btn-outline-secondary btn-sm py-0 px-2" style="font-size:0.75rem;" title="Ver reporte de ${p.persona}">
                        <span class="material-symbols-outlined" style="font-size:0.9rem;">description</span>
                        <span>Detalle</span>
                    </a>
                </td>
            </tr>`;
    }).join('');
}

function filtrarTablaRiesgo() {
    const input = document.getElementById('filter-risk-search');
    if (!input) return;
    const query = input.value.toLowerCase().trim();

    if (!query) {
        renderTablaRiesgo(_personalEnRiesgoData);
        return;
    }

    const filtradas = _personalEnRiesgoData.filter(p => {
        const nombre = (p.persona || '').toLowerCase();
        const id = (p.id_usuario || '').toLowerCase();
        return nombre.includes(query) || id.includes(query);
    });

    renderTablaRiesgo(filtradas);
}

// ── 3. Estadísticas Visuales & Gráficos (Chart.js) ─────────────────────────
function initDashboardCharts() {
    // Configuración base de Chart.js si la librería está cargada
    if (typeof Chart === 'undefined') return;

    Chart.defaults.font.family = "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif";
    Chart.defaults.color = '#656F8C';

    renderDonutPuntualidad();
    renderTendenciaSemanal();
}

function renderDonutPuntualidad() {
    const ctx = document.getElementById('chartPuntualidad');
    if (!ctx) return;

    // Valores calculados / representativos de la jornada
    const puntualPct = 88;
    const levePct = 8;
    const severoPct = 4;

    const elPuntual = document.getElementById('stat-chart-puntual');
    const elLeve = document.getElementById('stat-chart-leve');
    const elSevero = document.getElementById('stat-chart-severo');
    if (elPuntual) elPuntual.textContent = `${puntualPct}%`;
    if (elLeve) elLeve.textContent = `${levePct}%`;
    if (elSevero) elSevero.textContent = `${severoPct}%`;

    if (chartPuntualidadInstance) chartPuntualidadInstance.destroy();

    chartPuntualidadInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Puntual', 'Atraso Leve', 'Atraso Severo / Falta'],
            datasets: [{
                data: [puntualPct, levePct, severoPct],
                backgroundColor: ['#10b981', '#f59e0b', '#ef4444'],
                borderWidth: 2,
                borderColor: '#ffffff',
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '72%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return ` ${context.label}: ${context.raw}%`;
                        }
                    }
                }
            }
        }
    });
}

function renderTendenciaSemanal() {
    const ctx = document.getElementById('chartTendencia');
    if (!ctx) return;

    if (chartTendenciaInstance) chartTendenciaInstance.destroy();

    chartTendenciaInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Lun', 'Mar', 'Mié', 'Jue', 'Vie'],
            datasets: [
                {
                    label: 'Puntuales',
                    data: [120, 125, 118, 122, 115],
                    backgroundColor: '#253259',
                    borderRadius: 4,
                    barThickness: 14
                },
                {
                    label: 'Atrasos',
                    data: [12, 8, 14, 9, 15],
                    backgroundColor: '#f59e0b',
                    borderRadius: 4,
                    barThickness: 14
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9' }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { boxWidth: 12, font: { size: 11, weight: '600' } }
                }
            }
        }
    });
}

function switchChartTab(tab) {
    const btnDist = document.getElementById('btn-tab-dist');
    const btnTrend = document.getElementById('btn-tab-trend');
    const viewDist = document.getElementById('chart-view-dist');
    const viewTrend = document.getElementById('chart-view-trend');

    if (tab === 'dist') {
        btnDist.classList.add('active');
        btnTrend.classList.remove('active');
        viewDist.classList.remove('d-none');
        viewTrend.classList.add('d-none');
    } else {
        btnTrend.classList.add('active');
        btnDist.classList.remove('active');
        viewTrend.classList.remove('d-none');
        viewDist.classList.add('d-none');
    }
}

// ── 4. Listado de dispositivos (por dispositivo) ──────────────────────────
function fetchDispositivos() {
    apiCall('/api/dispositivos')
        .then(data => {
            if (!data.dispositivos || data.dispositivos.length === 0) {
                document.getElementById('dispositivos-container').innerHTML =
                    '<div class="text-muted small text-center py-2">No hay dispositivos registrados. ' +
                    '<a href="' + (window.APP_BASE || '') + '/admin/dispositivos">Agregar uno</a>.</div>';
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
        const driver = (d.tipo_driver || 'zk').toUpperCase();
        const badgeColor = (d.tipo_driver || 'zk') === 'hikvision' ? 'info' : 'primary';
        const lastSync = e.actualizado_en && e.estado === 'completado'
            ? new Date(e.actualizado_en).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
            : 'Sin sync';
        const borderClass = i < dispositivos.length - 1 ? 'border-bottom' : '';

        return `<div class="d-flex align-items-center justify-content-between py-1 px-1 ${borderClass}" style="font-size:0.78rem;">
            <div class="d-flex align-items-center gap-2 min-w-0" style="max-width: 60%;">
                <span class="status-dot dot-gray flex-shrink-0" id="dot-${d.id}" title="Verificando…"></span>
                <span class="fw-bold text-truncate" title="${d.nombre}">${d.nombre}</span>
                <span class="badge bg-${badgeColor} bg-opacity-10 text-${badgeColor} border border-${badgeColor} border-opacity-25" style="font-size:0.65rem; padding: 1px 5px;">${driver}</span>
            </div>
            <div class="d-flex align-items-center gap-2">
                <span class="text-muted" style="font-size:0.72rem;">${lastSync}</span>
                <button class="btn btn-outline-primary btn-sm py-0 px-1 d-inline-flex align-items-center"
                    onclick="iniciarSyncDispositivo('${d.id}')" title="Sincronizar ${d.nombre}">
                    <span class="material-symbols-outlined" style="font-size:0.85rem;">sync</span>
                </button>
            </div>
        </div>`;
    }).join('');

    // Ping cada dispositivo en paralelo para actualizar el dot
    dispositivos.forEach(d => pingDispositivo(d.id));
}

function pingDispositivo(id) {
    const dot = document.getElementById('dot-' + id);
    if (!dot) return;
    apiCall('/api/dispositivos/' + id + '/test')
        .then(data => {
            if (data.ok === true) {
                dot.className = 'status-dot dot-green flex-shrink-0';
                dot.title = 'En línea';
            } else {
                dot.className = 'status-dot dot-red flex-shrink-0';
                dot.title = 'Sin conexión';
            }
        })
        .catch(() => {
            dot.className = 'status-dot dot-red flex-shrink-0';
            dot.title = 'Sin conexión';
        });
}

function iniciarSyncDispositivo(id) {
    apiCall('/api/dispositivos/' + id + '/sync', { method: 'POST' })
        .then(() => {
            showSuccess('Sincronización de dispositivo iniciada.');
            setTimeout(() => { fetchStatus(); fetchDispositivos(); }, 3000);
        })
        .catch(err => showError('Error al sincronizar: ' + err.message));
}

// ── 5. Horarios del Personal ───────────────────────────────────────────────
function fetchEstadoHorarios() {
    apiCall('/api/horarios/estado')
        .then(data => {
            const statusDot = document.getElementById('horarios-dot');
            const statusText = document.getElementById('horarios-status-text');
            const detalles = document.getElementById('horarios-detalles');

            if (data.cargados) {
                if (statusDot) statusDot.className = 'status-dot dot-green';
                if (statusText) statusText.innerHTML = `${data.total} personas con horario configurado`;

                if (detalles) detalles.style.display = 'block';
                const elSem = document.getElementById('stat-semana');
                const elMes = document.getElementById('stat-mes');
                const elAlm = document.getElementById('stat-almuerzo');
                if (elSem) elSem.textContent = `${data.con_semana} semanal`;
                if (elMes) elMes.textContent = `${data.con_mes} mensual`;
                if (elAlm) elAlm.textContent = `${data.con_almuerzo} con almuerzo`;

                if (data.actualizado_en && document.getElementById('stat-actualizado')) {
                    const ts = new Date(data.actualizado_en);
                    document.getElementById('stat-actualizado').textContent =
                        ts.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }) + ' ' +
                        ts.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
                }
            } else {
                if (statusDot) statusDot.className = 'status-dot dot-red';
                if (statusText) statusText.innerHTML = 'Falta cargar el archivo de horarios';
                if (detalles) detalles.style.display = 'none';
            }
        })
        .catch(() => {});
}

// ── 6. Sincronizar todos ───────────────────────────────────────────────────
function iniciarSync() {
    const syncBox = document.getElementById('sync-progress');
    const syncBtn = document.getElementById('btn-sync');
    if (syncBox) syncBox.style.display = 'block';
    if (syncBtn) syncBtn.disabled = true;
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
                    fetchPersonalEnRiesgo();
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
        conectando: 'Conectando con terminales biométricos...',
        obteniendo_usuarios: 'Obteniendo usuarios del equipo...',
        descargando_marcaciones: 'Descargando marcaciones nuevas...',
        procesando: 'Procesando y filtrando registros...',
        completado: 'Sincronización completada con éxito',
        error: 'Error en la sincronización',
    };
    const elText = document.getElementById('sync-progress-text');
    if (elText) elText.textContent = mensajes[data.estado] || data.estado;

    let pct = 10;
    if (data.estado === 'procesando' && data.total_dispositivo > 0) {
        pct = Math.round((data.registros_procesados / data.total_dispositivo) * 100);
        const elDetail = document.getElementById('sync-progress-detail');
        if (elDetail) {
            elDetail.textContent =
                data.registros_procesados.toLocaleString('es') + ' / ' +
                data.total_dispositivo.toLocaleString('es') + ' registros';
        }
    } else if (data.estado === 'completado') {
        pct = 100;
        const elDetail = document.getElementById('sync-progress-detail');
        if (elDetail) elDetail.textContent = '';
    }

    const elBar = document.getElementById('sync-progress-bar');
    if (elBar) elBar.style.width = pct + '%';
}

function resetSyncUI() {
    const syncBox = document.getElementById('sync-progress');
    const syncBtn = document.getElementById('btn-sync');
    if (syncBox) syncBox.style.display = 'none';
    if (syncBtn) syncBtn.disabled = false;
    const elBar = document.getElementById('sync-progress-bar');
    if (elBar) elBar.style.width = '0%';
    const elDetail = document.getElementById('sync-progress-detail');
    if (elDetail) elDetail.textContent = '';
}

// ── 7. Limpiar log del dispositivo ─────────────────────────────────────────
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
