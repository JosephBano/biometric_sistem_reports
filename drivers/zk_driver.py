import os
from datetime import datetime, time as dt_time

try:
    from zk import ZK
    ZK_DISPONIBLE = True
except ImportError:
    ZK_DISPONIBLE = False

from drivers.base import BiometricDriver

class ZKDriver(BiometricDriver):
    """Driver para dispositivos biométricos ZKTeco usando pyzk."""

    def __init__(self, dispositivo: dict):
        super().__init__(dispositivo)
        
        self.ip = dispositivo.get('ip')
        self.port = dispositivo.get('puerto', 4370)
        self.timeout = dispositivo.get('timeout_seg', 120)
        self.udp = dispositivo.get('protocolo', 'tcp').lower() == 'udp'
        
        # Desencriptar la contraseña del dispositivo
        # Asume que si password_enc está vacío, usa 0 (default pyzk)
        from auth import decrypt_device_password
        pwd_enc = dispositivo.get('password_enc')
        
        # Retro-compatibilidad con la variable de entorno si pwd_enc es None (Fase 1/2)
        if pwd_enc:
            try:
                self.password = int(decrypt_device_password(pwd_enc))
            except Exception:
                self.password = int(os.getenv("ZK_PASSWORD", "0"))
        else:
            self.password = int(os.getenv("ZK_PASSWORD", "0"))

    def _make_zk(self):
        if not ZK_DISPONIBLE:
            raise RuntimeError("La librería pyzk no está instalada.")
        return ZK(
            self.ip,
            port=self.port,
            timeout=self.timeout,
            password=self.password,
            force_udp=self.udp,
            ommit_ping=True
        )

    def _punch_to_tipo(self, punch: int) -> str | None:
        """Convierte att.punch estándar ZK a 'Entrada' o 'Salida'."""
        _MAPA = {0: "Entrada", 1: "Salida", 2: "Salida",
                 3: "Entrada", 4: "Entrada", 5: "Salida"}
        return _MAPA.get(punch)

    def test_conexion(self) -> bool:
        if not ZK_DISPONIBLE:
            return False
        try:
            zk = ZK(self.ip, port=self.port, timeout=10, 
                    password=self.password, force_udp=self.udp, ommit_ping=True)
            conn = zk.connect()
            conn.disconnect()
            return True
        except Exception:
            return False

    def get_usuarios(self) -> list[dict]:
        zk = self._make_zk()
        conn = None
        try:
            conn = zk.connect()
            usuarios = conn.get_users()
            return [
                {
                    "id_usuario": str(u.user_id),
                    "nombre": str(u.name).strip(),
                    "privilegio": u.privilege
                } for u in usuarios
            ]
        finally:
            if conn:
                try: conn.disconnect()
                except: pass

    def get_asistencias(self, desde: datetime = None) -> list[dict]:
        zk = self._make_zk()
        conn = None
        registros = []
        try:
            conn = zk.connect()
            # Cache de usuarios para mapear IDs a nombres (útil pero nombre en BD manda)
            user_dict = {str(u.user_id): str(u.name).strip() for u in conn.get_users()}
            
            attendances = conn.get_attendance()
            
            for att in attendances:
                ts = att.timestamp
                if not isinstance(ts, datetime):
                    try: ts = datetime.combine(ts, dt_time.min)
                    except Exception: continue
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                
                # Filtrar desde (si aplica)
                if desde and ts <= desde:
                    continue

                tipo = self._punch_to_tipo(att.punch)
                if tipo is None:
                    continue

                nombre = user_dict.get(str(att.user_id), f"Usuario {att.user_id}")
                
                registros.append({
                    "id_usuario": str(att.user_id),
                    "nombre": nombre,
                    "fecha_hora": ts,
                    "punch_raw": att.punch,
                    "tipo": tipo,
                    "fuente": "zk"
                })
            
            return registros
        finally:
            if conn:
                try: conn.disconnect()
                except: pass

    def clear_asistencias(self) -> int:
        zk = self._make_zk()
        conn = None
        try:
            conn = zk.connect()
            total = len(conn.get_attendance())
            conn.clear_attendance()
            return total
        finally:
            if conn:
                try: conn.disconnect()
                except: pass

    def get_capacidad(self) -> dict:
        total = 0
        cap_max = int(os.getenv("ZK_CAPACIDAD_MAX", "100000"))
        try:
            zk = self._make_zk()
            conn = zk.connect()
            total = len(conn.get_attendance())
            conn.disconnect()
        except:
            pass
        return {
            "total_registros": total,
            "capacidad_max": cap_max
        }
