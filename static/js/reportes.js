let tomSelectPersonaRpt = null;
let tomSelectPersonaRapida = null;
let personasCache = [];
let ultimaPersonaConsultada = '';
let _horariosCache = [];
let offcanvasHorario = null;

// Estado de paginación para el reporte diario en pantalla
let diasReporteActual = [];
let diasPorFechaReporte = {};
let currentPageReportes = 1;
const PAGE_SIZE_REPORTES = 15;

// ── Formateo Visual de Nombres en Memoria (Sin modificar la BD) ─────────────

function formatearApellidoNombre(nombre) {
    if (!nombre || typeof nombre !== 'string') return '';
    const trimmed = nombre.trim();
    if (trimmed.includes(',')) return trimmed;
    const partes = trimmed.split(/\s+/);
    if (partes.length <= 1) return trimmed;
    if (partes.length === 2) return `${partes[1]} ${partes[0]}`;
    if (partes.length === 3) return `${partes[1]} ${partes[2]} ${partes[0]}`;
    if (partes.length >= 4) {
        const nombres = partes.slice(0, -2).join(' ');
        const apellidos = partes.slice(-2).join(' ');
        return `${apellidos} ${nombres}`;
    }
    return trimmed;
}

document.addEventListener('DOMContentLoaded', () => {
    // Inicializar Offcanvas de Horarios si existe
    const elOffcanvas = document.getElementById('offcanvas-horario');
    if (elOffcanvas) {
        offcanvasHorario = new bootstrap.Offcanvas(elOffcanvas);
    }
    cargarHorarios();

    // Inicializar fechas por defecto (Mes actual)
    setMesActual();
    initFechasRapidas();

    // Inicializar TomSelect para Reporte Rápido (solo personas activas)
    tomSelectPersonaRapida = new TomSelect('#persona-rapida', {
        valueField: 'nombre',
        labelField: 'nombre',
        searchField: ['nombre', 'identificacion', 'id_usuario_zk'],
        maxOptions: 1000,
        create: false,
        placeholder: 'Escribe el nombre, cédula o ID biométrico...',
        render: {
            option: function(d, escape) {
                const nombreMostrar = formatearApellidoNombre(d.nombre);
                const meta = [
                    d.identificacion ? 'CI: ' + escape(d.identificacion) : '',
                    d.id_usuario_zk ? 'ZK ID: ' + escape(d.id_usuario_zk) : '',
                ].filter(Boolean).join(' &middot; ');
                return '<div class="py-1">'
                    + '<div class="fw-bold text-dark">' + escape(nombreMostrar) + '</div>'
                    + (meta ? '<div class="text-muted small mt-1">' + meta + '</div>' : '')
                    + '</div>';
            },
            item: function(d, escape) {
                const nombreMostrar = formatearApellidoNombre(d.nombre);
                const zk = d.id_usuario_zk ? ' <span class="text-muted small">(ZK ' + escape(d.id_usuario_zk) + ')</span>' : '';
                return '<div class="fw-semibold text-dark">' + escape(nombreMostrar) + zk + '</div>';
            },
            no_results: function() {
                return '<div class="p-3 text-muted small text-center">No se encontraron personas activas con ese criterio.</div>';
            },
        },
        onChange: function (value) {
            const btnQuickEdit = document.getElementById('btn-quick-edit-persona');
            if (btnQuickEdit) {
                if (value) {
                    btnQuickEdit.classList.remove('d-none');
                    btnQuickEdit.classList.add('d-inline-flex');
                } else {
                    btnQuickEdit.classList.remove('d-inline-flex');
                    btnQuickEdit.classList.add('d-none');
                }
            }
            if (!value) {
                setEstadoVistaRapida('placeholder');
                return;
            }
            consultarReporteRapidoActual();
        }
    });

    // Inicializar TomSelect para Reporte Detallado
    tomSelectPersonaRpt = new TomSelect('#persona', {
        valueField: 'nombre',
        labelField: 'nombre',
        searchField: ['nombre', 'identificacion', 'id_usuario_zk'],
        maxOptions: 1000,
        create: false,
        placeholder: 'Buscar persona activa...',
        render: {
            option: function(d, escape) {
                const nombreMostrar = formatearApellidoNombre(d.nombre);
                const meta = [
                    d.identificacion ? 'CI: ' + escape(d.identificacion) : '',
                    d.id_usuario_zk ? 'ZK ID: ' + escape(d.id_usuario_zk) : '',
                ].filter(Boolean).join(' &middot; ');
                return '<div class="py-1">'
                    + '<div class="fw-bold text-dark">' + escape(nombreMostrar) + '</div>'
                    + (meta ? '<div class="text-muted small mt-1">' + meta + '</div>' : '')
                    + '</div>';
            },
            item: function(d, escape) {
                const nombreMostrar = formatearApellidoNombre(d.nombre);
                const zk = d.id_usuario_zk ? ' <span class="text-muted small">(ZK ' + escape(d.id_usuario_zk) + ')</span>' : '';
                return '<div class="fw-semibold text-dark">' + escape(nombreMostrar) + zk + '</div>';
            },
        }
    });

    actualizarVisibilidadModo();
    cargarPersonasIniciales();

    // Listeners de cambio de fecha para el reporte detallado
    const fInicio = document.getElementById('fecha-inicio');
    const fFin = document.getElementById('fecha-fin');
    if (fInicio) fInicio.addEventListener('change', reloadPersonas);
    if (fFin) fFin.addEventListener('change', reloadPersonas);

    // Exclusividades especiales
    const cSin = document.getElementById('f-sin-horario');
    const cTodos = document.getElementById('f-todos-usuarios');
    if (cSin) {
        cSin.addEventListener('change', function () {
            if (this.checked && cTodos) cTodos.checked = false;
        });
    }
    if (cTodos) {
        cTodos.addEventListener('change', function () {
            if (this.checked && cSin) cSin.checked = false;
        });
    }
});

// ── Carga y Cache de Personas (Solo Activas) ─────────────────────────────────

function cargarPersonasIniciales() {
    fetch(_BASE + '/api/personas/buscar?activo=true')
        .then(r => r.ok ? r.json() : { personas: [] })
        .then(data => {
            if (data.personas) {
                personasCache = data.personas.filter(p => p.activo !== false);
                poblarSelectsPersonas(personasCache);
            }
        })
        .catch(err => {
            console.warn('No se pudo precargar la lista de personas:', err);
        });
}

function cargarPersonasParaFechas(fi, ff) {
    if (!fi || !ff) return;
    fetch(_BASE + '/api/personas/buscar?activo=true')
        .then(r => r.ok ? r.json() : { personas: [] })
        .then(data => {
            if (data.personas) {
                personasCache = data.personas.filter(p => p.activo !== false);
                poblarSelectsPersonas(personasCache);
            }
        })
        .catch(console.error);
}

let personasDisponibles = [];
let personasSeleccionadas = [];
let seleccionadosTempDisponibles = new Set();
let seleccionadosTempElegidos = new Set();

function poblarSelectsPersonas(lista) {
    if (!lista || !Array.isArray(lista)) return;

    // Reporte Rápido
    if (tomSelectPersonaRapida) {
        const urlParams = new URLSearchParams(window.location.search);
        const paramPersona = urlParams.get('persona') || urlParams.get('persona_id');
        const valorActual = tomSelectPersonaRapida.getValue();

        tomSelectPersonaRapida.clear();
        tomSelectPersonaRapida.clearOptions();
        tomSelectPersonaRapida.addOptions(lista);

        if (paramPersona) {
            const found = lista.find(p => p.nombre === paramPersona || p.id === paramPersona || String(p.id_usuario_zk) === String(paramPersona) || p.nombre.toLowerCase() === paramPersona.toLowerCase());
            if (found) {
                tomSelectPersonaRapida.setValue(found.nombre);
            }
        } else if (valorActual && lista.some(p => p.nombre === valorActual)) {
            tomSelectPersonaRapida.setValue(valorActual, true);
        }
    }

    // Reporte Detallado - Individual
    if (tomSelectPersonaRpt) {
        const valorActual = tomSelectPersonaRpt.getValue();
        tomSelectPersonaRpt.clear();
        tomSelectPersonaRpt.clearOptions();
        tomSelectPersonaRpt.addOptions(lista);
        if (valorActual && lista.some(p => p.nombre === valorActual)) {
            tomSelectPersonaRpt.setValue(valorActual, true);
        }
    }

    // Reporte Detallado - Dual Listbox
    const nombresElegidos = new Set(personasSeleccionadas.map(p => p.nombre));
    personasDisponibles = lista.filter(p => !nombresElegidos.has(p.nombre));
    personasSeleccionadas = lista.filter(p => nombresElegidos.has(p.nombre));
    renderDualList();
}

