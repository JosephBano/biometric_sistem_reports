let _horariosCache = [];
let offcanvasHorario = null;

document.addEventListener('DOMContentLoaded', () => {
    offcanvasHorario = new bootstrap.Offcanvas(document.getElementById('offcanvas-horario'));
    
    // Listeners for uploads
    const hi = document.getElementById('horarios-input');
    if (hi) hi.addEventListener('change', e => {
        if (e.target.files.length > 0) importarHorarios(e.target.files[0]);
    });

    const fi = document.getElementById('feriados-import-file');
    if (fi) fi.addEventListener('change', e => {
        if (e.target.files.length > 0) importarFeriados(e.target.files[0]);
    });

    cargarHorarios();
    cargarFeriados();
});

// ════════════ HORARIOS ════════════════════════

function cargarHorarios() {
    apiCall('/api/horarios')
        .then(data => {
            _horariosCache = data.horarios || [];
            document.getElementById('horarios-count').textContent = data.total || 0;
            renderTablaHorarios(_horariosCache);
        })
        .catch(err => {
            const tbody = document.getElementById('horarios-tbody');
            if(tbody) tbody.innerHTML = `<tr><td colspan="13" class="text-danger text-center py-4">Error cargando horarios: ${err}</td></tr>`;
        });
}

function filtrarTablaHorarios() {
    const q = document.getElementById('search-horarios').value.toLowerCase();
    if (!q) {
        renderTablaHorarios(_horariosCache);
        return;
    }
    const filtrados = _horariosCache.filter(h => 
        (h.nombre && h.nombre.toLowerCase().includes(q)) || 
        (h.id_usuario && String(h.id_usuario).includes(q)) ||
        (h.notas && h.notas.toLowerCase().includes(q))
    );
    renderTablaHorarios(filtrados);
}

function renderTablaHorarios(lista) {
    const tbody = document.getElementById('horarios-tbody');
    if (!tbody) return;

    if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="13" class="text-center text-muted py-4">No hay horarios.</td></tr>';
        return;
    }

    const html = lista.map(h => {
        // Muestra "entrada / salida" o solo "entrada" si no hay salida configurada
        const d = dia => {
            const ent = h[dia];
            const sal = h[`${dia}_salida`];
            if (!ent) return '<span class="text-muted">—</span>';
            if (sal) return `<span class="text-nowrap">${ent}<br><small class="text-muted">${sal}</small></span>`;
            return ent;
        };
        const hasOverrides = DIAS.some(d => h[`${d}_almuerzo_min`] !== null && h[`${d}_almuerzo_min`] !== undefined);
        const alm = h.almuerzo_min ? `${h.almuerzo_min} m${hasOverrides ? '*' : ''}` : (hasOverrides ? 'Variable*' : '<span class="text-muted">0</span>');
        
        let hContrato = '<span class="text-muted">—</span>';
        if (h.horas_semana) hContrato = `<span class="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25">${h.horas_semana}h/sem</span>`;
        else if (h.horas_mes) hContrato = `<span class="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25">${h.horas_mes}h/mes</span>`;

        const hJson = JSON.stringify(h).replace(/"/g, '&quot;');
        const notas = h.notas ? `<span class="text-muted" style="font-size: 0.75rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; max-width: 150px;" title="${h.notas}">${h.notas}</span>` : '<span class="text-muted">—</span>';

        return `
            <tr>
                <td class="fw-semibold text-nowrap">${h.nombre}</td>
                <td><span class="badge bg-light text-dark border">${h.id_usuario}</span></td>
                <td>${d('lunes')}</td>
                <td>${d('martes')}</td>
                <td>${d('miercoles')}</td>
                <td>${d('jueves')}</td>
                <td>${d('viernes')}</td>
                <td>${d('sabado')}</td>
                <td>${d('domingo')}</td>
                <td class="text-center">${alm}</td>
                <td class="text-center">${hContrato}</td>
                <td>${notas}</td>
                <td class="text-end text-nowrap">
                    <button class="btn btn-sm btn-outline-primary py-0 px-2" onclick="abrirOffcanvasEditar(${hJson})" title="Editar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">edit</span></button>
                    <button class="btn btn-sm btn-outline-danger py-0 px-2 ms-1" onclick="eliminarHorario('${h.id_usuario}', '${h.nombre}')" title="Eliminar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">delete</span></button>
                </td>
            </tr>
        `;
    }).join("");
    tbody.innerHTML = html;
}

function importarHorarios(file) {
    if (!file) return;
    document.getElementById('horarios-upload-progress').style.display = 'block';

    const formData = new FormData();
    formData.append('archivo', file);

    fetch('/api/horarios/importar', { method: 'POST', body: formData })
        .then(response => response.json().then(data => ({ status: response.status, ok: response.ok, body: data })))
        .then(res => {
            document.getElementById('horarios-upload-progress').style.display = 'none';
            document.getElementById('horarios-input').value = '';
            if (!res.ok) throw new Error(res.body.error || 'Error desconocido');

            let meta = "";
            if (res.body.sin_match_zk && res.body.sin_match_zk.length > 0) {
                meta = `\nAdvertencia: ${res.body.sin_match_zk.length} IDs en el archivo no existen en el dispositivo ZK.`;
            }
            showSuccess(`Se importaron ${res.body.total_cargados} horarios correctamente.${meta}`);
            cargarHorarios();
        })
        .catch(err => {
            document.getElementById('horarios-upload-progress').style.display = 'none';
            document.getElementById('horarios-input').value = '';
            showError("Error al importar: " + err.message);
        });
}

