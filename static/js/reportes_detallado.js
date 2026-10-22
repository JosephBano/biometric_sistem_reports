// static/js/reportes_detallado.js
// Modulo 3: Periodos detallados, dual listbox de seleccion masiva y exportacion

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

