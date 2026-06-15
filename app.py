"""
app.py — Sistema de inversion (metodo J.L. Cava) · interfaz amable
==================================================================

Version pensada para consultar a diario, tambien desde el movil. En vez de una
tabla tecnica, da:
  1. Un VEREDICTO grande arriba: que toca hacer hoy, en lenguaje claro.
  2. Un SEMAFORO por activo (verde/ambar/rojo), con lo accionable destacado.
  3. Los numeros tecnicos (ADX, EMA, RSI) plegados, por si los quieres ver.

Reutiliza el mismo motor y datos que el watcher (cava_engine, cava_data), asi
la web y los avisos nunca se contradicen. La app INFORMA, no opera.

Ejecutar:  streamlit run app.py
"""

from __future__ import annotations
import streamlit as st

import cava_data as data
import cava_engine as engine


DEFAULT_WATCHLIST = [
    {"name": "S&P 500",      "trend": "up",   "support": None,  "stop": None},
    {"name": "Nasdaq 100",   "trend": "up",   "support": None,  "stop": None},
    {"name": "EuroStoxx 50", "trend": "side", "support": None,  "stop": None},
    {"name": "Oro (futuro)", "trend": "up",   "support": None,  "stop": None},
    {"name": "Plata (futuro)","trend": "up",  "support": None,  "stop": None},
    {"name": "Bitcoin",      "trend": "up",   "support": 60300, "stop": 59100},
    {"name": "Ethereum",     "trend": "up",   "support": None,  "stop": None},
    {"name": "Mineras BTC WGMI", "trend": "up", "support": None, "stop": None},
    {"name": "Ciberseguridad CIBR", "trend": "up", "support": None, "stop": None},
    {"name": "Semiconductores SMH", "trend": "up", "support": None, "stop": None},
    {"name": "Tecnologia XLK",      "trend": "up", "support": None, "stop": None},
    {"name": "Nvidia",    "trend": "up", "support": None, "stop": None},
    {"name": "Apple",     "trend": "up", "support": None, "stop": None},
    {"name": "Microsoft", "trend": "up", "support": None, "stop": None},
    {"name": "Alphabet",  "trend": "up", "support": None, "stop": None},
    {"name": "Amazon",    "trend": "up", "support": None, "stop": None},
    {"name": "Meta",      "trend": "up", "support": None, "stop": None},
    {"name": "Tesla",     "trend": "up", "support": None, "stop": None},
    {"name": "Corea ETF (UCITS)",  "trend": "up", "support": None, "stop": None},
    {"name": "Samsung (vigilar)",  "trend": "up", "support": None, "stop": None},
    {"name": "SK Hynix (vigilar)", "trend": "up", "support": None, "stop": None},
]

STYLE = {
    "operable":  ("\U0001F7E2", "#1f8a4c", "OPERABLE",   0),
    "watchlist": ("\U0001F7E1", "#c8881a", "VIGILAR",    1),
    "wait":      ("\u26AA",     "#8a8275", "Esperar",    2),
    "no-open":   ("\U0001F534", "#b23b30", "No abrir",   3),
    "error":     ("\u2753",     "#8a8275", "Sin datos",  4),
}