function exportarHorariosCsv() {
    window.location.href = '/api/horarios/exportar';
}

const DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];

function abrirOffcanvasCrear() {
    document.getElementById('mh-modo').value = 'crear';
    document.getElementById('offcanvasHorarioLabel').textContent = 'Crear Horario';
    document.getElementById('mh-id').value = '';
    document.getElementById('mh-id').readOnly = false;
    document.getElementById('mh-nombre').value = '';
    document.getElementById('mh-error').style.display = 'none';
    document.getElementById('mh-notas').value = '';
    document.getElementById('mh-almuerzo').value = '0';

    DIAS.forEach(d => {
        document.getElementById(`mh-${d}`).value = '';
        document.getElementById(`mh-${d}-salida`).value = '';
        const isWeekend = (d === 'sabado' || d === 'domingo');
        document.getElementById(`mh-libre-${d}`).checked = isWeekend;
        toggleDia(d);
    });

    document.getElementById('tipoHorasNone').checked = true;
    document.getElementById('mh-horas-semana').value = '';
    document.getElementById('mh-horas-mes').value = '';
    toggleTipoHoras();

    offcanvasHorario.show();
}

function abrirOffcanvasEditar(h) {
    document.getElementById('mh-modo').value = 'editar';
    document.getElementById('offcanvasHorarioLabel').textContent = `Editar: ${h.nombre}`;
    document.getElementById('mh-id').value = h.id_usuario;
    document.getElementById('mh-id').readOnly = true;
    document.getElementById('mh-nombre').value = h.nombre;
    document.getElementById('mh-error').style.display = 'none';
    document.getElementById('mh-notas').value = h.notas || '';
    document.getElementById('mh-almuerzo').value = h.almuerzo_min || '0';

    DIAS.forEach(d => {
        if (h[d]) {
            document.getElementById(`mh-${d}`).value = h[d];
            document.getElementById(`mh-libre-${d}`).checked = false;
        } else {
            document.getElementById(`mh-${d}`).value = '';
            document.getElementById(`mh-libre-${d}`).checked = true;
        }
        // Rellenar hora de salida si existe
        const salidaKey = `${d}_salida`;
        document.getElementById(`mh-${d}-salida`).value = h[salidaKey] || '';
        toggleDia(d);
    });

    // Horas de contrato
    if (h.horas_semana) {
        document.getElementById('tipoHorasSemana').checked = true;
        document.getElementById('mh-horas-semana').value = h.horas_semana;
        document.getElementById('mh-horas-mes').value = '';
    } else if (h.horas_mes) {
        document.getElementById('tipoHorasMes').checked = true;
        document.getElementById('mh-horas-mes').value = h.horas_mes;
        document.getElementById('mh-horas-semana').value = '';
    } else {
        document.getElementById('tipoHorasNone').checked = true;
        document.getElementById('mh-horas-semana').value = '';
        document.getElementById('mh-horas-mes').value = '';
    }
    toggleTipoHoras();

    offcanvasHorario.show();
}

function toggleDia(dia) {
    const isLibre = document.getElementById(`mh-libre-${dia}`).checked;
    const inputHora = document.getElementById(`mh-${dia}`);
    const inputSalida = document.getElementById(`mh-${dia}-salida`);
    inputHora.disabled = isLibre;
    inputSalida.disabled = isLibre;
    if (isLibre) {
        inputHora.value = '';
        inputSalida.value = '';
    }
}

function toggleTipoHoras() {
    const tipo = document.querySelector('input[name="tipoHoras"]:checked').value;
    document.getElementById('div-horas-semana').style.display = (tipo === 'semana') ? 'block' : 'none';
    document.getElementById('div-horas-mes').style.display = (tipo === 'mes') ? 'block' : 'none';
}

