// static/js/reportes_rapido.js
// Modulo 1: Carga de personas, filtros rapidos, renderizado paginado en pantalla

var tomSelectPersonaRpt = null;
var tomSelectPersonaRapida = null;
var personasCache = [];
var ultimaPersonaConsultada = '';
var _horariosCache = [];
var offcanvasHorario = null;

// Estado de paginación para el reporte diario en pantalla
var diasReporteActual = [];
var diasPorFechaReporte = {};
var currentPageReportes = 1;
var PAGE_SIZE_REPORTES = 15;

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

// Usa esc() unificado de api.js
// (definicion delegada a window.esc)

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

