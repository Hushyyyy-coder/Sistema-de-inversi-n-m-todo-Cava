"""
cava_engine.py — Motor de decision del sistema de inversion (metodo J.L. Cava)
==============================================================================

Traduce a Python el flujo de decision de la seccion 12 del documento (los
mismos 14 pasos del prototipo HTML), como FUNCIONES PURAS: reciben un snapshot
de datos (el que produce cava_data.py) y devuelven un veredicto estructurado.

Es la unica fuente de la verdad de la logica. Tanto el watcher (avisos Telegram)
como la app web (Streamlit) importan de aqui, para que el aviso y la pantalla
nunca se desincronicen.

Jerarquia del documento (manda de arriba a abajo):
    liquidez -> primas de riesgo -> fuerza relativa -> regimen (ADX+media55)
    -> tendencia de fondo -> modulos -> estacional -> cierre de tendencia
    -> R:R / watchlist -> alerta

PRINCIPIOS NO NEGOCIABLES (estan en el codigo como vetos):
    - Si la liquidez se contrae (dolar al alza): NO abrir nuevos largos.
    - Ninguna senal contra la tendencia dominante de fondo se ejecuta.
    - La app AVISA, no opera. Nunca devuelve una orden de compra/venta real.
    - Las proyecciones de precio son opinion, jamas disparador.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional


# ----------------------------------------------------------------------------
# Entrada y salida
# ----------------------------------------------------------------------------
@dataclass
class AssetInput:
    """Lo que el motor necesita de un activo. Lo rellena cava_data.fetch_snapshot()."""
    name: str
    price: float
    ema20: float
    ema55: float
    adx: float
    adx_slope: str          # 'up' | 'down' | 'flat'
    rsi: float
    trend: str = "side"     # tendencia de FONDO (semanal/mensual): 'up'|'side'|'down'
    support: Optional[float] = None   # zona de soporte objetivo (watchlist)
    stop: Optional[float] = None      # stop previsto, para R:R


@dataclass
class Verdict:
    asset: str
    action: str             # 'operable' | 'watchlist' | 'wait' | 'no-open'
    headline: str
    regime: str             # 'strong' | 'range' | 'mixed'
    regime_txt: str
    module: str
    signal: str
    signal_quality: str     # 'alta' | 'media' | 'contra' | 'ninguna'
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    rr: Optional[float] = None
    veto: Optional[str] = None
    notes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ----------------------------------------------------------------------------
# Paso 1-2: contexto de liquidez (compartido por todos los activos)
# ----------------------------------------------------------------------------
def liquidity_verdict(dollar_state: str, cds_state: str = "calm") -> dict:
    """
    dollar_state: 'up' (dolar sube=liquidez escasa) | 'down' (liquidez amplia) | 'flat'
    cds_state:    'calm' (primas planas/cayendo) | 'rising' (en tendencia alcista)
    Regla del documento: el dolar es el proxy 'gratis'; los CDS confirman techo.
    """
    if dollar_state == "up":
        return {"cls": "con",
                "txt": "Contraccion: el dolar sube y rompe sus medias, liquidez escasa. "
                       "Predisposicion a NO abrir nuevos largos / aligerar."}
    if dollar_state == "down":
        if cds_state == "rising":
            return {"cls": "neu",
                    "txt": "Mixto: el dolar acompana, pero las primas de riesgo se disparan. "
                           "Viento a favor con cautela; vigilar cierre de tendencia."}
        return {"cls": "pro",
                "txt": "Expansion: dolar debil y primas planas, liquidez amplia. "
                       "Viento a favor para los activos mas fuertes."}
    return {"cls": "neu",
            "txt": "Neutro: dolar plano. Operar solo senales de alta fiabilidad "
                   "y exigir mas a la relacion riesgo-recompensa."}


# ----------------------------------------------------------------------------
# Paso 4: regimen de mercado (ADX + media 55)
# ----------------------------------------------------------------------------
def market_regime(adx: float, adx_slope: str) -> tuple[str, str]:
    if adx > 30 and adx_slope == "up":
        return "strong", "Tendencia fuerte (ADX > 30, pendiente positiva)"
    if adx < 25 or adx_slope == "down":
        return "range", "Lateral / tendencia escasa (ADX bajo o cayendo)"
    return "mixed", "Transicion (ADX 25-30 o pendiente plana)"


# ----------------------------------------------------------------------------
# Pasos 5-13: el motor completo para un activo
# ----------------------------------------------------------------------------
def evaluate(asset: AssetInput, liq: dict, rr_min: float = 5.0) -> Verdict:
    regime, regime_txt = market_regime(asset.adx, asset.adx_slope)
    dist55 = (asset.price / asset.ema55 - 1) * 100

    module, signal, quality, entry = "—", "", "ninguna", None
    veto = None

    # Veto 1: liquidez en contraccion (el contexto manda sobre el modulo)
    if liq["cls"] == "con":
        veto = ("El filtro de liquidez esta en contraccion (dolar al alza). "
                "No se abren nuevos largos aunque el activo de senal tecnica.")

    if veto is None:
        if regime == "strong" and asset.trend == "up":
            # Modulo 2 (swing): retroceso a la media de 20
            if asset.ema20 * 0.985 <= asset.price <= asset.ema20 * 1.005:
                module = "Modulo 2 — Swing"
                signal = ("Retroceso a la media de 20 en tendencia fuerte (ADX>30). "
                          "Mayor fiabilidad si el MACD rapido gira al alza y el estocastico esta cortado al alza.")
                quality, entry = "alta", asset.ema20
            # Modulo 1 (tendencial): retroceso a la media de 55
            elif abs(dist55) <= 1.5:
                module = "Modulo 1 — Tendencial"
                signal = ("El precio retrocede a la media de 55 en tendencia alcista. "
                          "Setup principal: esperar confirmacion del MACD diario al alza sobre la media.")
                quality, entry = "alta", asset.ema55
            # Modulo 3 a favor: RSI < 40 girandose
            elif asset.rsi < 40:
                module = "Modulo 3 — Osciladores (a favor)"
                signal = ("RSI < 40 con tendencia alcista de fondo: sobreventa a favor de tendencia. "
                          "Compra cuando el RSI se gire y supere de nuevo el 40.")
                quality, entry = "media", asset.price
            else:
                module = "Modulo 1 — Tendencial"
                signal = (f"Tendencia alcista fuerte pero precio extendido ({dist55:+.1f}% sobre la media 55). "
                          "No hay entrada: esperar retroceso a la media.")
                quality, entry = "ninguna", None

        elif regime == "range":
            if asset.trend == "up" and asset.rsi < 40:
                module = "Modulo 3 — Osciladores"
                signal = ("Mercado lateral con RSI en sobreventa (<40) y fondo alcista. "
                          "Posible giro: senal de baja fiabilidad, exigir confirmacion de precio.")
                quality, entry = "media", asset.price
            elif asset.trend == "up" and asset.rsi > 70:
                module = "Modulo 3 — Osciladores"
                signal = "Lateral con RSI en sobrecompra: posible techo de rango. No es entrada larga."
                quality, entry = "ninguna", None
            else:
                module = "Modulo 3 — Osciladores"
                signal = ("Mercado lateral sin extremo de oscilador claro. Sin senal: esperar a los "
                          "bordes del rango o a que el ADX confirme nueva tendencia.")
                quality, entry = "ninguna", None

        elif regime == "strong" and asset.trend == "down":
            module = "Modulo 1/2 — lado bajista"
            signal = ("Tendencia bajista fuerte. Las entradas largas se descartan por ir contra "
                      "la tendencia de fondo (operativa corta fuera de la cartera estructurada).")
            quality, entry = "contra", None

        else:
            module = "Transicion"
            signal = ("El ADX no confirma tendencia fuerte ni rango claro. Mejor esperar; vigilar el "
                      "Modulo 4 (ADX saliendo de lateral, VIX, cierre de gaps) como detector de oportunidad.")
            quality, entry = "ninguna", None

    # Veto 2: senal contra la tendencia de fondo
    if veto is None and asset.trend == "down" and quality in ("alta", "media"):
        veto = ("La senal va contra la tendencia dominante de fondo (bajista). Se descarta: "
                "ninguna senal contra la tendencia de fondo se ejecuta.")

    # Pasos 12-13: R:R y watchlist
    entry_out = stop_out = target_out = rr_out = None
    notes = []
    action = "wait"

    if veto:
        action = "no-open"
    elif entry and asset.stop and entry > asset.stop:
        risk = entry - asset.stop
        target_out = round(entry + risk * rr_min, 2)
        stop_out = asset.stop
        if asset.price > entry * 1.015:
            action = "watchlist"
            ref = asset.support if asset.support else entry
            notes.append(f"Precio ({asset.price}) por encima de la zona de entrada ({entry:.0f}). "
                         f"Aun no hay R:R 1:{rr_min:.0f} limpia. A LISTA DE VIGILANCIA con alerta en {ref:.0f}.")
        else:
            action = "operable"
            entry_out, rr_out = round(entry, 2), rr_min
            notes.append(f"Entrada ~{entry:.0f} · Stop {asset.stop:.0f} (riesgo {risk:.0f}) · "
                         f"Objetivo 1:{rr_min:.0f} ~{target_out:.0f}.")
    elif entry:
        notes.append("Falta un stop valido por debajo de la entrada para calcular la R:R.")

    # Titular
    if action == "no-open":
        headline = "No abrir"
    elif action == "watchlist":
        headline = "A la lista de vigilancia"
    elif action == "operable":
        headline = "Setup operable"
    else:
        headline = "Sin entrada ahora"

    return Verdict(
        asset=asset.name, action=action, headline=headline,
        regime=regime, regime_txt=regime_txt, module=module,
        signal=signal, signal_quality=quality,
        entry=entry_out, stop=stop_out, target=target_out, rr=rr_out,
        veto=veto, notes=notes,
    )


# ----------------------------------------------------------------------------
# Señal de SALIDA (venta) por agotamiento tecnico, fiel a Cava:
# "la tendencia continua hasta prueba evidente de conclusion".
# Dos pruebas de agotamiento: (1) el precio pierde la EMA55 (media que define
# la tendencia de fondo) y (2) el ADX cae (la fuerza de la tendencia se agota).
#   - ninguna  -> mantener (la tendencia aguanta)
#   - una sola -> vigilar (aviso, aun no es prueba evidente)
#   - las dos  -> señal de venta (prueba evidente de conclusion)
# Ademas calcula la plusvalia/minusvalia respecto al precio de compra.
# ----------------------------------------------------------------------------
# MODO ACUMULACION SPOT — para comprar y MANTENER (no trading fino).
# Devuelve DOS señales por separado:
#   A) "buen punto de acumular": tendencia de fondo alcista (precio sobre la
#      media de 200) + NO eufórico (RSI no disparado) + liquidez no en contra.
#   B) "comprar la caida": el precio esta cerca de un soporte fuerte tras corregir.
# Pensado para horizonte largo: prioriza no comprar caro y que el fondo acompañe.
# ----------------------------------------------------------------------------
def near_buy(price: float, support_manual, supports: list, cerca_pct: float = 3.0) -> dict | None:
    """
    Decide si un activo esta CERCA de una compra vigilable, para avisar arriba.
    Distingue dos origenes:
      - "manual": el usuario puso un soporte a mano (campo support del activo).
      - "detectado": un soporte fuerte detectado por el sistema esta cerca.
    Devuelve dict con tipo/nivel/dist, o None si no esta cerca.
    Prioriza el soporte manual si existe (es decision explicita del usuario).
    """
    # Caso 1: soporte puesto a mano
    if support_manual:
        dist = (price / support_manual - 1) * 100
        if 0 <= dist <= cerca_pct:        # el precio esta justo encima del soporte manual
            return {"origen": "manual", "nivel": round(support_manual, 2),
                    "dist_pct": round(dist, 1)}

    # Caso 2: soporte fuerte detectado cercano
    for s in (supports or []):
        if s["tipo"] in ("minimo repetido", "origen del ultimo tramo", "media 200 sesiones"):
            if s["dist_pct"] <= cerca_pct:
                return {"origen": "detectado", "nivel": s["nivel"],
                        "tipo": s["tipo"], "stop": s["stop"], "dist_pct": s["dist_pct"],
                        "trampa": s.get("trampa", False)}
    return None


def escalones_acumulacion(price: float, supports: list, n: int = 5,
                          reparto: list | None = None) -> list:
    """
    Genera un PLAN DE COMPRA ESCALONADA para acumular spot: n niveles de entrada
    anclados en los soportes detectados, de mas cercano (arriba) a mas lejano
    (abajo). Si no hay suficientes soportes, rellena con caidas porcentuales.
    Reparte el capital de forma CRECIENTE hacia abajo (menos arriba, mas abajo):
    cuanto mas cae, mas se compra, porque mejor precio = mas conviccion.

    Devuelve: [{"nivel":..., "caida_pct":..., "capital_pct":..., "origen":...}, ...]
    El usuario decide el capital total; la app solo sugiere el reparto.
    """
    if reparto is None:
        # reparto creciente por defecto (suma 100): 10/15/20/25/30
        reparto = [10, 15, 20, 25, 30][:n]
        # si n != 5, normalizar a 100
        if len(reparto) < n:
            reparto = reparto + [reparto[-1]] * (n - len(reparto))
        total = sum(reparto)
        reparto = [round(r * 100 / total) for r in reparto]

    # Niveles base: soportes por debajo del precio, de mas alto a mas bajo
    niveles = []
    for s in (supports or []):
        if s["nivel"] < price:
            niveles.append({"nivel": s["nivel"], "origen": s["tipo"]})
    niveles = sorted(niveles, key=lambda x: -x["nivel"])[:n]

    # Si faltan escalones, rellenar con caidas desde el ultimo nivel (o desde precio)
    if len(niveles) < n:
        base = niveles[-1]["nivel"] if niveles else price
        faltan = n - len(niveles)
        # caidas adicionales del 8% encadenado
        for i in range(faltan):
            base = round(base * 0.92, 2)
            niveles.append({"nivel": base, "origen": "caida estimada"})

    # Montar el plan con caida % desde precio y reparto de capital
    plan = []
    for i, nv in enumerate(niveles[:n]):
        cap = reparto[i] if i < len(reparto) else reparto[-1]
        plan.append({
            "escalon": i + 1,
            "nivel": nv["nivel"],
            "caida_pct": round((1 - nv["nivel"] / price) * 100, 1),
            "capital_pct": cap,
            "origen": nv["origen"],
        })
    return plan


def evaluate_accumulation(price: float, sma200, rsi: float, supports: list,
                          liq: dict, cerca_pct: float = 3.0) -> dict:
    # --- Señal A: buen punto de acumular ---
    # NOTA IMPORTANTE: el modo acumulacion spot (comprar para mantener anos) NO
    # hereda el veto de liquidez del modo trading. Para quien acumula a largo
    # plazo, un dolar fuerte que tira los precios abajo es una OPORTUNIDAD de
    # comprar barato, no un freno. Por eso la liquidez aqui es solo contexto.
    sobre_200 = (sma200 is not None and price > sma200)   # tendencia de fondo alcista
    no_euforico = rsi < 70                                 # no comprar en euforia
    dolar_fuerte = liq.get("cls") == "con"

    if sobre_200 and no_euforico:
        a_estado, a_cls = "acumular", "ok"
        extra = (" Ademas el dolar esta fuerte y el mercado corrige: para acumular a "
                 "largo plazo, suele ser buen momento para comprar barato.") if dolar_fuerte else ""
        a_txt = ("Buen punto para acumular y mantener: tendencia de fondo alcista "
                 "(sobre la media de 200) y sin euforia." + extra)
    elif sobre_200 and not no_euforico:
        a_estado, a_cls = "esperar", "warn"
        a_txt = ("Tendencia de fondo alcista, pero el activo esta caliente (RSI alto). "
                 "Mejor esperar a que se enfrie antes de acumular.")
    else:  # not sobre_200
        a_estado, a_cls = "no", "off"
        a_txt = ("Por debajo de su media de 200: la tendencia de fondo no acompaña. "
                 "Para comprar y mantener, mejor esperar a que la recupere.")

    # --- Señal B: comprar la caida (cerca de soporte fuerte) ---
    soporte_cerca = None
    for s in (supports or []):
        # soporte "fuerte" = mínimo repetido, origen de tramo o media 200
        if s["tipo"] in ("minimo repetido", "origen del ultimo tramo", "media 200 sesiones"):
            if s["dist_pct"] <= cerca_pct:   # el precio ya esta cerca (<=3% por defecto)
                soporte_cerca = s
                break

    if soporte_cerca:
        b_estado, b_cls = "cerca de soporte", "ok"
        fiable = (" Ademas, ya hubo una barrida previa sobre este nivel (el precio lo "
                  "perforo y lo recupero): señal MAS FIABLE segun Cava ('sin trampa no "
                  "se compra').") if soporte_cerca.get("trampa") else (
                  " Aun no se ha visto una barrida previa sobre este nivel; vigila por si "
                  "la limpieza esta por llegar.")
        b_txt = (f"El precio esta cerca de un soporte fuerte ({soporte_cerca['nivel']}, "
                 f"{soporte_cerca['tipo']}). Zona donde vigilar una compra de la caida, "
                 f"con stop bajo {soporte_cerca['stop']}.{fiable}")
    else:
        b_estado, b_cls = "lejos", "off"
        b_txt = "El precio no esta cerca de ningun soporte fuerte ahora mismo."

    return {
        "acumular_estado": a_estado, "acumular_cls": a_cls, "acumular_txt": a_txt,
        "caida_estado": b_estado, "caida_cls": b_cls, "caida_txt": b_txt,
        "soporte_cerca": soporte_cerca,
    }


# ----------------------------------------------------------------------------
def evaluate_exit(price: float, ema55: float, adx: float, adx_slope: str,
                  buy_price: float | None = None) -> dict:
    pierde_ema = price < ema55
    adx_cae = (adx_slope == "down")

    señales = int(pierde_ema) + int(adx_cae)
    if señales == 0:
        estado, cls = "mantener", "ok"
        txt = "La tendencia aguanta: el precio sigue sobre su EMA55 y la fuerza no se agota."
    elif señales == 1:
        estado, cls = "vigilar", "warn"
        motivo = "el precio ha perdido la EMA55" if pierde_ema else "el ADX (fuerza) esta cayendo"
        txt = f"Aviso: {motivo}. Aun no es prueba evidente de conclusion, pero vigila de cerca."
    else:
        estado, cls = "vender", "exit"
        txt = ("Señal de salida: el precio ha perdido la EMA55 y el ADX cae. "
               "Prueba evidente de agotamiento de la tendencia. Valora vender.")

    pnl_pct = None
    if buy_price:
        pnl_pct = round((price / buy_price - 1) * 100, 2)

    return {"estado": estado, "cls": cls, "txt": txt,
            "pierde_ema": pierde_ema, "adx_cae": adx_cae, "pnl_pct": pnl_pct}



    print("=== cava_engine.py — autoprueba con BTC real (8 jun 2026) ===\n")

    btc = AssetInput(
        name="Bitcoin", price=63261.99, ema20=62612.38, ema55=65293.29,
        adx=58.1, adx_slope="down", rsi=50.0, trend="side",
        support=60300, stop=59100,
    )

    escenarios = [
        ("Liquidez a favor (dolar debil)",  liquidity_verdict("down", "calm")),
        ("Liquidez en contra (dolar fuerte)", liquidity_verdict("up", "calm")),
    ]
    for titulo, liq in escenarios:
        v = evaluate(btc, liq)
        print(f"--- {titulo}")
        print(f"    Liquidez : {liq['cls']}")
        print(f"    Regimen  : {v.regime_txt}")
        print(f"    Modulo   : {v.module}")
        print(f"    Accion   : {v.headline.upper()}  (calidad senal: {v.signal_quality})")
        if v.veto:
            print(f"    VETO     : {v.veto}")
        for n in v.notes:
            print(f"    Nota     : {n}")
        print()

    # Mismo BTC pero declarando la tendencia de fondo alcista
    print("--- Mismo BTC, fondo declarado ALCISTA, liquidez a favor")
    btc_up = AssetInput(**{**btc.__dict__, "trend": "up"})
    v = evaluate(btc_up, liquidity_verdict("down", "calm"))
    print(f"    Regimen  : {v.regime_txt}")
    print(f"    Modulo   : {v.module}")
    print(f"    Accion   : {v.headline.upper()}  (calidad: {v.signal_quality})")
    for n in v.notes:
        print(f"    Nota     : {n}")


if __name__ == "__main__":
    _self_test()
