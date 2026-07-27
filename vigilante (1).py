"""
vigilante.py — El reloj automatico del Sistema Cava (para GitHub Actions)
=========================================================================

Corre 1 vez al dia tras el cierre (en la nube, gratis, sin depender de tu PC).
Hace cuatro cosas:

  1. Descarga los snapshots reales de la watchlist (cava_data).
  2. Los pasa por el motor (cava_engine): soportes, barridas, veredicto.
  3. Detecta MOVIMIENTOS INTERESANTES y manda aviso inmediato al movil (ntfy):
       - activo cerca de soporte fuerte CON barrida (senal de mas calidad)
       - activo que acaba de PERFORAR un soporte (barrida o ruptura)
       - cambio de veredicto del dolar (liquidez pasa a favor / en contra)
  4. Manda un RESUMEN DIARIO completo a hora fija, aunque no haya nada nuevo.

Ademas guarda cada senal en historial_senales.csv (validacion en papel).

PRINCIPIO: el vigilante AVISA, no opera. Nunca compra ni vende.

Variables de entorno (GitHub Secrets):
    NTFY_TOPIC   canal secreto de ntfy (obligatorio para recibir avisos)

Estado entre ejecuciones: estado_vigilante.json (para no repetir el mismo aviso).
"""
from __future__ import annotations
import os
import sys
import json

import cava_data as data
import cava_engine as engine
import notificar
import registro

ESTADO_PATH = "estado_vigilante.json"

# Watchlist: los mismos nombres que en la app (deben existir en SYMBOLS)
WATCHLIST = [
    "S&P 500", "Nasdaq 100", "EuroStoxx 50", "Oro (futuro)", "Plata (futuro)",
    "Bitcoin", "Ethereum", "Mineras BTC WGMI", "Ciberseguridad CIBR",
    "Semiconductores SMH", "Tecnologia XLK", "Nvidia", "Apple", "Microsoft",
    "Alphabet", "Amazon", "Meta", "Tesla", "Corea ETF (UCITS)",
    "Samsung (vigilar)", "SK Hynix (vigilar)",
    "Uranio (sigue URA, compra URNU)", "Espacio (sigue UFO, compra JEDI)",
    "Cloud (sigue WCLD, compra WCLD.L)", "Inmobiliario (sigue VNQ, compra XRES)",
    "Semis global (sigue SOXX, compra SEMI/SEC0)",
    "Monster MNST", "Coca-Cola KO", "Alimentacion (sigue PBJ, compra IUCS)",
    "Biotecnologia XBI",
]


