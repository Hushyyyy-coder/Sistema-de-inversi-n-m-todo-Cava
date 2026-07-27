"""
notificar.py — Alertas al movil via ntfy.sh (GRATIS)
=====================================================

ntfy.sh manda notificaciones al movil sin cuenta ni claves de API: solo un
"topic" (nombre de canal que eliges tu). Instala la app "ntfy" en el movil y
suscribete a ese mismo topic.

IMPORTANTE: el topic es como una contrasena. Usa un nombre largo y aleatorio
para que nadie mas pueda leer ni mandarte mensajes. Ej: cava-fred-x7k9q2m4

Configuracion (variable de entorno):
    NTFY_TOPIC = cava-fred-x7k9q2m4     (en GitHub: Secret del repositorio)

Uso:
    from notificar import enviar, esta_configurado
    enviar("Titulo", "Mensaje del cuerpo")
"""
from __future__ import annotations
import os

SERVIDOR = "https://ntfy.sh"


def _topic() -> str | None:
    return os.environ.get("NTFY_TOPIC")


def esta_configurado() -> bool:
    return bool(_topic())


def enviar(titulo: str, mensaje: str, prioridad: int = 3, emojis: str | None = None) -> bool:
    """
    Manda una notificacion al movil. Devuelve True si se envio bien.
    prioridad: ntfy usa 1-5 (3=normal, 4=alta, 5=urgente).
    emojis: etiquetas ntfy separadas por coma (ej. "chart_with_upwards_trend").
    """
    topic = _topic()
    if not topic:
        print("[ntfy] Falta NTFY_TOPIC en el entorno; no se envia.")
        return False
    try:
        import requests
    except ImportError:
        print("[ntfy] Falta la libreria 'requests'.")
        return False

    headers = {"Title": titulo.encode("utf-8"), "Priority": str(prioridad)}
    if emojis:
        headers["Tags"] = emojis
    try:
        r = requests.post(f"{SERVIDOR}/{topic}",
                          data=mensaje.encode("utf-8"),
                          headers=headers, timeout=15)
        if r.status_code == 200:
            return True
        print(f"[ntfy] Error HTTP {r.status_code}: {r.text[:120]}")
        return False
    except Exception as e:
        print(f"[ntfy] No se pudo enviar: {e}")
        return False


def enviar_prueba() -> bool:
    return enviar("Sistema Cava - prueba",
                  "Si lees esto en el movil, las alertas funcionan.",
                  prioridad=3, emojis="white_check_mark")
