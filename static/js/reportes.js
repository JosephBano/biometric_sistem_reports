/**
 * static/js/reportes.js
 * 
 * Módulo orquestador de reportes.
 * El código monolítico original (~2000 líneas) ha sido dividido en 4 módulos
 * cohesivos (< 800 líneas cada uno) según los criterios del Issue #10:
 *   - reportes_rapido.js: Filtros rápidos, paginación y renderizado en pantalla
 *   - reportes_marcaciones.js: Modal enterprise de marcaciones, descargas y envío por correo
 *   - reportes_detallado.js: Configuración detallada, dual listbox y exportación
 *   - reportes_edicion.js: Modales y offcanvas de edición inline de usuario y horarios
 */
(function () {
    const modules = [
        'reportes_rapido.js',
        'reportes_marcaciones.js',
        'reportes_detallado.js',
        'reportes_edicion.js'
    ];

    // Si ya fueron incluidos directamente en el HTML, evitar doble inyección
    if (typeof window.consultarReporteRapidoActual === 'function') {
        return;
    }

    const basePath = (typeof window.APP_BASE !== 'undefined' ? window.APP_BASE : '') + '/static/js/';
    modules.forEach(function (file) {
        const s = document.createElement('script');
        s.src = basePath + file;
        s.async = false;
        document.head.appendChild(s);
    });
})();