def cargar_estado() -> dict:
    if os.path.exists(ESTADO_PATH):
        try:
            with open(ESTADO_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def guardar_estado(estado: dict) -> None:
    with open(ESTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def analizar():
    """Descarga y evalua todos los activos. Devuelve (snapshots, liquidez)."""
    dollar = data.fetch_dollar_state()
    liq = engine.liquidity_verdict(dollar.get("state", "flat"))
    snaps = []
    for nombre in WATCHLIST:
        try:
            s = data.fetch_snapshot(nombre)
            snaps.append(s)
        except Exception as e:
            print(f"  aviso: {nombre} sin datos ({e})")
    return snaps, liq, dollar


def detectar_movimientos(snaps, liq, estado):
    """
    Devuelve avisos NUEVOS de PRECIO DE ENTRADA: cuando el precio ha LLEGADO
    (no solo se acerca) a un nivel accionable. Tres tipos, distinguidos:
      A) Toca un ESCALON de compra del plan escalonado.
      B) Toca un SOPORTE FUERTE con barrida (✅) confirmada (senal de mas calidad).
      C) Ha PERFORADO un soporte (barrida o ruptura).
    "Llegar" = el precio esta en el nivel o por debajo, dentro de un margen del 1%
    (para no exigir que toque el centimo exacto).
    """
    import cava_engine as engine
    avisos = []
    filas_registro = []
    visto = estado.get("avisado", {})
    nuevo_visto = {}
    MARGEN = 0.01  # 1%: se considera "ha llegado" si el precio esta a <=1% por encima o ya por debajo

    def ha_llegado(precio, nivel):
        # el precio ha alcanzado el nivel si esta en el o por debajo, o a <=1% por encima
        return precio <= nivel * (1 + MARGEN)

    for s in snaps:
        nombre = s["name"]
        precio = s["price"]
        supports = s.get("supports") or []

        # --- A) Escalones de compra tocados ---
        escalones = []
        try:
            escalones = engine.escalones_acumulacion(precio, supports,
                                                     sma200w=s.get("sma200w"))
        except Exception:
            escalones = []
        for esc in escalones:
            nivel = esc["nivel"]
            if ha_llegado(precio, nivel) and nivel > 0:
                clave = f"{nombre}-escalon-{esc['escalon']}-{nivel}"
                nuevo_visto[clave] = True
                if clave not in visto:
                    origen = esc["origen"] if esc["origen"] != "caida estimada" else "nivel estimado"
                    avisos.append((
                        4,
                        f"Precio de entrada: {nombre}",
                        f"{nombre} ha llegado al escalon {esc['escalon']} de compra "
                        f"({nivel}, {origen}). Plan: destinar {esc['capital_pct']}% del "
                        f"capital de este activo. La app sugiere; tu decides.",
                    ))
                    filas_registro.append({
                        "modo": "vigilante", "activo": nombre,
                        "tipo_senal": f"escalon {esc['escalon']} tocado", "precio": precio,
                        "nivel": nivel, "detalle": f"{esc['capital_pct']}% capital · {origen}",
                    })

        # --- B) Soporte fuerte con barrida tocado (senal de mas calidad) ---
        for sup in supports:
            if sup["tipo"] in ("minimo repetido", "origen del ultimo tramo",
                               "media 200 sesiones") and sup.get("trampa"):
                if ha_llegado(precio, sup["nivel"]):
                    clave = f"{nombre}-soporte-barrida-{sup['nivel']}"
                    nuevo_visto[clave] = True
                    if clave not in visto:
                        avisos.append((
                            5,
                            f"Soporte con barrida: {nombre}",
                            f"{nombre} ha llegado a un soporte fuerte con barrida "
                            f"confirmada ✅ ({sup['nivel']}, {sup['tipo']}). Senal de mas "
                            f"calidad segun Cava ('sin trampa no se compra'). Stop bajo "
                            f"{sup['stop']}.",
                        ))
                        filas_registro.append({
                            "modo": "vigilante", "activo": nombre,
                            "tipo_senal": "soporte con barrida tocado", "precio": precio,
                            "nivel": sup["nivel"], "stop": sup["stop"],
                            "barrida": True, "detalle": sup["tipo"],
                        })
                    break

        # --- C) Soporte perforado (barrida o ruptura) ---
        perf = s.get("perforated")
        if perf:
            clave = f"{nombre}-perforado-{perf['nivel']}"
            nuevo_visto[clave] = True
            if clave not in visto:
                avisos.append((
                    4,
                    f"Soporte perforado: {nombre}",
                    f"{nombre} ha perforado el soporte de {perf['nivel']} "
                    f"({perf['tipo']}). Vigila si lo recupera (barrida) o "
                    f"sigue cayendo (ruptura).",
                ))
                filas_registro.append({
                    "modo": "vigilante", "activo": nombre,
                    "tipo_senal": "soporte perforado", "precio": precio,
                    "nivel": perf["nivel"], "detalle": perf["tipo"],
                })

    return avisos, filas_registro, nuevo_visto


def construir_resumen(snaps, liq, dollar):
    """Resumen diario corto y legible."""
    lineas = []
    dxy = dollar.get("price", "?")
    estado_liq = {"con": "CONTRACCION (dolar fuerte, no abrir largos)",
                  "pro": "EXPANSION (liquidez a favor)",
                  "neu": "NEUTRO"}.get(liq["cls"], liq["cls"])
    lineas.append(f"Dolar (DXY) {dxy} - {estado_liq}")

    # contar cuantos cerca de soporte / con barrida
    cerca, con_barrida, perforados = [], [], []
    for s in snaps:
        for sup in (s.get("supports") or []):
            if sup["tipo"] in ("minimo repetido", "origen del ultimo tramo",
                               "media 200 sesiones") and sup["dist_pct"] <= 3.0:
                cerca.append(s["name"])
                if sup.get("trampa"):
                    con_barrida.append(s["name"])
                break
        if s.get("perforated"):
            perforados.append(s["name"])

    if con_barrida:
        lineas.append(f"En soporte CON barrida (mas fiable): {', '.join(con_barrida)}")
    if cerca:
        otros = [a for a in cerca if a not in con_barrida]
        if otros:
            lineas.append(f"Cerca de soporte: {', '.join(otros)}")
    if perforados:
        lineas.append(f"Soporte perforado (vigilar): {', '.join(perforados)}")
    if not cerca and not perforados:
        lineas.append("Ningun activo cerca de soporte hoy. Paciencia.")

    return "\n".join(lineas)


def main():
    modo_test = "--test" in sys.argv
    modo_resumen = "--resumen" in sys.argv  # forzar resumen aunque no toque hora

    if modo_test:
        ok = notificar.enviar_prueba()
        print("Prueba enviada." if ok else "No se pudo enviar (revisa NTFY_TOPIC).")
        return

    print("Analizando la watchlist...")
    snaps, liq, dollar = analizar()
    print(f"  {len(snaps)} activos analizados. Liquidez: {liq['cls']}")

    estado = cargar_estado()

    # --- Movimientos interesantes (aviso inmediato) ---
    avisos, filas, nuevo_visto = detectar_movimientos(snaps, liq, estado)

    # cambio de veredicto del dolar
    liq_anterior = estado.get("liq_cls")
    if liq_anterior and liq_anterior != liq["cls"]:
        avisos.append((
            4, "Cambio de liquidez",
            f"El veredicto del dolar ha cambiado: {liq_anterior} -> {liq['cls']}. "
            f"{liq['txt']}",
        ))

    # enviar avisos inmediatos
    enviados = 0
    for prioridad, titulo, mensaje in avisos:
        if notificar.enviar(titulo, mensaje, prioridad=prioridad,
                            emojis="chart_with_upwards_trend"):
            enviados += 1
    print(f"  {enviados} aviso(s) inmediato(s) enviado(s).")

    # registrar en el historial permanente
    registro.registrar(filas)
    if filas:
        print(f"  {len(filas)} senal(es) guardada(s) en {registro.CSV_PATH}")

    # --- Resumen diario (siempre que corra el job, o si se fuerza) ---
    resumen = construir_resumen(snaps, liq, dollar)
    print("\n--- RESUMEN ---")
    print(resumen)
    notificar.enviar("Resumen diario - Sistema Cava", resumen,
                     prioridad=3, emojis="clipboard")

    # guardar estado para la proxima ejecucion
    estado["avisado"] = nuevo_visto
    estado["liq_cls"] = liq["cls"]
    guardar_estado(estado)
    print("\nEstado guardado. Listo.")


if __name__ == "__main__":
    main()
