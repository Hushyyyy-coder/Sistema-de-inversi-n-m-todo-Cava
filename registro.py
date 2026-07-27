"""
registro.py — Diario permanente de senales (para validacion en papel)
======================================================================

Guarda cada senal detectada en un CSV que NUNCA se borra, para que con el
tiempo puedas comprobar si el sistema acierta ANTES de arriesgar dinero real
(la validacion en papel de 4-6 meses que siempre nos propusimos).

A diferencia de las notificaciones ntfy (que se borran a los pocos dias), esto
es un historial permanente que puedes abrir en Excel y analizar.

Archivo: historial_senales.csv  (en la raiz del repo; el Action hace commit)
"""
from __future__ import annotations
import os
import csv
from datetime import datetime

CSV_PATH = "historial_senales.csv"

CAMPOS = ["fecha", "hora", "modo", "activo", "tipo_senal", "precio",
          "nivel", "stop", "barrida", "detalle"]


def registrar(filas: list[dict]) -> None:
    """
    Anade filas al historial. Cada fila es un dict con las claves de CAMPOS
    (las que falten se dejan vacias). Crea el archivo con cabecera si no existe.
    """
    if not filas:
        return
    existe = os.path.exists(CSV_PATH)
    ahora = datetime.now()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
        if not existe:
            w.writeheader()
        for fila in filas:
            base = {c: "" for c in CAMPOS}
            base["fecha"] = ahora.strftime("%Y-%m-%d")
            base["hora"] = ahora.strftime("%H:%M")
            base.update(fila)
            w.writerow(base)


def registrar_senal(modo, activo, tipo_senal, precio, nivel="", stop="",
                    barrida="", detalle="") -> None:
    """Atajo para registrar una sola senal."""
    registrar([{
        "modo": modo, "activo": activo, "tipo_senal": tipo_senal,
        "precio": precio, "nivel": nivel, "stop": stop,
        "barrida": "si" if barrida else "", "detalle": detalle,
    }])
