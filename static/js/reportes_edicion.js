// static/js/reportes_edicion.js
// Modulo 4: Gestion inline de colaboradores, horarios y grupos desde reportes

// ════════════════════════════════════════════════════════════════════════════
// GESTIÓN DE USUARIOS Y HORARIOS DESDE EL MÓDULO DE REPORTES
// ════════════════════════════════════════════════════════════════════════════

var _personaEnEdicion = null;
var _targetSelectGrupo = null;
var _targetSelectGF = null;

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



