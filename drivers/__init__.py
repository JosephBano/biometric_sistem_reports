from drivers.base import BiometricDriver
from drivers.zk_driver import ZKDriver
from drivers.hikvision_driver import HikvisionDriver

def get_driver(dispositivo: dict) -> BiometricDriver:
    """
    Factory: devuelve el driver adecuado según el tipo_driver configurado 
    en el diccionario del dispositivo.
    """
    tipo = dispositivo.get('tipo_driver', 'zk').lower()
    
    drivers = {
        'zk': ZKDriver,
        'hikvision': HikvisionDriver
    }
    
    cls = drivers.get(tipo)
    if not cls:
        # Fallback a ZK
        cls = ZKDriver
        
    return cls(dispositivo)
