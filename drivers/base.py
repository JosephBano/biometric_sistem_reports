from datetime import datetime

class BiometricDriver:
    """Clase base para todos los drivers biométricos."""
    
    def __init__(self, dispositivo: dict):
        self.dispositivo = dispositivo

    def test_conexion(self) -> bool:
        """Verifica si el dispositivo responde a un ping básico."""
        raise NotImplementedError

    def get_usuarios(self) -> list[dict]:
        """
        Retorna la lista de usuarios en el dispositivo.
        Formato esperado por dict:
        {
            "id_usuario": str,
            "nombre": str,
            "privilegio": int
        }
        """
        raise NotImplementedError

    def get_asistencias(self, desde: datetime = None) -> list[dict]:
        """
        Retorna las marcaciones del dispositivo, opcionalmente a partir de la fecha `desde`.
        Formato esperado por dict:
        {
            "id_usuario": str,
            "nombre": str,
            "fecha_hora": datetime,
            "punch_raw": int,
            "tipo": str,  # 'Entrada' o 'Salida'
            "fuente": str  # 'zk' o 'hikvision'
        }
        """
        raise NotImplementedError

    def clear_asistencias(self) -> int:
        """Elimina todos los registros de asistencia en el dispositivo."""
        raise NotImplementedError

    def get_capacidad(self) -> dict:
        """
        Retorna la capacidad del dispositivo.
        Formato esperado por dict:
        {
            "total_registros": int,
            "capacidad_max": int
        }
        """
        raise NotImplementedError
