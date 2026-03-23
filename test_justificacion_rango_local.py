import os
import sys
import json
sys.path.append('.')

from db import insertar_justificacion, get_justificaciones, listar_personas

print("--- INICIANDO TEST REGISTRO RANGO ---")

try:
    personas = listar_personas(activo=None)
    if not personas:
        print("No hay personas en la BD para probar.")
        sys.exit(0)
        
    p = personas[0]
    print(f"Probando con persona: {p['nombre']}")
    
    # Inserción
    res = insertar_justificacion(
        id_usuario=str(p['id']),
        nombre=p['nombre'],
        fecha='2026-05-01', 
        tipo='tardanza',
        motivo='Prueba Rango Automatizada',
        recuperable=1,
        fecha_recuperacion='2026-05-02',
        hora_recuperacion='08:30',
        hora_recuperacion_fin='10:45'
    )
    print("Resultado Inserción:", json.dumps(res, indent=2))
    
    # Verificación
    justs = get_justificaciones('2026-05-01', '2026-05-01')
    ok = False
    for j in justs:
        if j['nombre'] == p['nombre'] and j['tipo'] == 'tardanza':
            print("\nJustificación encontrada!")
            print(f"Desde: {j.get('hora_recuperacion')}")
            print(f"Hasta: {j.get('hora_recuperacion_fin')}")
            if j.get('hora_recuperacion_fin') == "10:45:00":
                print("\n✅ PRUEBA SUPERADA: hora_recuperacion_fin guardada correctamente.")
                ok = True
                
    if not ok:
        print("\n❌ PRUEBA FALLIDA: Falta hora_recuperacion_fin.")

except Exception as e:
    print(f"\n❌ ERROR EN PRUEBA: {str(e)}")
