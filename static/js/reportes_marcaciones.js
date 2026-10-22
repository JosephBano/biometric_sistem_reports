// static/js/reportes_marcaciones.js
// Modulo 2: Modal enterprise de marcaciones por dia, descarga y envio por email

// ── Modal Enterprise de Marcaciones del Día ─────────────────────────────────

window.abrirModalMarcaciones = function (fechaKey) {
    const dia = diasPorFechaReporte[fechaKey];
    if (!dia) return;

    const modalEl = document.getElementById('modalDetalleMarcaciones');
    if (!modalEl) return;
    const modal = new bootstrap.Modal(modalEl);

    const nombreDiaModal = dia.dia_nombre || obtenerDiaSemana(dia.fecha_str || dia.fecha_iso || dia.fecha);
    const fechaModalStr = dia.fecha_str || dia.fecha_iso || dia.fecha;
    document.getElementById('modalMarcacionesTitulo').textContent = `Marcaciones del ${nombreDiaModal ? nombreDiaModal + ' ' : ''}${fechaModalStr}`;
    const subEl = document.getElementById('modalMarcacionesSubtitulo');

    const obsStrLower = (Array.isArray(dia.observaciones) ? dia.observaciones.join(' ') : (dia.observaciones || '')).toLowerCase();
    let badgeLabel = 'Jornada Correcta';
    let badgeBg = '#ecfdf5';
    let badgeColor = '#047857';
    let badgeBorder = '#a7f3d0';
    let badgeIcon = 'check_circle';

    if (dia.justificado) {
        badgeLabel = 'Justificado';
        badgeBg = 'var(--token-color-navy-50, #eef2ff)';
        badgeColor = 'var(--token-color-navy-900, #1e293b)';
        badgeBorder = 'var(--token-color-slate-200, #cbd5e1)';
        badgeIcon = 'verified';
    } else if (dia.estado === 'salida_anticipada_severa' || dia.estado === 'salida_anticipada_leve' || dia.estado === 'salida_anticipada' || obsStrLower.includes('salida ant')) {
        badgeLabel = dia.estado === 'salida_anticipada_leve' ? 'Salida Anticipada Leve' : 'Salida Anticipada';
        badgeBg = '#fef2f2';
        badgeColor = '#b91c1c';
        badgeBorder = '#fecaca';
        badgeIcon = 'logout';
    } else if (dia.estado === 'severa' || dia.estado === 'tardanza_severa') {
        badgeLabel = 'Tardanza Severa';
        badgeBg = '#fef2f2';
        badgeColor = '#b91c1c';
        badgeBorder = '#fecaca';
        badgeIcon = 'warning';
    } else if (dia.estado === 'leve' || dia.estado === 'tardanza_leve') {
        if (obsStrLower.includes('almuerzo')) {
            badgeLabel = 'Exceso Almuerzo';
            badgeBg = '#fffbeb';
            badgeColor = '#b45309';
            badgeBorder = '#fde68a';
            badgeIcon = 'restaurant';
        } else {
            badgeLabel = 'Tardanza Leve';
            badgeBg = '#fffbeb';
            badgeColor = '#b45309';
            badgeBorder = '#fde68a';
            badgeIcon = 'schedule';
        }
    } else if (dia.estado === 'exceso_almuerzo' || dia.estado === 'almuerzo_largo') {
        badgeLabel = 'Exceso Almuerzo';
        badgeBg = '#fffbeb';
        badgeColor = '#b45309';
        badgeBorder = '#fde68a';
        badgeIcon = 'restaurant';
    } else if (dia.estado === 'ausencia' || dia.estado === 'ausente') {
        badgeLabel = 'Ausencia';
        badgeBg = '#fef2f2';
        badgeColor = '#b91c1c';
        badgeBorder = '#fecaca';
        badgeIcon = 'person_off';
    } else if (dia.estado === 'incompleto' || dia.estado === 'anomalia') {
        badgeLabel = 'Incompleto';
        badgeBg = '#fffbeb';
        badgeColor = '#b45309';
        badgeBorder = '#fde68a';
        badgeIcon = 'warning';
    } else if (dia.estado === 'extra') {
        badgeLabel = 'Día Extra';
        badgeBg = 'var(--token-color-navy-50, #eef2ff)';
        badgeColor = 'var(--token-color-navy-900, #1e293b)';
        badgeBorder = 'var(--token-color-slate-200, #cbd5e1)';
        badgeIcon = 'add_circle';
    } else if (dia.estado === 'feriado') {
        badgeLabel = 'Feriado';
        badgeBg = 'var(--token-color-slate-100, #f1f5f9)';
        badgeColor = 'var(--token-color-slate-700, #334155)';
        badgeBorder = 'var(--token-color-slate-200, #cbd5e1)';
        badgeIcon = 'beach_access';
    }

    const badgeHtml = `<span class="rippling-pill" style="background:${badgeBg}; color:${badgeColor}; border-color:${badgeBorder};"><span class="material-symbols-outlined" style="font-size:0.9rem;">${badgeIcon}</span> ${badgeLabel}</span>`;

    subEl.innerHTML = badgeHtml + ` <span class="text-muted">&middot; Colaborador: <strong>${esc(formatearApellidoNombre(ultimaPersonaConsultada) || 'Colaborador')}</strong></span>`;

    const body = document.getElementById('modalMarcacionesBody');

    // Resumen superior del día en el modal
    let summaryHtml = `
        <div class="row g-2 mb-3">
            <div class="col-sm-3 col-6">
                <div class="p-2 bg-light rounded border text-center">
                    <small class="text-muted d-block" style="font-size:0.7rem;">HORARIO PROG.</small>
                    <strong class="text-dark">${esc(dia.hora_programada || '—')}</strong>
                </div>
            </div>
            <div class="col-sm-3 col-6">
                <div class="p-2 bg-light rounded border text-center">
                    <small class="text-muted d-block" style="font-size:0.7rem;">1ª ENTRADA</small>
                    <strong class="text-success">${esc(dia.llegada || '—')}</strong>
                </div>
            </div>
            <div class="col-sm-3 col-6">
                <div class="p-2 bg-light rounded border text-center">
                    <small class="text-muted d-block" style="font-size:0.7rem;">SALIDA FINAL (ÚLTIMA)</small>
                    <strong class="text-primary">${esc(dia.salida || '—')}</strong>
                </div>
            </div>
            <div class="col-sm-3 col-6">
                <div class="p-2 bg-light rounded border text-center">
                    <small class="text-muted d-block" style="font-size:0.7rem;">TIEMPO EN INST.</small>
                    <strong class="text-dark">${esc(dia.tiempo_dentro || '—')}</strong>
                </div>
            </div>
        </div>
    `;

    // Procesar lista de marcaciones del día
    let marcaciones = dia.marcaciones || [];

    // Fallback: si no vino lista de marcaciones pero sí detalle_registros string
    if (marcaciones.length === 0 && dia.detalle_registros) {
        const tokens = dia.detalle_registros.split(' / ');
        marcaciones = tokens.map(tok => {
            const parts = tok.trim().split(' ');
            return {
                tipo: parts[0] ? parts[0].toLowerCase() : '',
                hora: parts[1] || parts[0],
                tipo_raw: parts[0] || '',
                fuente: 'Biométrico'
            };
        });
    }

    if (marcaciones.length === 0) {
        body.innerHTML = summaryHtml + `
            <div class="text-center py-4 text-muted small">
                <span class="material-symbols-outlined d-block mb-2" style="font-size: 2rem; color: var(--token-color-slate-400);">event_busy</span>
                No se registraron marcaciones físicas en el biométrico para este día.
            </div>`;
    } else {
        const rows = marcaciones.map((m, i) => {
            const previo = i > 0 ? marcaciones[i - 1] : null;
            const esTipoSalida = (m.tipo || '').toLowerCase().includes('salida');
            const esTipoEntrada = (m.tipo || '').toLowerCase().includes('entrada');
            const conflicto = previo && ((esTipoSalida && (previo.tipo || '').toLowerCase().includes('salida')) ||
                                         (esTipoEntrada && (previo.tipo || '').toLowerCase().includes('entrada')));

            const pillTipo = esTipoEntrada
                ? '<span class="rippling-pill" style="background:#ecfdf5; color:#047857; border-color:#a7f3d0;"><span class="material-symbols-outlined" style="font-size:0.85rem;">login</span> Entrada</span>'
                : '<span class="rippling-pill rippling-pill-navy"><span class="material-symbols-outlined" style="font-size:0.85rem;">logout</span> Salida</span>';

            const avisoConflicto = conflicto
                ? '<span class="badge bg-warning bg-opacity-10 text-warning border border-warning border-opacity-25 ms-2" style="font-size:0.68rem;">Marcación consecutiva</span>'
                : '';

            return `
                <tr class="${conflicto ? 'table-warning' : ''}">
                    <td class="fw-bold text-dark text-nowrap">
                        <div class="d-flex align-items-center gap-1">
                            <span class="material-symbols-outlined text-muted" style="font-size: 1rem;">schedule</span>
                            <span>${esc(m.hora)}</span>
                        </div>
                    </td>
                    <td>${pillTipo}${avisoConflicto}</td>
                    <td class="text-muted small">${esc(m.tipo_raw || m.tipo || '—')}</td>
                    <td class="text-muted small"><span class="rippling-pill rippling-pill-slate" style="font-size:0.7rem;">${esc(m.fuente || 'Biométrico')}</span></td>
                </tr>
            `;
        }).join('');

        body.innerHTML = summaryHtml + `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h6 class="fw-bold text-dark mb-0" style="font-size: 0.875rem;">Secuencia Cronológica de Marcajes</h6>
                <span class="rippling-pill rippling-pill-slate" style="font-size:0.72rem;">${marcaciones.length} marcaciones registradas</span>
            </div>
            <div class="table-responsive border rounded-3 overflow-hidden">
                <table class="table table-sm table-hover align-middle mb-0">
                    <thead class="rippling-table-header">
                        <tr>
                            <th>Hora Marcación</th>
                            <th>Tipo Normalizado</th>
                            <th>Dato Original ZK</th>
                            <th>Fuente</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    }

    modal.show();
};

// ── Ir al Reporte Detallado con persona pre-seleccionada ─────────────────────

function irAReporteDetallado() {
    const persona = tomSelectPersonaRapida ? tomSelectPersonaRapida.getValue() : '';
    const fi = document.getElementById('fecha-inicio-rapido').value;
    const ff = document.getElementById('fecha-fin-rapido').value;

    const tabDetalladoBtn = document.getElementById('tab-detallado-btn');
    if (tabDetalladoBtn) {
        const bsTab = new bootstrap.Tab(tabDetalladoBtn);
        bsTab.show();
    }

    const modoSelect = document.getElementById('modo');
    if (modoSelect) {
        modoSelect.value = 'persona';
        actualizarVisibilidadModo();
    }

    if (fi) { const el = document.getElementById('fecha-inicio'); if (el) el.value = fi; }
    if (ff) { const el = document.getElementById('fecha-fin'); if (el) el.value = ff; }

    if (persona && tomSelectPersonaRpt) {
        setTimeout(() => {
            tomSelectPersonaRpt.setValue(persona, true);
        }, 150);
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Descarga Rápida de Archivo (PDF / Word) ───────────────────────────────────

function descargarArchivoRapido(formato = 'pdf') {
    const persona = tomSelectPersonaRapida ? tomSelectPersonaRapida.getValue() : ultimaPersonaConsultada;
    if (!persona) return showToast('Por favor, selecciona una persona primero.', 'warning');

    const fi = document.getElementById('fecha-inicio-rapido').value;
    const ff = document.getElementById('fecha-fin-rapido').value;
    if (!fi || !ff) return showToast('Seleccione un período válido.', 'warning');

    const spinner = document.getElementById('loading-spinner');
    const spinnerMsg = document.getElementById('loading-spinner-msg');
    if (spinnerMsg) spinnerMsg.textContent = `Generando archivo ${formato.toUpperCase()} para ${persona}...`;
    if (spinner) spinner.style.display = 'block';

    const payload = {
        fecha_inicio: fi,
        fecha_fin: ff,
        modo: 'persona',
        persona: persona,
        formato: formato,
        filtros: {
            mostrar_ausencias: true,
            mostrar_tardanza_severa: true,
            mostrar_tardanza_leve: true,
            mostrar_almuerzo: true,
            mostrar_incompletos: true,
            mostrar_salida_anticipada: true,
            mostrar_todos_los_dias: true,
            columna_tiempo_dentro: true,
            verificar_horas: true,
            mostrar_tiempo_extra: true,
            reporte_sin_horario: false,
            reporte_todos_usuarios: false,
        },
        excluidos: [],
    };

    fetch(_BASE + '/api/generar-desde-db', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
        .then(r => r.json().then(data => ({ status: r.status, ok: r.ok, body: data })))
        .then(res => {
            if (spinner) spinner.style.display = 'none';
            if (!res.ok) throw new Error(res.body.error || 'Error generando archivo');

            showToast(`Reporte de ${persona} generado. Descargando...`, 'success');

            const a = document.createElement('a');
            a.href = res.body.download_url;
            a.download = res.body.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        })
        .catch(err => {
            if (spinner) spinner.style.display = 'none';
            showToast('Error al generar: ' + err.message, 'danger');
        });
}

function enviarPorEmailRapido() {
    const persona = tomSelectPersonaRapida ? tomSelectPersonaRapida.getValue() : ultimaPersonaConsultada;
    if (!persona) return showToast('Debe seleccionar una persona.', 'warning');

    const emailInput = document.getElementById('email-destino-rapido');
    const email = emailInput ? emailInput.value.trim() : '';
    if (!email) return showToast('Debe ingresar un correo electrónico.', 'warning');
    if (!email.includes('@') || !email.includes('.')) return showToast('Formato de correo inválido.', 'warning');

    const fi = document.getElementById('fecha-inicio-rapido').value;
    const ff = document.getElementById('fecha-fin-rapido').value;
    if (!fi || !ff) return showToast('Debe seleccionar un rango de fechas.', 'warning');

    const spinner = document.getElementById('loading-spinner');
    const spinnerMsg = document.getElementById('loading-spinner-msg');
    if (spinnerMsg) spinnerMsg.textContent = `Enviando informe por correo a ${email}...`;
    if (spinner) spinner.style.display = 'block';

    const payload = {
        fecha_inicio: fi,
        fecha_fin: ff,
        persona: persona,
        email: email,
        filtros: {
            mostrar_ausencias: true,
            mostrar_tardanza_severa: true,
            mostrar_tardanza_leve: true,
            mostrar_almuerzo: true,
            mostrar_incompletos: true,
            mostrar_salida_anticipada: true,
            mostrar_todos_los_dias: true,
            columna_tiempo_dentro: true,
            verificar_horas: true,
            mostrar_tiempo_extra: true,
        },
        excluidos: [],
    };

    fetch(_BASE + '/api/reportes/enviar-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json().then(data => ({ status: r.status, ok: r.ok, body: data })))
        .then(res => {
            if (spinner) spinner.style.display = 'none';
            if (!res.ok) throw new Error(res.body.error || 'Error al enviar correo');
            showToast(res.body.message || `Reporte enviado por correo correctamente a ${email}`, 'success');
            if (emailInput) emailInput.value = '';
        })
        .catch(err => {
            if (spinner) spinner.style.display = 'none';
            showToast('Error al enviar: ' + err.message, 'danger');
        });
}