st.set_page_config(page_title="Sistema Cava", page_icon="\U0001F4C8",
                   layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,800&family=Inter:wght@400;500;600;700&display=swap');
  .stApp { background: #f6f3ec; }
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  h1, h2, h3 { font-family: 'Fraunces', serif; color: #14233b; }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.5rem; max-width: 720px; }
  .hero { border-radius: 14px; padding: 26px 22px; margin: 6px 0 18px;
          color: #fff; box-shadow: 0 8px 24px rgba(0,0,0,0.10); }
  .hero .lab { font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase; opacity: 0.85; }
  .hero .big { font-family: 'Fraunces', serif; font-weight: 800; font-size: 34px;
               line-height: 1.05; margin: 6px 0 8px; }
  .hero .sub { font-size: 15px; line-height: 1.5; opacity: 0.95; }
  .sema { display: flex; align-items: center; gap: 14px; padding: 13px 16px;
          border-radius: 10px; margin-bottom: 8px; background: #fff; border: 1px solid #e4ddcd; }
  .sema.act { border-left: 5px solid; }
  .sema .dot { font-size: 18px; }
  .sema .nm { font-weight: 600; font-size: 15.5px; color: #14233b; flex: 1; }
  .sema .st { font-size: 12px; font-weight: 700; letter-spacing: 0.05em;
              text-transform: uppercase; padding: 3px 10px; border-radius: 20px; }
  .sema .px { font-size: 12px; color: #8a8275; font-family: monospace; min-width: 70px; text-align: right; }
  .sectit { font-size: 13px; letter-spacing: 0.12em; text-transform: uppercase;
            color: #8a8275; margin: 22px 0 8px; font-weight: 600; }
  .tip { font-size: 12.5px; color: #8a8275; font-style: italic; margin-top: 18px;
         border-top: 1px solid #e4ddcd; padding-top: 12px; line-height: 1.6; }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Portero de acceso: pide contrasena antes de mostrar nada.
# La clave NO esta aqui: se lee de los "Secrets" de Streamlit (st.secrets).
# En local, si no hay secret configurado, deja pasar (para que puedas probar).
# ----------------------------------------------------------------------------
def _check_password() -> bool:
    # Si no hay contrasena configurada en Secrets, no bloquear (modo local/abierto).
    clave_correcta = st.secrets.get("app_password", None) if hasattr(st, "secrets") else None
    if not clave_correcta:
        return True

    if st.session_state.get("acceso_ok"):
        return True

    st.markdown("<div class='hero' style='background:linear-gradient(135deg,#54616f,#3a444f)'>"
                "<div class='lab'>Acceso privado</div>"
                "<div class='big'>Sistema Cava</div>"
                "<div class='sub'>Introduce la contrasena para entrar.</div></div>",
                unsafe_allow_html=True)
    intento = st.text_input("Contrasena", type="password", label_visibility="collapsed",
                            placeholder="Contrasena")
    if intento:
        if intento == clave_correcta:
            st.session_state["acceso_ok"] = True
            st.rerun()
        else:
            st.error("Contrasena incorrecta.")
    return False


if not _check_password():
    st.stop()


@st.cache_data(ttl=1800, show_spinner=False)
def get_dollar(): return data.fetch_dollar_state()

@st.cache_data(ttl=1800, show_spinner=False)
def get_snapshot(name): return data.fetch_snapshot(name)


def mostrar_soportes(snap):
    """Pinta los soportes candidatos detectados, con su stop sugerido."""
    sups = snap.get("supports") or []
    if not sups:
        st.caption("No se han detectado soportes claros por debajo del precio actual.")
        return
    st.markdown("**Soportes propuestos** (la app sugiere, tu decides):")
    for s in sups:
        st.markdown(
            f"• **{s['nivel']}** · _{s['tipo']}_ · stop sugerido **{s['stop']}** "
            f"· el precio debe caer {s['dist_pct']}% para llegar")
    st.caption("Para vigilar uno, ponlo como soporte y stop del activo. "
               "Elige el nivel segun tu criterio del grafico, como hace Cava.")

prog = st.progress(0.0, text="Mirando el mercado por ti...")
try:
    dollar = get_dollar()
    liq = engine.liquidity_verdict(dollar["state"], cds_state="calm")
except Exception:
    dollar, liq = None, engine.liquidity_verdict("flat")

results = []
total = len(DEFAULT_WATCHLIST)
for i, item in enumerate(DEFAULT_WATCHLIST):
    prog.progress((i + 1) / total, text=f"Revisando {item['name']} ({i+1}/{total})...")
    try:
        snap = get_snapshot(item["name"])
        a = engine.AssetInput(name=item["name"], price=snap["price"], ema20=snap["ema20"],
                              ema55=snap["ema55"], adx=snap["adx"], adx_slope=snap["adx_slope"],
                              rsi=snap["rsi"], trend=item["trend"],
                              support=item["support"], stop=item["stop"])
        v = engine.evaluate(a, liq)
        results.append({"name": item["name"], "v": v, "snap": snap, "action": v.action})
    except Exception as e:
        results.append({"name": item["name"], "v": None, "snap": None, "action": "error", "err": str(e)})
prog.empty()

operables = [r for r in results if r["action"] == "operable"]
vigilar   = [r for r in results if r["action"] == "watchlist"]

if liq["cls"] == "con":
    hero_color = "linear-gradient(135deg,#b23b30,#7d2922)"
    hero_big = "Hoy toca esperar"
    hero_sub = ("El dolar esta fuerte (liquidez escasa). Segun el metodo, no se abren "
                "nuevos largos aunque algun activo parezca atractivo. Paciencia: no fuerces nada.")
elif operables:
    hero_color = "linear-gradient(135deg,#1f8a4c,#156337)"
    hero_big = f"{len(operables)} oportunidad(es)"
    hero_sub = f"Hay setup operable en: {', '.join(r['name'] for r in operables)}. Revisa su ficha abajo."
elif vigilar:
    hero_color = "linear-gradient(135deg,#c8881a,#8a5413)"
    hero_big = "Vigilar de cerca"
    hero_sub = f"Sin entrada limpia aun, pero atento a: {', '.join(r['name'] for r in vigilar)}."
else:
    hero_color = "linear-gradient(135deg,#54616f,#3a444f)"
    hero_big = "Sin señales hoy"
    hero_sub = "Ningun activo da entrada clara. Dia tranquilo: esperar es tambien una decision."

dollar_txt = (f"Dolar (DXY) {dollar['price']} · medias 5/10 mensuales {dollar['sma5_m']}/{dollar['sma10_m']}"
              if dollar else "Contexto de liquidez no disponible")

st.markdown(
    f"<div class='hero' style='background:{hero_color}'>"
    f"<div class='lab'>Veredicto de hoy</div>"
    f"<div class='big'>{hero_big}</div>"
    f"<div class='sub'>{hero_sub}</div></div>",
    unsafe_allow_html=True)
st.caption(f"\U0001F4A7 {dollar_txt} — {liq['txt']}")

accionables = operables + vigilar
if accionables:
    st.markdown("<div class='sectit'>Lo que pide atencion</div>", unsafe_allow_html=True)
    for r in accionables:
        v, snap = r["v"], r["snap"]
        emoji, color, label, _ = STYLE[r["action"]]
        st.markdown(
            f"<div class='sema act' style='border-left-color:{color}'>"
            f"<span class='dot'>{emoji}</span><span class='nm'>{r['name']}</span>"
            f"<span class='st' style='background:{color}22;color:{color}'>{label}</span>"
            f"<span class='px'>{snap['price']}</span></div>", unsafe_allow_html=True)
        with st.expander(f"Detalle de {r['name']}"):
            st.write(f"**{v.module}** — {v.regime_txt}")
            st.write(v.signal)
            if v.rr:
                st.info(f"Entrada ~{v.entry} · Stop {v.stop} · Objetivo {v.target} · R:R 1:{int(v.rr)}")
            for n in v.notes:
                st.write(f"• {n}")
            st.caption(f"ADX {snap['adx']} ({snap['adx_slope']}) · RSI {snap['rsi']} · "
                       f"EMA55 {snap['ema55']} · {snap['bars']} velas (al {snap['asof']})")
            mostrar_soportes(snap)

resto = [r for r in results if r["action"] not in ("operable", "watchlist")]
resto.sort(key=lambda r: STYLE[r["action"]][3])
st.markdown("<div class='sectit'>El resto de la lista</div>", unsafe_allow_html=True)
for r in resto:
    emoji, color, label, _ = STYLE[r["action"]]
    px = r["snap"]["price"] if r["snap"] else "—"
    st.markdown(
        f"<div class='sema'><span class='dot'>{emoji}</span>"
        f"<span class='nm'>{r['name']}</span>"
        f"<span class='st' style='background:{color}1a;color:{color}'>{label}</span>"
        f"<span class='px'>{px}</span></div>", unsafe_allow_html=True)
    if r["snap"]:
        with st.expander(f"Ver numeros de {r['name']}"):
            v, snap = r["v"], r["snap"]
            st.write(f"**{v.module}** — {v.regime_txt}")
            st.write(v.signal)
            if v.veto:
                st.warning(v.veto)
            st.caption(f"ADX {snap['adx']} ({snap['adx_slope']}) · RSI {snap['rsi']} · "
                       f"precio {snap['price']} · EMA55 {snap['ema55']} · {snap['bars']} velas (al {snap['asof']})")
            mostrar_soportes(snap)

st.markdown(
    "<div class='tip'>Regla maestra: la tendencia continua hasta prueba evidente de conclusion; "
    "los indicadores solo avisan. El sistema informa, no opera ni es asesoramiento. "
    "La tendencia de fondo de cada activo es tu juicio. Validar en papel 4-6 meses antes de arriesgar dinero real.</div>",
    unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# MI CARTERA — señales de VENTA por agotamiento tecnico.
# Las posiciones se leen de los Secrets de Streamlit (privadas, fuera del codigo).
# Formato esperado en Secrets:
#   [cartera]
#   "Bitcoin" = 60000
#   "Nvidia"  = 180
# (nombre del activo tal cual aparece en la watchlist = precio medio de compra)
# ----------------------------------------------------------------------------
EXIT_STYLE = {
    "ok":   ("\U0001F7E2", "#1f8a4c", "Mantener"),
    "warn": ("\U0001F7E1", "#c8881a", "Vigilar"),
    "exit": ("\U0001F534", "#b23b30", "Vender"),
}

cartera = {}
try:
    if hasattr(st, "secrets") and "cartera" in st.secrets:
        cartera = dict(st.secrets["cartera"])
except Exception:
    cartera = {}

if cartera:
    st.markdown("<div class='sectit'>Mi cartera — señales de venta</div>", unsafe_allow_html=True)
    # indexar resultados ya calculados por nombre, para no re-descargar
    by_name = {r["name"]: r for r in results}
    for nombre, precio_compra in cartera.items():
        r = by_name.get(nombre)
        if not r or not r.get("snap"):
            st.markdown(
                f"<div class='sema'><span class='dot'>\u2753</span>"
                f"<span class='nm'>{nombre}</span>"
                f"<span class='st' style='background:#8a82751a;color:#8a8275'>sin datos</span>"
                f"<span class='px'>—</span></div>", unsafe_allow_html=True)
            st.caption(f"'{nombre}' no esta en la watchlist o no cargo datos hoy. "
                       f"Revisa que el nombre coincida exactamente con la lista.")
            continue
        snap = r["snap"]
        try:
            ex = engine.evaluate_exit(snap["price"], snap["ema55"], snap["adx"],
                                      snap["adx_slope"], buy_price=float(precio_compra))
        except Exception as err:
            st.markdown(
                f"<div class='sema'><span class='dot'>\u2753</span>"
                f"<span class='nm'>{nombre}</span>"
                f"<span class='st' style='background:#8a82751a;color:#8a8275'>error</span>"
                f"<span class='px'>—</span></div>", unsafe_allow_html=True)
            st.caption(f"No pude evaluar '{nombre}': revisa que el precio de compra sea un numero "
                       f"(ej. 60000, sin comillas ni simbolos).")
            continue
        emoji, color, label = EXIT_STYLE[ex["cls"]]
        pnl = f"{ex['pnl_pct']:+.1f}%" if ex["pnl_pct"] is not None else ""
        st.markdown(
            f"<div class='sema act' style='border-left-color:{color}'>"
            f"<span class='dot'>{emoji}</span>"
            f"<span class='nm'>{nombre}</span>"
            f"<span class='st' style='background:{color}22;color:{color}'>{label}</span>"
            f"<span class='px'>{pnl}</span></div>", unsafe_allow_html=True)
        with st.expander(f"Detalle de {nombre}"):
            st.write(ex["txt"])
            st.caption(f"Compra {precio_compra} · precio {snap['price']} · "
                       f"EMA55 {snap['ema55']} · ADX {snap['adx']} ({snap['adx_slope']})")
else:
    st.markdown(
        "<div class='tip'>Para ver señales de venta de <b>tu cartera</b>, anade tus posiciones "
        "en los Secrets de Streamlit (seccion [cartera], formato: nombre del activo = precio de compra). "
        "Quedan privadas, fuera del codigo.</div>", unsafe_allow_html=True)


if st.button("\U0001F504 Actualizar datos ahora"):
    st.cache_data.clear()
    st.rerun()