function guardarHorario() {
    const modo = document.getElementById('mh-modo').value;
    const idUsuario = document.getElementById('mh-id').value;
    const nombre = document.getElementById('mh-nombre').value;

    if (!idUsuario) return errMh("El ID es requerido.");
    if (!nombre) return errMh("El nombre es requerido.");

    const payload = {
        id_usuario: idUsuario,
        nombre: nombre,
        almuerzo_min: parseInt(document.getElementById('mh-almuerzo').value) || 0,
        notas: document.getElementById('mh-notas').value,
        horas_semana: null,
        horas_mes: null
    };

    const tipoH = document.querySelector('input[name="tipoHoras"]:checked').value;
    if (tipoH === 'semana') {
        const val = document.getElementById('mh-horas-semana').value;
        if (!val) return errMh("Especifique las horas semanales.");
        payload.horas_semana = parseFloat(val);
    } else if (tipoH === 'mes') {
        const val = document.getElementById('mh-horas-mes').value;
        if (!val) return errMh("Especifique las horas mensuales.");
        payload.horas_mes = parseFloat(val);
    }

    let countActivos = 0;
    for (const d of DIAS) {
        if (!document.getElementById(`mh-libre-${d}`).checked) {
            const h = document.getElementById(`mh-${d}`).value;
            if (!h) return errMh(`Especifique la hora de entrada para ${d} o márquelo como libre.`);
            payload[d] = h;
            // Agregar hora de salida si fue especificada (opcional)
            const salida = document.getElementById(`mh-${d}-salida`).value;
            if (salida) payload[`${d}_salida`] = salida;
            countActivos++;
        }
    }

    if (countActivos === 0) return errMh("Debe configurar al menos un día laborable.");

    const url = modo === 'crear' ? '/api/horarios' : `/api/horarios/${idUsuario}`;
    const method = modo === 'crear' ? 'POST' : 'PUT';

    apiCall(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(data => {
        offcanvasHorario.hide();
        showSuccess(`Horario de ${nombre} ${modo === 'crear' ? 'creado' : 'actualizado'} correctamente.`);
        cargarHorarios();
    })
    .catch(err => errMh(err.message));
}

function errMh(msg) {
    const e = document.getElementById('mh-error');
    e.textContent = msg;
    e.style.display = 'block';
}

function eliminarHorario(idStr, nombre) {
    if (!confirm(`¿Está seguro de eliminar el horario de ${nombre}?`)) return;
    apiCall(`/api/horarios/${idStr}`, { method: 'DELETE' })
    .then(() => {
        showSuccess(`Horario de ${nombre} eliminado.`);
        cargarHorarios();
    })
    .catch(err => showError(`Error eliminando horario: ${err.message}`));
}

// ════════════ FERIADOS ════════════════════════

function cargarFeriados() {
    apiCall('/api/feriados')
        .then(data => {
            const listaDiv = document.getElementById('feriados-lista');
            if(!listaDiv) return;
            
            if (!data.feriados || data.feriados.length === 0) {
                listaDiv.innerHTML = '<p class="text-muted small mb-0 p-3 bg-white border rounded">No hay feriados registrados.</p>';
                return;
            }
            
            // Agrupar por mes y año a futuro si hay muchos, 
            // pero mantenemos la lista plana elegante por ahora
            
            const badges = {
                'nacional': '<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25 px-2">Nacional</span>',
                'local': '<span class="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25 px-2">Local</span>',
                'institucional': '<span class="badge bg-warning bg-opacity-10 text-warning border border-warning border-opacity-25 px-2">Institucional</span>'
            };

            let html = '<table class="table table-sm table-hover align-middle bg-white mb-0 border rounded overflow-hidden"><tbody>';
            data.feriados.forEach(f => {
                const b = badges[f.tipo] || `<span class="badge bg-secondary">${f.tipo}</span>`;
                html += `
                    <tr>
                        <td style="width: 120px;" class="fw-semibold">${f.fecha}</td>
                        <td>${f.descripcion}</td>
                        <td style="width: 100px;">${b}</td>
                        <td class="text-end" style="width: 60px;">
                            <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="eliminarFeriado('${f.fecha}')" title="Eliminar"><span class="material-symbols-outlined" style="font-size: 1rem; vertical-align: middle;">delete</span></button>
                        </td>
                    </tr>
                `;
            });
            html += '</tbody></table>';
            listaDiv.innerHTML = html;
        });
}

function agregarFeriado() {
    const fecha = document.getElementById('feriado-fecha').value;
    const desc = document.getElementById('feriado-descripcion').value.trim();
    const tipo = document.getElementById('feriado-tipo').value;

    if (!fecha || !desc) {
        showError('Fecha y descripción son requeridos para el feriado.');
        return;
    }

    apiCall('/api/feriados', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fecha, descripcion: desc, tipo })
    })
    .then(() => {
        document.getElementById('feriado-fecha').value = '';
        document.getElementById('feriado-descripcion').value = '';
        cargarFeriados();
        showSuccess('Feriado agregado correctamente.');
    })
    .catch(err => showError(err.message));
}

function eliminarFeriado(fecha) {
    if (!confirm('¿Eliminar el feriado del ' + fecha + '?')) return;
    apiCall(`/api/feriados/${fecha}`, { method: 'DELETE' })
        .then(() => {
            cargarFeriados();
            showSuccess('Feriado eliminado.');
        })
        .catch(err => showError(err.message));
}

function importarFeriados(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append('archivo', file);

    fetch('/api/feriados/importar', { method: 'POST', body: formData })
        .then(response => response.json().then(data => ({ status: response.status, ok: response.ok, body: data })))
        .then(res => {
            document.getElementById('feriados-import-file').value = '';
            if (!res.ok) throw new Error(res.body.error || 'Error desconocido');
            showSuccess(`Se importaron ${res.body.total_importados} feriados.`);
            cargarFeriados();
        })
        .catch(err => {
            document.getElementById('feriados-import-file').value = '';
            showError("Error: " + err.message);
        });
}

function exportarFeriados() {
    window.location.href = "/api/feriados/exportar";
}
