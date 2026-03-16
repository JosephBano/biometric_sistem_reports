let tomSelectPersonaRpt = null;

document.addEventListener('DOMContentLoaded', () => {
    setMesActual();

    tomSelectPersonaRpt = new TomSelect('#persona', {
        placeholder: 'Buscar persona...',
        allowEmptyOption: true,
        maxOptions: 200,
        create: false,
    });

    actualizarVisibilidadModo();

    document.getElementById('fecha-inicio').addEventListener('change', reloadPersonas);
    document.getElementById('fecha-fin').addEventListener('change', reloadPersonas);

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

function setMesActual() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const lastDay = new Date(y, now.getMonth() + 1, 0).getDate();
    document.getElementById('fecha-inicio').value = `${y}-${m}-01`;
    document.getElementById('fecha-fin').value = `${y}-${m}-${String(lastDay).padStart(2, '0')}`;
    reloadPersonas();
}

function setSemanaActual() {
    const now = new Date();
    const diaSemana = now.getDay() === 0 ? 6 : now.getDay() - 1; // Lunes=0, Dom=6
    const lunes = new Date(now);
    lunes.setDate(now.getDate() - diaSemana);
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    
    document.getElementById('fecha-inicio').value = formatIsoDate(lunes);
    document.getElementById('fecha-fin').value = formatIsoDate(domingo);
    reloadPersonas();
}

function setMesAnterior() {
    const now = new Date();
    let y = now.getFullYear();
    let m = now.getMonth(); // 0-based
    
    if (m === 0) {
        m = 12;
        y--;
    }
    
    const lastDay = new Date(y, m, 0).getDate(); // last day of prev month
    
    document.getElementById('fecha-inicio').value = `${y}-${String(m).padStart(2,'0')}-01`;
    document.getElementById('fecha-fin').value = `${y}-${String(m).padStart(2,'0')}-${String(lastDay).padStart(2,'0')}`;
    reloadPersonas();
}

function formatIsoDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function actualizarVisibilidadModo() {
    const v = document.getElementById('modo').value;
    const esGeneral = v === 'general';

    document.getElementById('persona-group').style.display = v === 'persona' ? 'block' : 'none';
    document.getElementById('varias-group').style.display = v === 'varias' ? 'block' : 'none';
    document.getElementById('especiales-group').style.display = esGeneral ? 'block' : 'none';

    // Grupo de filtros exclusivos de persona/varias
    const grupoPersona = document.getElementById('filtros-persona-only');
    if (grupoPersona) {
        grupoPersona.style.display = esGeneral ? 'none' : 'block';
        // Al cambiar a general, desactivar los filtros que no aplican
        // para que no se envíen como activos y confundan al backend
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
    const v = document.getElementById('modo').value;
    if (v === 'persona') loadPersonasSingle();
    if (v === 'varias') loadPersonasVarias();
}

function loadPersonasSingle() {
    const fi = document.getElementById('fecha-inicio').value;
    const ff = document.getElementById('fecha-fin').value;
    if (!fi || !ff) return;

    apiCall('/api/personas-db?fecha_inicio=' + fi + '&fecha_fin=' + ff)
        .then(data => {
            tomSelectPersonaRpt.clear();
            tomSelectPersonaRpt.clearOptions();
            if(data.personas) {
                data.personas.forEach(p => {
                    tomSelectPersonaRpt.addOption({ value: p, text: p });
                });
            }
        });
}

function loadPersonasVarias() {
    const fi = document.getElementById('fecha-inicio').value;
    const ff = document.getElementById('fecha-fin').value;
    if (!fi || !ff) return;

    apiCall('/api/personas-db?fecha_inicio=' + fi + '&fecha_fin=' + ff)
        .then(data => {
            const sel = document.getElementById('personas-varias');
            sel.innerHTML = '';
            (data.personas || []).forEach(p => {
                const opt = document.createElement('option');
                opt.value = p;
                opt.textContent = p;
                sel.appendChild(opt);
            });
        });
}

function seleccionarTodasPersonas() {
    const sel = document.getElementById('personas-varias');
    for (let i = 0; i < sel.options.length; i++) {
        sel.options[i].selected = true;
    }
}
function deseleccionarTodasPersonas() {
    const sel = document.getElementById('personas-varias');
    for (let i = 0; i < sel.options.length; i++) {
        sel.options[i].selected = false;
    }
}

function leerFiltros() {
    const chk = id => { const el = document.getElementById(id); return el ? el.checked : false; };
    return {
        mostrar_ausencias:          chk('f-ausencias'),
        mostrar_tardanza_severa:    chk('f-tardanza-severa'),
        mostrar_tardanza_leve:      chk('f-tardanza-leve'),
        mostrar_almuerzo:           chk('f-almuerzo'),
        mostrar_incompletos:        chk('f-incompletos'),
        mostrar_salida_anticipada:  chk('f-salida-anticipada'),
        mostrar_todos_los_dias:     chk('f-todos-dias'),
        columna_tiempo_dentro:      chk('f-tiempo-dentro'),
        reporte_sin_horario:        chk('f-sin-horario'),
        reporte_todos_usuarios:     chk('f-todos-usuarios'),
        verificar_horas:            chk('f-horas-contrato'),
        mostrar_tiempo_extra:       chk('f-tiempo-extra'),
    };
}

function generarReporte() {
    const btn = document.getElementById('btn-submit');
    const spinner = document.getElementById('loading-spinner');
    
    const fi = document.getElementById('fecha-inicio').value;
    const ff = document.getElementById('fecha-fin').value;
    const excl = document.getElementById('excluidos').value.split(',').map(s => s.trim()).filter(s => s);
    const filtros = leerFiltros();
    const modo = document.getElementById('modo').value;

    const payload = {
        fecha_inicio: fi,
        fecha_fin: ff,
        modo: modo,
        filtros: filtros,
        excluidos: excl
    };

    if (modo === 'persona') {
        const p = tomSelectPersonaRpt.getValue();
        if (!p) return showError("Debe seleccionar una persona.");
        payload.persona = p;
    } else if (modo === 'varias') {
        const sel = document.getElementById('personas-varias');
        const elegidas = Array.from(sel.selectedOptions).map(o => o.value);
        if (elegidas.length === 0) return showError("Debe seleccionar al menos una persona.");
        payload.personas = elegidas;
    }

    spinner.style.display = 'block';
    btn.disabled = true;

    // Use raw fetch for download capability
    fetch('/api/generar-desde-db', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
    .then(r => r.json().then(data => ({status: r.status, ok: r.ok, body: data})))
    .then(res => {
        spinner.style.display = 'none';
        btn.disabled = false;
        if (!res.ok) throw new Error(res.body.error || 'Error generando reporte');
        
        showSuccess('Reporte generado. Descargando...');
        
        const a = document.createElement('a');
        a.href = res.body.download_url;
        a.download = res.body.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    })
    .catch(err => {
        spinner.style.display = 'none';
        btn.disabled = false;
        showError("Error al generar: " + err.message);
    });
}

function enviarPorEmail() {
    const btn = document.querySelector('#persona-group button');
    const emailInput = document.getElementById('email-destino');
    const loading = document.getElementById('loading-spinner');
    
    const email = emailInput ? emailInput.value.trim() : '';
    if (!email) return showError("Debe ingresar un correo electrónico.");
    if (!email.includes('@') || !email.includes('.')) {
        return showError("Formato de correo inválido.");
    }
    
    const fi = document.getElementById('fecha-inicio').value;
    const ff = document.getElementById('fecha-fin').value;
    const excl = document.getElementById('excluidos').value.split(',').map(s => s.trim()).filter(s => s);
    const filtros = leerFiltros();
    const p = tomSelectPersonaRpt ? tomSelectPersonaRpt.getValue() : '';

    if (!p) return showError("Debe seleccionar una persona.");
    if (!fi || !ff) return showError("Debe seleccionar un rango de fechas.");

    const payload = {
        fecha_inicio: fi,
        fecha_fin: ff,
        persona: p,
        email: email,
        filtros: filtros,
        excluidos: excl
    };

    if(loading) loading.style.display = 'block';
    if(btn) btn.disabled = true;

    apiCall('/api/reportes/enviar-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(data => {
        if(loading) loading.style.display = 'none';
        if(btn) btn.disabled = false;
        showSuccess(data.message || 'Reporte enviado por correo correctamente.');
        if(emailInput) emailInput.value = '';
    })
    .catch(err => {
        if(loading) loading.style.display = 'none';
        if(btn) btn.disabled = false;
        showError("Error al enviar: " + err.message);
    });
}