// ── Manejo de Períodos Rápidos ───────────────────────────────────────────────

function initFechasRapidas() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const lastDay = new Date(y, now.getMonth() + 1, 0).getDate();

    const fi = document.getElementById('fecha-inicio-rapido');
    const ff = document.getElementById('fecha-fin-rapido');
    if (fi) fi.value = `${y}-${m}-01`;
    if (ff) ff.value = `${y}-${m}-${String(lastDay).padStart(2, '0')}`;
}

function setPeriodoRapido(tipo, btnEl) {
    const now = new Date();
    let inicio = '';
    let fin = '';

    if (tipo === 'mes-actual') {
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const lastDay = new Date(y, now.getMonth() + 1, 0).getDate();
        inicio = `${y}-${m}-01`;
        fin = `${y}-${m}-${String(lastDay).padStart(2, '0')}`;
    } else if (tipo === 'mes-anterior') {
        let y = now.getFullYear();
        let m = now.getMonth(); // 0-based
        if (m === 0) {
            m = 12;
            y--;
        }
        const lastDay = new Date(y, m, 0).getDate();
        inicio = `${y}-${String(m).padStart(2, '0')}-01`;
        fin = `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
    } else if (tipo === 'semana-actual') {
        const diaSemana = now.getDay() === 0 ? 6 : now.getDay() - 1; // Lunes=0
        const lunes = new Date(now);
        lunes.setDate(now.getDate() - diaSemana);
        const domingo = new Date(lunes);
        domingo.setDate(lunes.getDate() + 6);
        inicio = formatIsoDate(lunes);
        fin = formatIsoDate(domingo);
    }

    const fi = document.getElementById('fecha-inicio-rapido');
    const ff = document.getElementById('fecha-fin-rapido');
    if (fi) fi.value = inicio;
    if (ff) ff.value = fin;

    // Actualizar clases de botones
    ['btn-q-mes-actual', 'btn-q-mes-anterior', 'btn-q-semana-actual', 'btn-q-personalizado'].forEach(id => {
        const b = document.getElementById(id);
        if (b) {
            b.classList.remove('btn-rippling-primary');
            b.classList.add('btn-rippling-secondary');
        }
    });

    if (btnEl) {
        btnEl.classList.remove('btn-rippling-secondary');
        btnEl.classList.add('btn-rippling-primary');
    }

    // Si ya hay una persona seleccionada, refrescar su reporte inmediatamente
    if (tomSelectPersonaRapida && tomSelectPersonaRapida.getValue()) {
        consultarReporteRapidoActual();
    }
}

function toggleFechasRapidas(btnEl) {
    const box = document.getElementById('contenedor-fechas-rapidas');
    if (!box) return;
    if (box.style.display === 'none' || !box.style.display) {
        box.style.display = 'block';
        if (btnEl) {
            btnEl.classList.remove('btn-rippling-secondary');
            btnEl.classList.add('btn-rippling-primary');
        }
    } else {
        box.style.display = 'none';
        if (btnEl) {
            btnEl.classList.remove('btn-rippling-primary');
            btnEl.classList.add('btn-rippling-secondary');
        }
    }
}

// ── Manejo de Estados de Vista Rápida ────────────────────────────────────────

function setEstadoVistaRapida(estado) {
    // estado: 'placeholder' | 'loading' | 'resultado'
    const placeholder = document.getElementById('placeholder-reporte-rapido');
    const loading = document.getElementById('rr-loading');
    const resultado = document.getElementById('resultado-reporte-rapido');

    if (placeholder) placeholder.style.display = (estado === 'placeholder') ? 'flex' : 'none';
    if (loading) loading.style.display = (estado === 'loading') ? 'flex' : 'none';
    if (resultado) resultado.style.display = (estado === 'resultado') ? 'flex' : 'none';
}

// ── Consulta y Renderizado Inmediato con Paginación ─────────────────────────

function consultarReporteRapidoActual() {
    const persona = tomSelectPersonaRapida ? tomSelectPersonaRapida.getValue() : '';
    if (!persona) {
        setEstadoVistaRapida('placeholder');
        return;
    }

    const fi = document.getElementById('fecha-inicio-rapido').value;
    const ff = document.getElementById('fecha-fin-rapido').value;
    if (!fi || !ff) {
        showToast('Seleccione un período de fechas válido.', 'warning');
        return;
    }

    const rrLoadingMsg = document.getElementById('rr-loading-msg');
    if (rrLoadingMsg) rrLoadingMsg.textContent = `Consultando datos de ${persona}...`;
    setEstadoVistaRapida('loading');

    fetch(_BASE + `/api/reportes/persona-data?persona=${encodeURIComponent(persona)}&fecha_inicio=${fi}&fecha_fin=${ff}`)
        .then(r => {
            if (!r.ok) {
                return r.json().then(e => { throw new Error(e.error || 'Error ' + r.status); });
            }
            return r.json();
        })
        .then(data => {
            if (data.error) throw new Error(data.error);

            ultimaPersonaConsultada = persona;
            setEstadoVistaRapida('resultado');
            renderizarReporteRapidoEnPantalla(data);
        })
        .catch(err => {
            setEstadoVistaRapida('placeholder');
            showToast('Error al obtener datos: ' + err.message, 'danger');
        });
}

function esc(v) {
    return String(v === null || v === undefined ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function renderizarReporteRapidoEnPantalla(data) {
    setEstadoVistaRapida('resultado');

    const persona = data.persona || 'Colaborador';
    const resumen = data.resumen || {};
    diasReporteActual = data.dias || [];
    diasPorFechaReporte = {};

    diasReporteActual.forEach(d => {
        const key = d.fecha_iso || d.fecha;
        diasPorFechaReporte[key] = d;
    });

    // ── Encabezado ──
    const elNombre = document.getElementById('txt-nombre-persona');
    if (elNombre) elNombre.textContent = formatearApellidoNombre(persona);

    const elRango = document.getElementById('txt-rango-persona');
    if (elRango) {
        const fmtFecha = iso => {
            if (!iso) return '—';
            const [y, m, d] = iso.split('-');
            const meses = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
            return `${parseInt(d)} ${meses[parseInt(m)-1]} ${y}`;
        };
        elRango.textContent = `${fmtFecha(data.fecha_inicio)} — ${fmtFecha(data.fecha_fin)}`;
    }

    const elHorario = document.getElementById('txt-horario-persona');
    if (elHorario) {
        const hInfo = data.horario_info || {};
        elHorario.textContent = hInfo.tipo ? hInfo.tipo : 'Horario Asignado';
    }

    // ── Resumen & Conteo Completo de Tardanzas / Ausencias / KPIs ──
    const diasAsistidos = resumen.total_dias || diasReporteActual.filter(d => d.estado !== 'ausencia' && d.estado !== 'feriado').length || 0;
    const diasLaborables = resumen.dias_laborables || resumen.total_periodo || diasReporteActual.length || 0;

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val !== undefined ? val : '0';
    };

    setVal('kpi-total-dias', diasAsistidos);
    setVal('kpi-tardanzas-leves', resumen.tardanza_leve || 0);
    setVal('kpi-tardanzas-severas', resumen.tardanza_severa || 0);
    setVal('kpi-exceso-almuerzo', resumen.exceso_almuerzo || resumen.almuerzo_largo || 0);
    setVal('kpi-ausencias', resumen.ausencias || 0);
    setVal('kpi-anomalias', resumen.anomalia || resumen.incompletos || 0);
    setVal('kpi-justificadas', resumen.justificadas || 0);

    // Barra de asistencia
    const elDiasLab = document.getElementById('kpi-dias-laborables');
    if (elDiasLab) elDiasLab.textContent = diasLaborables;

    const pct = diasLaborables > 0 ? Math.round((diasAsistidos / diasLaborables) * 100) : 0;
    const elPct = document.getElementById('kpi-pct-asistencia');
    if (elPct) elPct.textContent = pct + '%';

    const barAsist = document.getElementById('bar-asistencia');
    if (barAsist) barAsist.style.width = pct + '%';

    // ── Renderizar Tabla con Paginación ──
    currentPageReportes = 1;
    renderTablaDiasPaginada();
}

function cambiarPaginaReporte(page) {
    const totalPages = Math.max(1, Math.ceil(diasReporteActual.length / PAGE_SIZE_REPORTES));
    if (page < 1 || page > totalPages) return;
    currentPageReportes = page;
    renderTablaDiasPaginada();
}

function renderTablaDiasPaginada() {
    const tbody = document.getElementById('tbody-reporte-rapido');
    const totalTxt = document.getElementById('txt-total-registros-tabla');
    const paginationFooter = document.getElementById('paginationFooterReportes');
    const paginationInfo = document.getElementById('paginationInfoReportes');
    const btnPrev = document.getElementById('btnPrevReportes');
    const btnNext = document.getElementById('btnNextReportes');

    const totalDias = diasReporteActual.length;
    if (totalTxt) totalTxt.textContent = `${totalDias} día${totalDias !== 1 ? 's' : ''} en el período`;

    if (!tbody) return;
    tbody.innerHTML = '';

    if (totalDias === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-5">
                    <p class="text-muted mb-0">No se encontraron registros para esta persona en el período seleccionado.</p>
                </td>
            </tr>`;
        if (paginationFooter) paginationFooter.style.display = 'none';
        return;
    }

    const totalPages = Math.max(1, Math.ceil(totalDias / PAGE_SIZE_REPORTES));
    if (currentPageReportes > totalPages) currentPageReportes = totalPages;

    const inicio = (currentPageReportes - 1) * PAGE_SIZE_REPORTES;
    const fin = Math.min(inicio + PAGE_SIZE_REPORTES, totalDias);
    const diasPagina = diasReporteActual.slice(inicio, fin);

    if (paginationFooter) {
        paginationFooter.style.display = totalPages > 1 ? 'flex' : 'none';
        if (paginationInfo) {
            paginationInfo.textContent = `Página ${currentPageReportes} de ${totalPages} (${totalDias} días en el período)`;
        }
        if (btnPrev) btnPrev.disabled = currentPageReportes <= 1;
        if (btnNext) btnNext.disabled = currentPageReportes >= totalPages;
    }

    diasPagina.forEach(d => {
        const tr = document.createElement('tr');
        tr.className = 'tr-clickable';
        const keyFecha = d.fecha_iso || d.fecha;
        tr.setAttribute('data-fecha', keyFecha);
        tr.onclick = function () { abrirModalMarcaciones(keyFecha); };

        // ── Estado Badge con Rippling Pills ──
function obtenerDiaSemana(fechaVal) {
    if (!fechaVal) return '';
    try {
        let s = String(fechaVal).trim().split('T')[0];
        if (s.includes('/')) {
            const parts = s.split('/');
            if (parts.length === 3) {
                const dt = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
                const dias = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
                return dias[dt.getDay()];
            }
        } else if (s.includes('-')) {
            const parts = s.split('-');
            if (parts.length === 3) {
                const dt = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                const dias = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
                return dias[dt.getDay()];
            }
        }
    } catch(e) {}
    return '';
}

        let badgeEstado = '';
        const obsStrLower = (Array.isArray(d.observaciones) ? d.observaciones.join(' ') : (d.observaciones || '')).toLowerCase();

        if (d.estado === 'salida_anticipada_severa' || d.estado === 'salida_anticipada_leve' || d.estado === 'salida_anticipada' || obsStrLower.includes('salida ant')) {
            badgeEstado = '<span class="rippling-pill" style="background:#fef2f2; color:#b91c1c; border-color:#fecaca;"><span class="material-symbols-outlined" style="font-size:0.9rem;">logout</span> Salida Anticipada</span>';
        } else if (d.estado === 'severa' || d.estado === 'tardanza_severa') {
            badgeEstado = '<span class="rippling-pill" style="background:#fef2f2; color:#b91c1c; border-color:#fecaca;"><span class="material-symbols-outlined" style="font-size:0.9rem;">error</span> Tardanza Severa</span>';
        } else if (d.estado === 'leve' || d.estado === 'tardanza_leve') {
            if (obsStrLower.includes('almuerzo')) {
                badgeEstado = '<span class="rippling-pill rippling-pill-gold"><span class="material-symbols-outlined" style="font-size:0.9rem;">restaurant</span> Exceso Almuerzo</span>';
            } else {
                badgeEstado = '<span class="rippling-pill rippling-pill-gold"><span class="material-symbols-outlined" style="font-size:0.9rem;">schedule</span> Tardanza Leve</span>';
            }
        } else if (d.estado === 'exceso_almuerzo' || d.estado === 'almuerzo_largo') {
            badgeEstado = '<span class="rippling-pill rippling-pill-gold"><span class="material-symbols-outlined" style="font-size:0.9rem;">restaurant</span> Exceso Almuerzo</span>';
        } else if (d.estado === 'ausencia' || d.estado === 'ausente') {
            badgeEstado = '<span class="rippling-pill" style="background:#fef2f2; color:#b91c1c; border-color:#fecaca;"><span class="material-symbols-outlined" style="font-size:0.9rem;">person_off</span> Ausencia</span>';
        } else if (d.estado === 'incompleto' || d.estado === 'anomalia') {
            badgeEstado = '<span class="rippling-pill" style="background:#fffbeb; color:#b45309; border-color:#fde68a;"><span class="material-symbols-outlined" style="font-size:0.9rem;">warning</span> Incompleto</span>';
        } else if (d.estado === 'sin_horario') {
            badgeEstado = '<span class="rippling-pill" style="background:#f8fafc; color:#334155; border-color:#cbd5e1;"><span class="material-symbols-outlined" style="font-size:0.9rem;">schedule</span> Sin Horario</span>';
        } else if (d.estado === 'extra') {
            badgeEstado = '<span class="rippling-pill rippling-pill-navy"><span class="material-symbols-outlined" style="font-size:0.9rem;">add_circle</span> Día Extra</span>';
        } else if (d.estado === 'feriado') {
            badgeEstado = '<span class="rippling-pill rippling-pill-slate"><span class="material-symbols-outlined" style="font-size:0.9rem;">beach_access</span> Feriado</span>';
        } else {
            badgeEstado = '<span class="rippling-pill" style="background:#ecfdf5; color:#047857; border-color:#a7f3d0;"><span class="material-symbols-outlined" style="font-size:0.9rem;">check_circle</span> Puntual</span>';
        }

        if (d.justificado) {
            badgeEstado += ' <span class="rippling-pill rippling-pill-navy" style="font-size:0.68rem; margin-top:2px;">Justificado</span>';
        }

        const llegadaStr = d.llegada
            ? `<span class="time-badge time-badge-in"><span class="material-symbols-outlined" style="font-size:0.9rem;">login</span>${esc(d.llegada)}</span>`
            : '<span class="time-badge-empty">—</span>';

        const salidaStr = d.salida
            ? `<span class="time-badge time-badge-out"><span class="material-symbols-outlined" style="font-size:0.9rem;">logout</span>${esc(d.salida)}</span>`
            : '<span class="time-badge-empty">—</span>';

        const tiempoDentroStr = d.tiempo_dentro
            ? `<span class="fw-semibold text-dark">${esc(d.tiempo_dentro)}</span>`
            : '<span class="text-muted">—</span>';

        let almuerzoStr = '<span class="text-muted">—</span>';
        if (d.almuerzo_duracion) {
            almuerzoStr = `${d.almuerzo_duracion}m`;
            if (d.almuerzo_exceso && d.almuerzo_exceso > 0) {
                almuerzoStr += ` <span class="text-danger fw-semibold">(+${d.almuerzo_exceso}m)</span>`;
            }
        } else if (d.permiso_duracion) {
            almuerzoStr = `Permiso ${d.permiso_duracion}m`;
        }

        const obsList = Array.isArray(d.observaciones) ? d.observaciones : [];
        const obsStr = obsList.length > 0
            ? obsList.map(o => `<div class="small text-muted" style="line-height:1.3; margin-bottom:2px;">&bull; ${esc(o)}</div>`).join('')
            : '<span class="text-muted">—</span>';

        const nombreDia = d.dia_nombre || obtenerDiaSemana(d.fecha_str || d.fecha_iso || d.fecha);
        const fechaTexto = esc(d.fecha_str || d.fecha_iso || d.fecha);
        const abrevDia = nombreDia ? nombreDia.substring(0, 3).toUpperCase() : '';

        tr.innerHTML = `
            <td>
                <div class="d-flex align-items-center gap-2">
                    <div class="d-flex flex-column align-items-center justify-content-center bg-light border rounded px-2 py-1 text-center" style="min-width: 44px;">
                        <span class="text-primary fw-bold" style="font-size: 0.72rem; line-height: 1;">${esc(abrevDia)}</span>
                    </div>
                    <div>
                        <div class="fw-bold text-dark" style="font-size:0.875rem;">${fechaTexto}</div>
                        ${nombreDia ? `<div class="text-muted small" style="font-size:0.75rem; font-weight:600;">${esc(nombreDia)}</div>` : ''}
                    </div>
                </div>
            </td>
            <td><span class="fw-semibold text-dark">${esc(d.hora_programada || '—')}</span></td>
            <td>${llegadaStr}</td>
            <td>${salidaStr}</td>
            <td>${tiempoDentroStr}</td>
            <td>${almuerzoStr}</td>
            <td>${badgeEstado}</td>
            <td>${obsStr}</td>
            <td class="text-end">
                <button type="button" class="btn btn-sm btn-outline-secondary py-1 px-2" title="Ver marcaciones del día" onclick="event.stopPropagation(); abrirModalMarcaciones('${keyFecha}');">
                    <span class="material-symbols-outlined" style="font-size: 1.05rem;">visibility</span>
                </button>
            </td>
        `;

        tbody.appendChild(tr);
    });
}

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

