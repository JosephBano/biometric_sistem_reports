from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from zk import ZK
import uvicorn
from datetime import datetime, time
from typing import Optional
import json

app = FastAPI()

# ⭐ CONFIGURAR CORS - ESTO ES LO MÁS IMPORTANTE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todas las fuentes (puedes restringir a dominios específicos)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEVICE_IP = "192.168.7.129"
DEVICE_PORT = 4370
DEVICE_PASSWORD = 12345

def parse_fecha(cadena: str, fin_de_dia: bool = False) -> datetime:
    """
    Convierte una cadena a datetime.
    - Si es solo fecha (YYYY-MM-DD) y fin_de_dia=False -> 00:00:00
    - Si es solo fecha (YYYY-MM-DD) y fin_de_dia=True  -> 23:59:59.999999
    - Si incluye hora (YYYY-MM-DDTHH:MM:SS) se respeta exactamente.
    """
    es_solo_fecha = len(cadena.strip()) == 10

    try:
        if es_solo_fecha:
            fecha = datetime.strptime(cadena, "%Y-%m-%d").date()
            if fin_de_dia:
                return datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59, 999999)
            else:
                return datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
        else:
            return datetime.fromisoformat(cadena)
    except ValueError:
        raise ValueError("Formato inválido. Use YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS")

@app.get("/asistencias")
async def get_asistencias(
    fecha_inicio: Optional[str] = Query(None, description="Fecha de inicio (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha de fin (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)")
):
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=DEVICE_PASSWORD)
    conn = None
    try:
        conn = zk.connect()
        attendances = conn.get_attendance()

        inicio_dt = None
        fin_dt = None
        if fecha_inicio:
            try:
                inicio_dt = parse_fecha(fecha_inicio, fin_de_dia=False)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        if fecha_fin:
            try:
                fin_dt = parse_fecha(fecha_fin, fin_de_dia=True)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        resultados = []
        for att in attendances:
            ts = att.timestamp

            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    continue
            elif not isinstance(ts, datetime):
                try:
                    ts = datetime.combine(ts, time.min)
                except Exception:
                    continue

            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)

            if inicio_dt and ts < inicio_dt:
                continue
            if fin_dt and ts > fin_dt:
                continue

            resultados.append({
                "id_usuario": att.user_id,
                "fecha_hora": ts.isoformat(),
                "tipo": att.punch
            })

        return resultados

    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e), "mensaje": "Error al obtener asistencias"}
    finally:
        if conn:
            conn.disconnect()


@app.get("/usuarios")
async def get_usuarios():
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=DEVICE_PASSWORD)
    conn = None
    try:
        conn = zk.connect()
        users = conn.get_users()
        return [
            {
                "id_usuario": user.user_id,
                "nombre": user.name,
                "privilegio": user.privilege,
                "contraseña": user.password
            }
            for user in users
        ]
    except Exception as e:
        return {"error": str(e), "mensaje": "Error al obtener usuarios"}
    finally:
        if conn:
            conn.disconnect()


@app.get("/asistencias-con-nombre")
async def get_asistencias_con_nombre(
    fecha_inicio: Optional[str] = Query(None, description="Fecha de inicio (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha de fin (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)")
):
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=DEVICE_PASSWORD)
    conn = None
    try:
        conn = zk.connect()
        users = conn.get_users()
        user_dict = {user.user_id: user.name for user in users}

        attendances = conn.get_attendance()

        inicio_dt = None
        fin_dt = None
        if fecha_inicio:
            try:
                inicio_dt = parse_fecha(fecha_inicio, fin_de_dia=False)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        if fecha_fin:
            try:
                fin_dt = parse_fecha(fecha_fin, fin_de_dia=True)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        resultados = []
        for att in attendances:
            ts = att.timestamp

            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    continue
            elif not isinstance(ts, datetime):
                try:
                    ts = datetime.combine(ts, time.min)
                except Exception:
                    continue

            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)

            if inicio_dt and ts < inicio_dt:
                continue
            if fin_dt and ts > fin_dt:
                continue

            # Asegurar que el nombre sea una cadena válida UTF-8
            nombre = user_dict.get(att.user_id, "Desconocido")
            if nombre:
                nombre = str(nombre).strip()
            
            resultados.append({
                "id_usuario": str(att.user_id),
                "nombre_usuario": nombre,
                "fecha_hora": ts.isoformat(),
                "tipo": int(att.punch)
            })

        return resultados

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener asistencias: {str(e)}")
    finally:
        if conn:
            conn.disconnect()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)