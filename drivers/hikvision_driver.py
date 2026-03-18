from datetime import datetime
import requests

from drivers.base import BiometricDriver

class HikvisionDriver(BiometricDriver):
    """
    Comunicación vía HTTP ISAPI de Hikvision.
    Nota: Esto es una implementación básica / de andamiaje. 
    En Hikvision, se debe usar digest auth y XMLs, o JSON si lo soporta.
    """

    def __init__(self, dispositivo: dict):
        super().__init__(dispositivo)
        
        self.ip = dispositivo.get('ip')
        self.port = dispositivo.get('puerto', 80)
        protocolo = dispositivo.get('protocolo', 'http').lower()
        if protocolo not in ('http', 'https'):
            protocolo = 'http'
        
        self.base_url = f"{protocolo}://{self.ip}:{self.port}/ISAPI"
        
        # Desencriptar la contraseña del dispositivo
        from auth import decrypt_device_password
        self.username = "admin" # asume usuario admin para ISAPI
        pwd_enc = dispositivo.get('password_enc')
        
        if pwd_enc:
            try:
                self.password = decrypt_device_password(pwd_enc)
            except Exception:
                self.password = ""
        else:
            self.password = ""

    def _get_auth(self):
        from requests.auth import HTTPDigestAuth
        return HTTPDigestAuth(self.username, self.password)

    def test_conexion(self) -> bool:
        """Ping básico al endpoint ISAPI/System/deviceInfo"""
        url = f"{self.base_url}/System/deviceInfo"
        try:
            resp = requests.get(url, auth=self._get_auth(), timeout=5)
            # 200 OK y aveces 401 si falla pero la IP si dio ping (aunque ISAPI restringe)
            return resp.status_code == 200
        except Exception:
            return False

    def get_usuarios(self) -> list[dict]:
        """Obtiene la lista de usuarios vía ISAPI/AccessControl/UserInfo"""
        # Implementación mock/básica
        url = f"{self.base_url}/AccessControl/UserInfo/Search?format=json"
        payload = {
            "UserInfoSearchCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": 1000
            }
        }
        res_usuarios = []
        try:
            resp = requests.post(url, json=payload, auth=self._get_auth(), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                users = data.get("UserInfoSearch", {}).get("UserInfo", [])
                for u in users:
                    res_usuarios.append({
                        "id_usuario": u.get("employeeNo"),
                        "nombre": u.get("name", ""),
                        "privilegio": 0
                    })
        except Exception:
            pass
        return res_usuarios

    def get_asistencias(self, desde: datetime = None) -> list[dict]:
        """Obtiene eventos vía ISAPI/AccessControl/AcsEvent"""
        url = f"{self.base_url}/AccessControl/AcsEvent?format=json"
        
        startTime = (desde or datetime(2000, 1, 1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        
        payload = {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": 1000,
                "major": 5, # Access Control Event
                "minor": 75, # Ej. Card or Fingerprint Authentication
                "startTime": startTime,
            }
        }
        
        registros = []
        try:
            resp = requests.post(url, json=payload, auth=self._get_auth(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("AcsEvent", {}).get("InfoList", [])
                for ev in events:
                    # Hikvision devuelve YYYY-MM-DDTHH:MM:SS+08:00
                    ts_str = ev.get("time", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace('+08:00', '+00:00'))
                        ts = ts.replace(tzinfo=None)
                    except:
                        continue
                        
                    # Filtrar eventos
                    if desde and ts <= desde:
                        continue
                        
                    registros.append({
                        "id_usuario": ev.get("employeeNoString"),
                        "nombre": ev.get("name", "Usuario"),
                        "fecha_hora": ts,
                        "punch_raw": 0,
                        "tipo": "Entrada", # En Hikvision la dirección a veces viene en otro campo
                        "fuente": "hikvision"
                    })
        except Exception:
            pass
            
        return registros

    def clear_asistencias(self) -> int:
        return 0 # No soportado o riesgoso por ahora

    def get_capacidad(self) -> dict:
        return {
            "total_registros": 0,
            "capacidad_max": 100000
        }