// ── Manejo de Períodos para Reporte Detallado ────────────────────────────────

function setPeriodoDetallado(tipo, btnEl) {
    const now = new Date();
    let inicio = '';
    let fin = '';

    if (tipo === 'mes-actual') {
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const lastDay = new Date(y, now.getMonth() + 1, 0).getDate();
        inicio = `${y}-${m}-01`;
        fin = `${y}-${m}-${String(lastDay).padStart(2, '0')}`;
    } else if (tipo === 'mes-anterior') {
        let y = now.getFullYear();
        let m = now.getMonth(); // 0-based
        if (m === 0) {
            m = 12;
            y--;
        }
        const lastDay = new Date(y, m, 0).getDate();
        inicio = `${y}-${String(m).padStart(2, '0')}-01`;
        fin = `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
    } else if (tipo === 'semana-actual') {
        const diaSemana = now.getDay() === 0 ? 6 : now.getDay() - 1; // Lunes=0, Dom=6
        const lunes = new Date(now);
        lunes.setDate(now.getDate() - diaSemana);
        const domingo = new Date(lunes);
        domingo.setDate(lunes.getDate() + 6);
        inicio = formatIsoDate(lunes);
        fin = formatIsoDate(domingo);
    }

    const fi = document.getElementById('fecha-inicio');
    const ff = document.getElementById('fecha-fin');
    if (fi) fi.value = inicio;
    if (ff) ff.value = fin;

    // Actualizar estilo visual activo de botones de fecha (igual que en reporte rápido)
    ['btn-d-mes-actual', 'btn-d-mes-anterior', 'btn-d-semana-actual'].forEach(id => {
        const b = document.getElementById(id);
        if (b) {
            b.classList.remove('btn-rippling-primary');
            b.classList.add('btn-rippling-secondary');
        }
    });

    if (btnEl) {
        btnEl.classList.remove('btn-rippling-secondary');
        btnEl.classList.add('btn-rippling-primary');
    }

    reloadPersonas();
}

function setMesActual() {
    setPeriodoDetallado('mes-actual', document.getElementById('btn-d-mes-actual'));
}

function setSemanaActual() {
    setPeriodoDetallado('semana-actual', document.getElementById('btn-d-semana-actual'));
}

function setMesAnterior() {
    setPeriodoDetallado('mes-anterior', document.getElementById('btn-d-mes-anterior'));
}

function formatIsoDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

// ── Modos de Reporte Detallado & Email Toggle ────────────────────────────────

function toggleEmailDetallado() {
    const box = document.getElementById('box-email-detallado');
    const ico = document.getElementById('icoToggleEmailDetallado');
    if (!box) return;
    const isHidden = box.style.display === 'none' || !box.style.display;
    box.style.display = isHidden ? 'block' : 'none';
    if (ico) ico.textContent = isHidden ? 'expand_less' : 'expand_more';
}

function actualizarVisibilidadModo() {
    const v = document.getElementById('modo').value;
    const esGeneral = v === 'general';

    const pGrp = document.getElementById('persona-group');
    if (pGrp) pGrp.style.display = v === 'persona' ? 'block' : 'none';
    const vGrp = document.getElementById('varias-group');
    if (vGrp) {
        vGrp.style.display = v === 'varias' ? 'block' : 'none';
        if (v === 'varias') renderDualList();
    }
    const eGrp = document.getElementById('especiales-group');
    if (eGrp) eGrp.style.display = esGeneral ? 'block' : 'none';

    const grupoPersona = document.getElementById('filtros-persona-only');
    if (grupoPersona) {
        grupoPersona.style.display = esGeneral ? 'none' : 'block';
        if (esGeneral) {
            ['f-ausencias', 'f-tiempo-dentro', 'f-horas-contrato', 'f-tiempo-extra'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.checked = false;
            });
        }
    }

    reloadPersonas();
}

function reloadPersonas() {
    const fi = document.getElementById('fecha-inicio').value;
    const ff = document.getElementById('fecha-fin').value;
    if (fi && ff) {
        cargarPersonasParaFechas(fi, ff);
    }
}

// ── Manejo de Dual Listbox para Múltiples Colaboradores ──────────────────────

function renderDualList() {
    const listDisp = document.getElementById('lista-disponibles');
    const listEleg = document.getElementById('lista-seleccionados');
    const countDisp = document.getElementById('count-disponibles');
    const countEleg = document.getElementById('count-seleccionados');
    const selVarias = document.getElementById('personas-varias');

    if (countDisp) countDisp.textContent = personasDisponibles.length;
    if (countEleg) countEleg.textContent = personasSeleccionadas.length;

    const filtroDisp = (document.getElementById('filtro-disponibles')?.value || '').toLowerCase().trim();
    const filtroEleg = (document.getElementById('filtro-seleccionados')?.value || '').toLowerCase().trim();

    if (listDisp) {
        const visibles = personasDisponibles.filter(p => {
            const nom = (p.nombre || '').toLowerCase();
            const nomDisp = formatearApellidoNombre(p.nombre).toLowerCase();
            const ci = (p.identificacion || '').toLowerCase();
            const zk = String(p.id_usuario_zk || '').toLowerCase();
            return !filtroDisp || nom.includes(filtroDisp) || nomDisp.includes(filtroDisp) || ci.includes(filtroDisp) || zk.includes(filtroDisp);
        });

        if (visibles.length === 0) {
            listDisp.innerHTML = '<div class="p-3 text-center text-muted small">No hay disponibles</div>';
        } else {
            listDisp.innerHTML = visibles.map(p => {
                const isSel = seleccionadosTempDisponibles.has(p.nombre);
                const nombreMostrar = formatearApellidoNombre(p.nombre);
                const meta = p.identificacion ? `CI: ${esc(p.identificacion)}` : (p.id_usuario_zk ? `ZK: ${esc(p.id_usuario_zk)}` : '');
                return `
                    <div class="dual-list-item ${isSel ? 'selected' : ''}" onclick="toggleSeleccionItem('disponible', '${esc(p.nombre)}', event)" ondblclick="moverPersonaIndividualADerecha('${esc(p.nombre)}')">
                        <div class="text-truncate">
                            <span class="d-block fw-semibold text-dark text-truncate">${esc(nombreMostrar)}</span>
                            ${meta ? `<span class="text-muted" style="font-size:0.7rem;">${meta}</span>` : ''}
                        </div>
                        <span class="material-symbols-outlined text-muted" style="font-size:1rem;">chevron_right</span>
                    </div>
                `;
            }).join('');
        }
    }

    if (listEleg) {
        const visibles = personasSeleccionadas.filter(p => {
            const nom = (p.nombre || '').toLowerCase();
            const nomDisp = formatearApellidoNombre(p.nombre).toLowerCase();
            const ci = (p.identificacion || '').toLowerCase();
            const zk = String(p.id_usuario_zk || '').toLowerCase();
            return !filtroEleg || nom.includes(filtroEleg) || nomDisp.includes(filtroEleg) || ci.includes(filtroEleg) || zk.includes(filtroEleg);
        });

        if (visibles.length === 0) {
            listEleg.innerHTML = '<div class="p-3 text-center text-muted small">Ningún colaborador añadido</div>';
        } else {
            listEleg.innerHTML = visibles.map(p => {
                const isSel = seleccionadosTempElegidos.has(p.nombre);
                const nombreMostrar = formatearApellidoNombre(p.nombre);
                const meta = p.identificacion ? `CI: ${esc(p.identificacion)}` : (p.id_usuario_zk ? `ZK: ${esc(p.id_usuario_zk)}` : '');
                return `
                    <div class="dual-list-item ${isSel ? 'selected' : ''}" onclick="toggleSeleccionItem('elegido', '${esc(p.nombre)}', event)" ondblclick="moverPersonaIndividualAIzquierda('${esc(p.nombre)}')">
                        <div class="text-truncate">
                            <span class="d-block fw-semibold text-navy text-truncate">${esc(nombreMostrar)}</span>
                            ${meta ? `<span class="text-muted" style="font-size:0.7rem;">${meta}</span>` : ''}
                        </div>
                        <button type="button" class="btn btn-link btn-sm p-0 text-danger text-decoration-none" onclick="moverPersonaIndividualAIzquierda('${esc(p.nombre)}'); event.stopPropagation();" title="Quitar">
                            <span class="material-symbols-outlined" style="font-size:1rem;">close</span>
                        </button>
                    </div>
                `;
            }).join('');
        }
    }

    // Sincronizar select hidden
    if (selVarias) {
        selVarias.innerHTML = '';
        personasSeleccionadas.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.nombre;
            opt.selected = true;
            selVarias.appendChild(opt);
        });
    }
}

function toggleSeleccionItem(origen, nombre, e) {
    const set = origen === 'disponible' ? seleccionadosTempDisponibles : seleccionadosTempElegidos;
    if (e && (e.ctrlKey || e.metaKey)) {
        if (set.has(nombre)) set.delete(nombre);
        else set.add(nombre);
    } else {
        if (set.has(nombre)) set.delete(nombre);
        else {
            set.clear();
            set.add(nombre);
        }
    }
    renderDualList();
}

function moverPersonaIndividualADerecha(nombre) {
    const idx = personasDisponibles.findIndex(p => p.nombre === nombre);
    if (idx !== -1) {
        const [p] = personasDisponibles.splice(idx, 1);
        personasSeleccionadas.push(p);
        seleccionadosTempDisponibles.delete(nombre);
        renderDualList();
    }
}

function moverPersonaIndividualAIzquierda(nombre) {
    const idx = personasSeleccionadas.findIndex(p => p.nombre === nombre);
    if (idx !== -1) {
        const [p] = personasSeleccionadas.splice(idx, 1);
        personasDisponibles.push(p);
        seleccionadosTempElegidos.delete(nombre);
        renderDualList();
    }
}

function moverSeleccionadosDerecha() {
    if (seleccionadosTempDisponibles.size === 0 && personasDisponibles.length > 0) {
        moverPersonaIndividualADerecha(personasDisponibles[0].nombre);
        return;
    }
    const aMover = Array.from(seleccionadosTempDisponibles);
    personasDisponibles = personasDisponibles.filter(p => {
        if (aMover.includes(p.nombre)) {
            personasSeleccionadas.push(p);
            return false;
        }
        return true;
    });
    seleccionadosTempDisponibles.clear();
    renderDualList();
}

function moverSeleccionadosIzquierda() {
    if (seleccionadosTempElegidos.size === 0 && personasSeleccionadas.length > 0) {
        moverPersonaIndividualAIzquierda(personasSeleccionadas[0].nombre);
        return;
    }
    const aMover = Array.from(seleccionadosTempElegidos);
    personasSeleccionadas = personasSeleccionadas.filter(p => {
        if (aMover.includes(p.nombre)) {
            personasDisponibles.push(p);
            return false;
        }
        return true;
    });
    seleccionadosTempElegidos.clear();
    renderDualList();
}

function moverTodosHaciaDerecha() {
    personasSeleccionadas.push(...personasDisponibles);
    personasDisponibles = [];
    seleccionadosTempDisponibles.clear();
    renderDualList();
}

function moverTodosHaciaIzquierda() {
    personasDisponibles.push(...personasSeleccionadas);
    personasSeleccionadas = [];
    seleccionadosTempElegidos.clear();
    renderDualList();
}

function filtrarListaDisponibles() {
    renderDualList();
}

function filtrarListaSeleccionados() {
    renderDualList();
}

function leerFiltros() {
    const chk = id => { const el = document.getElementById(id); return el ? el.checked : false; };
    return {
        mostrar_ausencias: chk('f-ausencias'),
        mostrar_tardanza_severa: chk('f-tardanza-severa'),
        mostrar_tardanza_leve: chk('f-tardanza-leve'),
        mostrar_almuerzo: chk('f-almuerzo'),
        mostrar_incompletos: chk('f-incompletos'),
        mostrar_salida_anticipada: chk('f-salida-anticipada'),
        mostrar_todos_los_dias: chk('f-todos-dias'),
        columna_tiempo_dentro: chk('f-tiempo-dentro'),
        reporte_sin_horario: chk('f-sin-horario'),
        reporte_todos_usuarios: chk('f-todos-usuarios'),
        verificar_horas: chk('f-horas-contrato'),
        mostrar_tiempo_extra: chk('f-tiempo-extra'),
    };
}

function generarReporte() {
    const btn = document.getElementById('btn-submit');
    const spinner = document.getElementById('loading-spinner');
    const spinnerMsg = document.getElementById('loading-spinner-msg');

    const fi = document.getElementById('fecha-inicio').value;
    const ff = document.getElementById('fecha-fin').value;
    const exclEl = document.getElementById('excluidos');
    const excl = exclEl ? exclEl.value.split(',').map(s => s.trim()).filter(s => s) : [];
    const filtros = leerFiltros();
    const modo = document.getElementById('modo').value;

    const fmtEl = document.querySelector('input[name="formato-reporte"]:checked');
    const formato = fmtEl ? fmtEl.value : 'pdf';

    const payload = {
        fecha_inicio: fi,
        fecha_fin: ff,
        modo: modo,
        filtros: filtros,
        excluidos: excl,
        formato: formato,
    };

    if (modo === 'persona') {
        const p = tomSelectPersonaRpt ? tomSelectPersonaRpt.getValue() : '';
        if (!p) return showToast("Debe seleccionar una persona.", 'warning');
        payload.persona = p;
    } else if (modo === 'varias') {
        const elegidas = personasSeleccionadas.map(p => p.nombre);
        if (elegidas.length === 0) return showToast("Debe agregar al menos un colaborador a la lista de seleccionados.", 'warning');
        payload.personas = elegidas;
    }

    if (spinnerMsg) spinnerMsg.textContent = 'Procesando y generando reporte detallado...';
    if (spinner) spinner.style.display = 'block';
    if (btn) btn.disabled = true;

    fetch(_BASE + '/api/generar-desde-db', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
        .then(r => r.json().then(data => ({ status: r.status, ok: r.ok, body: data })))
        .then(res => {
            if (spinner) spinner.style.display = 'none';
            if (btn) btn.disabled = false;
            if (!res.ok) throw new Error(res.body.error || 'Error generando reporte');

            showToast('Reporte generado. Descargando...', 'success');

            const a = document.createElement('a');
            a.href = res.body.download_url;
            a.download = res.body.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        })
        .catch(err => {
            if (spinner) spinner.style.display = 'none';
            if (btn) btn.disabled = false;
            showToast("Error al generar: " + err.message, 'danger');
        });
}

function enviarPorEmail() {
    const btn = document.querySelector('#persona-group button');
    const emailInput = document.getElementById('email-destino');
    const spinner = document.getElementById('loading-spinner');
    const spinnerMsg = document.getElementById('loading-spinner-msg');

    const email = emailInput ? emailInput.value.trim() : '';
    if (!email) return showToast("Debe ingresar un correo electrónico.", 'warning');
    if (!email.includes('@') || !email.includes('.')) {
        return showToast("Formato de correo inválido.", 'warning');
    }

    const fi = document.getElementById('fecha-inicio').value;
    const ff = document.getElementById('fecha-fin').value;
    const excl = document.getElementById('excluidos').value.split(',').map(s => s.trim()).filter(s => s);
    const filtros = leerFiltros();
    const p = tomSelectPersonaRpt ? tomSelectPersonaRpt.getValue() : '';

    if (!p) return showToast("Debe seleccionar una persona.", 'warning');
    if (!fi || !ff) return showToast("Debe seleccionar un rango de fechas.", 'warning');

    const payload = {
        fecha_inicio: fi,
        fecha_fin: ff,
        persona: p,
        email: email,
        filtros: filtros,
        excluidos: excl
    };

    if (spinnerMsg) spinnerMsg.textContent = `Enviando reporte por correo a ${email}...`;
    if (spinner) spinner.style.display = 'block';
    if (btn) btn.disabled = true;

    fetch((window.APP_BASE || '') + '/api/reportes/enviar-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json().then(data => ({ status: r.status, ok: r.ok, body: data })))
        .then(res => {
            if (spinner) spinner.style.display = 'none';
            if (btn) btn.disabled = false;
            if (!res.ok) throw new Error(res.body.error || 'Error al enviar reporte');
            showToast(res.body.message || 'Reporte enviado por correo correctamente.', 'success');
            if (emailInput) emailInput.value = '';
        })
        .catch(err => {
            if (spinner) spinner.style.display = 'none';
            if (btn) btn.disabled = false;
            showToast("Error al enviar: " + err.message, 'danger');
        });
}

// ════════════════════════════════════════════════════════════════════════════
// GESTIÓN DE USUARIOS Y HORARIOS DESDE EL MÓDULO DE REPORTES
// ════════════════════════════════════════════════════════════════════════════

let _personaEnEdicion = null;
let _targetSelectGrupo = null;
let _targetSelectGF = null;

function abrirModalEditarDesdeReporte() {
    const selVal = (tomSelectPersonaRapida && tomSelectPersonaRapida.getValue()) || ultimaPersonaConsultada || (tomSelectPersonaRpt && tomSelectPersonaRpt.getValue());
    if (!selVal) {
        showToast("Selecciona primero un colaborador en el buscador para editar sus datos y horarios.", "warning");
        return;
    }

    let p = (personasCache || []).find(x => x.nombre === selVal || x.id === selVal || String(x.id_usuario_zk) === String(selVal));
    if (!p) {
        // Consultar API si aún no está en cache
        fetch((window.APP_BASE || '') + '/api/personas/buscar?q=' + encodeURIComponent(selVal))
            .then(r => r.ok ? r.json() : { personas: [] })
            .then(data => {
                const found = (data.personas || []).find(x => x.nombre === selVal || x.id === selVal || String(x.id_usuario_zk) === String(selVal)) || data.personas[0];
                if (found) {
                    abrirModalConDatosPersona(found);
                } else {
                    showToast("No se encontró la información del colaborador seleccionado.", "danger");
                }
            })
            .catch(err => showToast("Error al obtener datos: " + err.message, "danger"));
    } else {
        abrirModalConDatosPersona(p);
    }
}

function abrirModalConDatosPersona(p) {
    if (!p) return;

    _personaEnEdicion = {
        id: p.id,
        nombre: p.nombre || '',
        idzk: (p.id_usuario_zk || '').trim()
    };

    const form = document.getElementById('formEditarPersona');
    if (form) form.action = (window.APP_BASE || '') + '/personas/' + p.id;

    const setVal = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.value = (v !== undefined && v !== null) ? v : '';
    };

    const subtitulo = document.getElementById('edit_subtitulo');
    if (subtitulo) subtitulo.textContent = formatearApellidoNombre(p.nombre);

    setVal('edit_persona_id_val', p.id);
    setVal('edit_nombre', p.nombre);
    setVal('edit_identificacion', p.identificacion);
    setVal('edit_tipo', p.tipo_persona_id);
    setVal('edit_grupo', p.grupo_id);
    setVal('edit_grupo_funcional', p.grupo_funcional_id);
    setVal('edit_email', p.email);
    setVal('edit_telefono', p.telefono);
    setVal('edit_activo', (p.activo !== false && p.activo !== 0) ? '1' : '0');
    setVal('edit_notas', p.notas);

    const zkVal = (p.id_usuario_zk || '').trim();
    const idzkInput = document.getElementById('edit_idzk');
    const idzkHidden = document.getElementById('edit_idzk_hidden');
    const zkBadge = document.getElementById('zk_locked_badge');
    const zkHelp = document.getElementById('zk_help_text');

    if (idzkHidden) idzkHidden.value = zkVal;
    if (idzkInput) {
        idzkInput.value = zkVal;
        if (zkVal !== '') {
            idzkInput.readOnly = true;
            idzkInput.classList.add('bg-white', 'text-muted');
            idzkInput.style.cursor = 'not-allowed';
            if (zkBadge) zkBadge.style.display = 'inline-flex';
            if (zkHelp) zkHelp.innerHTML = '<span class="text-secondary fw-semibold"><span class="material-symbols-outlined fs-6 align-middle">lock</span> El ID biométrico es permanente y no se puede modificar una vez creado.</span>';
        } else {
            idzkInput.readOnly = false;
            idzkInput.classList.remove('bg-white', 'text-muted');
            idzkInput.style.cursor = '';
            if (zkBadge) zkBadge.style.display = 'none';
            if (zkHelp) zkHelp.innerHTML = 'Asigna el número de usuario del dispositivo ZK (una vez guardado no se podrá modificar).';
        }
    }

    actualizarInfoHorarioEnModal(p.nombre || '', zkVal);

    const modalEl = document.getElementById('modalEditarPersona');
    if (modalEl) {
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
}

function actualizarInfoHorarioEnModal(nombre, idZk) {
    const badge = document.getElementById('edit_horario_badge');
    const desc = document.getElementById('edit_horario_desc');
    const btn = document.getElementById('btn-abrir-horario-desde-modal');
    const btnIcon = document.getElementById('btn-abrir-horario-icono');
    const btnTexto = document.getElementById('btn-abrir-horario-texto');
    if (!badge || !desc || !btn) return;

    if (!idZk) {
        badge.className = 'rippling-pill';
        badge.style = 'background-color: #fffbeb; color: #b45309; border-color: #fde68a; font-size:0.75rem;';
        badge.innerHTML = '<span class="material-symbols-outlined" style="font-size:0.8rem;">warning</span> Sin ID Reloj';
        desc.innerHTML = '<span class="text-muted">Asigna primero el ID biométrico arriba y guarda para configurar su turno individual.</span>';
        btn.disabled = true;
        btn.classList.add('opacity-50');
        if (btnTexto) btnTexto.textContent = 'Requiere ID ZK';
        return;
    }

    btn.disabled = false;
    btn.classList.remove('opacity-50');

    const DIAS = ['lunes','martes','miercoles','jueves','viernes','sabado','domingo'];
    const DIAS_LABEL = {lunes:'Lun', martes:'Mar', miercoles:'Mié', jueves:'Jue', viernes:'Vie', sabado:'Sáb', domingo:'Dom'};
    const h = (_horariosCache || []).find(item => String(item.id_usuario) === String(idZk));

    if (h) {
        badge.className = 'rippling-pill';
        badge.style = 'background-color: #ecfdf5; color: #047857; border-color: #a7f3d0; font-size:0.75rem;';
        badge.innerHTML = '<span class="material-symbols-outlined" style="font-size:0.8rem;">check_circle</span> Horario configurado';
        
        const diasActivos = DIAS.filter(d => h[d]).map(d => DIAS_LABEL[d]);
        const entrada = h.lunes || h.martes || h.miercoles || h.jueves || h.viernes || '';
        const salida = h.lunes_salida || h.martes_salida || h.miercoles_salida || h.jueves_salida || h.viernes_salida || '';
        const horarioStr = entrada ? (salida ? `${entrada} a ${salida}` : `Entrada: ${entrada}`) : 'Jornada personalizada';
        const almuerzoStr = h.almuerzo_min ? ` · Almuerzo: ${h.almuerzo_min} min` : '';

        desc.innerHTML = `<strong>${diasActivos.join(' ')}</strong> · ${horarioStr}${almuerzoStr}`;
        if (btnIcon) btnIcon.textContent = 'edit_calendar';
        if (btnTexto) btnTexto.textContent = 'Editar Horario';
    } else {
        badge.className = 'rippling-pill';
        badge.style = 'background-color: #fffbeb; color: #b45309; border-color: #fde68a; font-size:0.75rem;';
        badge.innerHTML = '<span class="material-symbols-outlined" style="font-size:0.8rem;">schedule</span> Sin horario individual';
        desc.innerHTML = '<span class="text-muted">Hereda horario de su grupo o no tiene turno individual definido.</span>';
        if (btnIcon) btnIcon.textContent = 'add_alarm';
        if (btnTexto) btnTexto.textContent = '+ Asignar Horario';
    }
}

function abrirHorarioDesdeModalEditar() {
    if (!_personaEnEdicion || !_personaEnEdicion.idzk) {
        const idzkInput = document.getElementById('edit_idzk');
        if (idzkInput && idzkInput.value) {
            _personaEnEdicion.idzk = idzkInput.value.trim();
        }
    }
    if (!_personaEnEdicion || !_personaEnEdicion.idzk) {
        showToast('Por favor ingresa primero el ID del reloj biométrico y guarda los cambios.', 'warning');
        return;
    }
    
    // Ocultar modal de edición
    const modalEl = document.getElementById('modalEditarPersona');
    if (modalEl) {
        const modalInst = bootstrap.Modal.getInstance(modalEl);
        if (modalInst) modalInst.hide();
    }

    const nombre = document.getElementById('edit_nombre')?.value || _personaEnEdicion.nombre;
    const idzk = _personaEnEdicion.idzk;

    // Abrir offcanvas de horario
    abrirHorarioDePersona(nombre, idzk);
}

const DIAS_HORARIOS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];

function cargarHorarios() {
    fetch((window.APP_BASE || '') + '/api/horarios')
        .then(r => r.ok ? r.json() : { horarios: [] })
        .then(data => {
            _horariosCache = data.horarios || [];
            if (_personaEnEdicion && _personaEnEdicion.idzk) {
                actualizarInfoHorarioEnModal(_personaEnEdicion.nombre, _personaEnEdicion.idzk);
            }
        })
        .catch(err => console.warn('Error al cargar horarios:', err));
}

function abrirOffcanvasCrear() {
    if (!offcanvasHorario) {
        const el = document.getElementById('offcanvas-horario');
        if (el) offcanvasHorario = new bootstrap.Offcanvas(el);
    }
    const modoEl = document.getElementById('mh-modo');
    if (modoEl) modoEl.value = 'crear';
    const labelEl = document.getElementById('offcanvasHorarioLabel');
    if (labelEl) labelEl.textContent = 'Nuevo horario de trabajo';
    const idEl = document.getElementById('mh-id');
    if (idEl) { idEl.value = ''; idEl.readOnly = false; }
    const nomEl = document.getElementById('mh-nombre');
    if (nomEl) nomEl.value = '';
    const errEl = document.getElementById('mh-error');
    if (errEl) errEl.style.display = 'none';
    const notasEl = document.getElementById('mh-notas');
    if (notasEl) notasEl.value = '';
    const almEl = document.getElementById('mh-almuerzo');
    if (almEl) almEl.value = '0';

    DIAS_HORARIOS.forEach(d => {
        const dIn = document.getElementById(`mh-${d}`);
        const dOut = document.getElementById(`mh-${d}-salida`);
        const dLibre = document.getElementById(`mh-libre-${d}`);
        if (dIn) dIn.value = '';
        if (dOut) dOut.value = '';
        const isWeekend = (d === 'sabado' || d === 'domingo');
        if (dLibre) dLibre.checked = isWeekend;
        toggleDia(d);
    });

    const thNone = document.getElementById('tipoHorasNone');
    if (thNone) thNone.checked = true;
    const thSem = document.getElementById('mh-horas-semana');
    if (thSem) thSem.value = '';
    const thMes = document.getElementById('mh-horas-mes');
    if (thMes) thMes.value = '';
    toggleTipoHoras();

    if (offcanvasHorario) offcanvasHorario.show();
}

function abrirOffcanvasEditar(h) {
    if (!offcanvasHorario) {
        const el = document.getElementById('offcanvas-horario');
        if (el) offcanvasHorario = new bootstrap.Offcanvas(el);
    }
    const modoEl = document.getElementById('mh-modo');
    if (modoEl) modoEl.value = 'editar';
    const labelEl = document.getElementById('offcanvasHorarioLabel');
    if (labelEl) labelEl.textContent = `Editar: ${h.nombre}`;
    const idEl = document.getElementById('mh-id');
    if (idEl) { idEl.value = h.id_usuario; idEl.readOnly = true; }
    const nomEl = document.getElementById('mh-nombre');
    if (nomEl) nomEl.value = h.nombre;
    const errEl = document.getElementById('mh-error');
    if (errEl) errEl.style.display = 'none';
    const notasEl = document.getElementById('mh-notas');
    if (notasEl) notasEl.value = h.notas || '';
    const almEl = document.getElementById('mh-almuerzo');
    if (almEl) almEl.value = h.almuerzo_min || '0';

    DIAS_HORARIOS.forEach(d => {
        const dIn = document.getElementById(`mh-${d}`);
        const dOut = document.getElementById(`mh-${d}-salida`);
        const dLibre = document.getElementById(`mh-libre-${d}`);
        if (h[d]) {
            if (dIn) dIn.value = h[d];
            if (dLibre) dLibre.checked = false;
        } else {
            if (dIn) dIn.value = '';
            if (dLibre) dLibre.checked = true;
        }
        if (dOut) dOut.value = h[`${d}_salida`] || '';
        toggleDia(d);
    });

    if (h.horas_semana) {
        const thSemRadio = document.getElementById('tipoHorasSemana');
        if (thSemRadio) thSemRadio.checked = true;
        const thSem = document.getElementById('mh-horas-semana');
        if (thSem) thSem.value = h.horas_semana;
        const thMes = document.getElementById('mh-horas-mes');
        if (thMes) thMes.value = '';
    } else if (h.horas_mes) {
        const thMesRadio = document.getElementById('tipoHorasMes');
        if (thMesRadio) thMesRadio.checked = true;
        const thMes = document.getElementById('mh-horas-mes');
        if (thMes) thMes.value = h.horas_mes;
        const thSem = document.getElementById('mh-horas-semana');
        if (thSem) thSem.value = '';
    } else {
        const thNone = document.getElementById('tipoHorasNone');
        if (thNone) thNone.checked = true;
        const thSem = document.getElementById('mh-horas-semana');
        if (thSem) thSem.value = '';
        const thMes = document.getElementById('mh-horas-mes');
        if (thMes) thMes.value = '';
    }
    toggleTipoHoras();

    if (offcanvasHorario) offcanvasHorario.show();
}

function toggleDia(dia) {
    const libreEl = document.getElementById(`mh-libre-${dia}`);
    const inputHora = document.getElementById(`mh-${dia}`);
    const inputSalida = document.getElementById(`mh-${dia}-salida`);
    const isLibre = libreEl ? libreEl.checked : false;
    if (inputHora) {
        inputHora.disabled = isLibre;
        if (isLibre) inputHora.value = '';
    }
    if (inputSalida) {
        inputSalida.disabled = isLibre;
        if (isLibre) inputSalida.value = '';
    }
}

function toggleTipoHoras() {
    const radio = document.querySelector('input[name="tipoHoras"]:checked');
    const tipo = radio ? radio.value : 'none';
    const divSem = document.getElementById('div-horas-semana');
    const divMes = document.getElementById('div-horas-mes');
    if (divSem) divSem.style.display = (tipo === 'semana') ? 'block' : 'none';
    if (divMes) divMes.style.display = (tipo === 'mes') ? 'block' : 'none';
}

function guardarHorario() {
    const modoEl = document.getElementById('mh-modo');
    const modo = modoEl ? modoEl.value : 'crear';
    const idUsuario = document.getElementById('mh-id')?.value;
    const nombre = document.getElementById('mh-nombre')?.value;

    if (!idUsuario) return errMh("El ID es requerido.");
    if (!nombre) return errMh("El nombre es requerido.");

    const payload = {
        id_usuario: idUsuario,
        nombre: nombre,
        almuerzo_min: parseInt(document.getElementById('mh-almuerzo')?.value) || 0,
        notas: document.getElementById('mh-notas')?.value || '',
        horas_semana: null,
        horas_mes: null
    };

    const radio = document.querySelector('input[name="tipoHoras"]:checked');
    const tipoH = radio ? radio.value : 'none';
    if (tipoH === 'semana') {
        const val = document.getElementById('mh-horas-semana')?.value;
        if (!val) return errMh("Especifique las horas semanales.");
        payload.horas_semana = parseFloat(val);
    } else if (tipoH === 'mes') {
        const val = document.getElementById('mh-horas-mes')?.value;
        if (!val) return errMh("Especifique las horas mensuales.");
        payload.horas_mes = parseFloat(val);
    }

    let countActivos = 0;
    for (const d of DIAS_HORARIOS) {
        const libreEl = document.getElementById(`mh-libre-${d}`);
        if (libreEl && !libreEl.checked) {
            const h = document.getElementById(`mh-${d}`)?.value;
            if (!h) return errMh(`Especifique la hora de entrada para ${d} o márquelo como libre.`);
            payload[d] = h;
            const salida = document.getElementById(`mh-${d}-salida`)?.value;
            if (salida) payload[`${d}_salida`] = salida;
            countActivos++;
        }
    }

    const url = (window.APP_BASE || '') + (modo === 'crear' ? '/api/horarios' : `/api/horarios/${idUsuario}`);
    const method = modo === 'crear' ? 'POST' : 'PUT';

    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify(payload)
    })
    .then(r => r.json().then(data => ({ status: r.status, ok: r.ok, body: data })))
    .then(res => {
        if (!res.ok) throw new Error(res.body?.error || 'Error al guardar el horario.');
        if (offcanvasHorario) offcanvasHorario.hide();
        showToast(`Horario de ${nombre} ${modo === 'crear' ? 'creado' : 'actualizado'} correctamente.`, 'success');
        cargarHorarios();
        if (typeof window.onHorarioGuardadoExitoso === 'function') {
            window.onHorarioGuardadoExitoso(payload);
        }
    })
    .catch(err => errMh(err.message));
}

function errMh(msg) {
    const e = document.getElementById('mh-error');
    if (e) {
        e.textContent = msg;
        e.style.display = 'block';
    }
}

// ── Creación Rápida Inline de Institución / Grupo ───────────────────────────
function abrirCrearGrupoRapido(targetSelectId) {
    _targetSelectGrupo = targetSelectId;
    const nombreInput = document.getElementById('inline_grupo_nombre');
    const errDiv = document.getElementById('inline_grupo_error');
    if (nombreInput) nombreInput.value = '';
    if (errDiv) errDiv.style.display = 'none';
    const modalEl = document.getElementById('modalCrearGrupoInline');
    if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

async function guardarGrupoInline() {
    const nombre = (document.getElementById('inline_grupo_nombre')?.value || '').trim();
    const errDiv = document.getElementById('inline_grupo_error');
    const btn = document.getElementById('btn-guardar-grupo-inline');

    if (!nombre) {
        if (errDiv) {
            errDiv.textContent = 'Ingresa el nombre de la institución / sede.';
            errDiv.style.display = 'block';
        }
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Creando...';
    }

    try {
        const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';
        const resp = await fetch((window.APP_BASE || '') + '/admin/grupos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ nombre: nombre, tipo_grupo: 'general' })
        });

        const data = await resp.json();
        if (!resp.ok || !data.ok) {
            throw new Error(data.error || 'Error al crear la institución.');
        }

        const nuevoGrupo = data.grupo;

        // Añadir a todos los selects de grupo en la página
        document.querySelectorAll('select.select-grupo-institucion, select[name="grupo_id"]').forEach(sel => {
            const opt = document.createElement('option');
            opt.value = nuevoGrupo.id;
            opt.textContent = nuevoGrupo.nombre;
            sel.appendChild(opt);
        });

        // Seleccionar en el select origen
        if (_targetSelectGrupo) {
            const targetEl = document.getElementById(_targetSelectGrupo);
            if (targetEl) targetEl.value = nuevoGrupo.id;
        }

        // Cerrar modal
        const modalEl = document.getElementById('modalCrearGrupoInline');
        if (modalEl) {
            const modalInst = bootstrap.Modal.getInstance(modalEl);
            if (modalInst) modalInst.hide();
        }

        showToast("Institución / sede creada correctamente.", "success");

    } catch (err) {
        if (errDiv) {
            errDiv.textContent = err.message;
            errDiv.style.display = 'block';
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Crear';
        }
    }
}

// ── Creación Rápida Inline de Grupo de Trabajo (Grupo Funcional) ────────────
function abrirCrearGFRapido(targetSelectId) {
    _targetSelectGF = targetSelectId;
    const nombreInput = document.getElementById('inline_gf_nombre');
    const tipoSel = document.getElementById('inline_gf_tipo_persona_id');
    const errDiv = document.getElementById('inline_gf_error');
    if (nombreInput) nombreInput.value = '';
    if (tipoSel) tipoSel.value = '';
    if (errDiv) errDiv.style.display = 'none';
    const modalEl = document.getElementById('modalCrearGFInline');
    if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

async function guardarGFInline() {
    const nombre = (document.getElementById('inline_gf_nombre')?.value || '').trim();
    const tipoPersonaId = document.getElementById('inline_gf_tipo_persona_id')?.value || null;
    const errDiv = document.getElementById('inline_gf_error');
    const btn = document.getElementById('btn-guardar-gf-inline');

    if (!nombre) {
        if (errDiv) {
            errDiv.textContent = 'Ingresa el nombre del grupo de trabajo.';
            errDiv.style.display = 'block';
        }
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Creando...';
    }

    try {
        const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';
        const resp = await fetch((window.APP_BASE || '') + '/admin/grupos-funcionales', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ nombre: nombre, tipo_persona_id: tipoPersonaId })
        });

        const data = await resp.json();
        if (!resp.ok || !data.ok) {
            throw new Error(data.error || 'Error al crear el grupo de trabajo.');
        }

        const nuevoGF = data.grupo_funcional;

        // Añadir a todos los selects de grupos funcionales en la página
        document.querySelectorAll('select.select-grupo-funcional, select[name="grupo_funcional_id"]').forEach(sel => {
            const opt = document.createElement('option');
            opt.value = nuevoGF.id;
            opt.textContent = nuevoGF.nombre;
            sel.appendChild(opt);
        });

        // Seleccionar en el select origen
        if (_targetSelectGF) {
            const targetEl = document.getElementById(_targetSelectGF);
            if (targetEl) targetEl.value = nuevoGF.id;
        }

        // Cerrar modal
        const modalEl = document.getElementById('modalCrearGFInline');
        if (modalEl) {
            const modalInst = bootstrap.Modal.getInstance(modalEl);
            if (modalInst) modalInst.hide();
        }

        showToast("Grupo de trabajo creado exitosamente.", "success");

    } catch (err) {
        if (errDiv) {
            errDiv.textContent = err.message;
            errDiv.style.display = 'block';
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Crear Grupo';
        }
    }
}

// ── Submit AJAX para Formulario de Edición de Persona ───────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const formEditar = document.getElementById('formEditarPersona');
    if (formEditar) {
        formEditar.addEventListener('submit', async function(e) {
            e.preventDefault();

            const btnSubmit = document.getElementById('btn-guardar-persona-modal');
            if (btnSubmit) {
                btnSubmit.disabled = true;
                btnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Guardando...';
            }

            try {
                const formData = new FormData(formEditar);
                const resp = await fetch(formEditar.action, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json'
                    }
                });

                const data = await resp.json().catch(() => ({ ok: resp.ok }));
                if (!resp.ok || data.ok === false) {
                    throw new Error(data.error || 'Error al guardar los cambios de la persona.');
                }

                // Cerrar modal
                const modalEl = document.getElementById('modalEditarPersona');
                if (modalEl) {
                    const modalInst = bootstrap.Modal.getInstance(modalEl);
                    if (modalInst) modalInst.hide();
                }

                showToast("Datos del usuario guardados correctamente.", "success");

                // Actualizar cache local de personas
                const nombreNuevo = formData.get('nombre');
                cargarPersonasIniciales();

                // Si el nombre cambió, actualizar select y refrescar reporte
                if (tomSelectPersonaRapida && nombreNuevo) {
                    tomSelectPersonaRapida.setValue(nombreNuevo, false);
                }

                // Refrescar reporte en pantalla
                consultarReporteRapidoActual();

            } catch (err) {
                showToast(err.message, "danger");
            } finally {
                if (btnSubmit) {
                    btnSubmit.disabled = false;
                    btnSubmit.innerHTML = '<span class="material-symbols-outlined fs-6">save</span><span>Guardar cambios</span>';
                }
            }
        });
    }
});



