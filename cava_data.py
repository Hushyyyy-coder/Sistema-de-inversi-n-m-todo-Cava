"""
cava_data.py — Capa de datos del sistema de inversión (método J.L. Cava)
========================================================================

Resuelve el cuello de botella del prototipo: conseguir HISTORIA LARGA diaria
(y semanal) real para poder calcular la media exponencial de 55 sesiones, el
ADX(14) y el RSI(14) de forma fiable.

Fuente: Yahoo Finance vía la librería `yfinance` (gratis, sin clave de API).
Cubre los cuatro tipos de activo del documento:

    - Índices:  Nasdaq 100 (^NDX), S&P 500 (^GSPC), EuroStoxx 50 (^STOXX50E)
    - Oro:      futuro del oro (GC=F)  /  ETC físico europeo (4GLD.DE)
    - Bitcoin:  BTC-USD
    - Dólar:    índice dólar DXY (DX-Y.NYB)  -> proxy de liquidez (medias 5/10 mensuales)
    - ETFs:     cualquier símbolo Yahoo (CIBR, IBIT, etc.)

IMPORTANTE sobre dónde corre esto:
    Este módulo necesita acceso a internet (Yahoo Finance). Está pensado para
    ejecutarse en GitHub Actions o en tu máquina, NO en un entorno sin red.
    Por eso incluye una función de autodiagnóstico (`self_check`) para que
    compruebes que la descarga funciona antes de conectarlo al motor.

Dependencias (requirements.txt):
    yfinance
    pandas
    numpy
"""

from __future__ import annotations
import sys
import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None  # se avisa en runtime; permite importar el módulo sin la librería


# --- Mapa de símbolos: nombre legible -> ticker de Yahoo Finance ------------
# (Verificados contra Yahoo Finance, junio 2026)
SYMBOLS = {
    # Indices
    "Nasdaq 100":    "^NDX",
    "S&P 500":       "^GSPC",
    "EuroStoxx 50":  "^STOXX50E",
    "Dolar (DXY)":   "DX-Y.NYB",
    # Metales y materias primas
    "Oro (futuro)":  "GC=F",
    "Oro 4GLD (ETC)":"4GLD.DE",
    "Plata (futuro)":"SI=F",
    "Petroleo WTI":  "CL=F",
    # Cripto
    "Bitcoin":       "BTC-USD",
    "Ethereum":      "ETH-USD",
    # ETFs tematicos
    "Ciberseguridad CIBR": "CIBR",
    "Semiconductores SMH": "SMH",
    "Semiconductores SOXX":"SOXX",
    "Tecnologia XLK":      "XLK",
    "iShares Bitcoin IBIT":"IBIT",
    # 7 Magnificos
    "Nvidia":     "NVDA",
    "Apple":      "AAPL",
    "Microsoft":  "MSFT",
    "Alphabet":   "GOOGL",
    "Amazon":     "AMZN",
    "Meta":       "META",
    "Tesla":      "TSLA",
    # Corea (tema HBM / memoria para IA). El ETF UCITS es el comprable desde Europa;
    # Samsung y SK Hynix son para VIGILAR (cotizan en Corea, dificiles de comprar directo).
    "Corea ETF (UCITS)":  "IKOR.L",     # iShares MSCI Korea UCITS, Londres (en GBp)
    "Samsung (vigilar)":  "005930.KS",  # Bolsa de Corea
    "SK Hynix (vigilar)": "000660.KS",  # Bolsa de Corea
}


# ----------------------------------------------------------------------------
# Indicadores (las reglas exactas del documento)
# ----------------------------------------------------------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    """Media exponencial. period=55 (Fibonacci) para el Modulo 1, 20 para swing."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder. El documento usa el nivel 40 a favor de tendencia."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ADX de Wilder (14). Es el selector de regimen del documento:
      - ADX > 30 con pendiente positiva -> tendencia fuerte (Modulos 1 y 2)
      - ADX bajo o cayendo              -> lateral (Modulo 3)
    Espera columnas High, Low, Close.
    """
    high, low, close = df["High"], df["Low"], df["Close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


# ----------------------------------------------------------------------------
# Descarga + cálculo: la pieza que el prototipo no podía hacer
# ----------------------------------------------------------------------------
def _download(ticker: str, period: str, interval: str = "1d", retries: int = 3):
    """Descarga con reintentos y pausa, para sortear el rate-limit de Yahoo."""
    import time
    last_err = None
    for intento in range(retries):
        try:
            df = yf.download(ticker, period=period, interval=interval,
                             auto_adjust=False, progress=False, threads=False)
            if df is not None and not df.empty:
                # Aplanar columnas multinivel SIEMPRE (causa del error "identically-labeled")
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df.dropna()
        except Exception as e:
            last_err = e
        time.sleep(1.5 * (intento + 1))  # pausa creciente: 1.5s, 3s, 4.5s
    if last_err:
        raise RuntimeError(f"Yahoo no respondio para {ticker} ({last_err})")
    raise RuntimeError(f"Sin datos para {ticker}. Revisa el simbolo.")


def fetch_snapshot(name_or_ticker: str, period: str = "1y") -> dict:
    """
    Descarga historia diaria larga de un activo y devuelve el snapshot que el
    motor de decision necesita: precio, EMA20, EMA55, ADX(+pendiente), RSI.

    A diferencia del feed de Crypto.com (tope 50 velas), aqui pedimos '1y'
    (~252 sesiones), mas que suficiente para una EMA55 diaria limpia.
    Con reintentos por si Yahoo limita las peticiones al vigilar muchos activos.
    """
    if yf is None:
        raise RuntimeError("Falta la libreria yfinance. Instala: pip install yfinance")

    ticker = SYMBOLS.get(name_or_ticker, name_or_ticker)
    df = _download(ticker, period)
    close = df["Close"]

    ema20 = ema(close, 20)
    ema55 = ema(close, 55)
    adx_series = adx(df, 14)
    rsi_series = rsi(close, 14)

    price = float(close.iloc[-1])
    adx_now = float(adx_series.iloc[-1])
    adx_prev = float(adx_series.iloc[-2])

    return {
        "name": name_or_ticker,
        "ticker": ticker,
        "bars": int(len(df)),
        "asof": str(df.index[-1].date()),
        "price": round(price, 2),
        "ema20": round(float(ema20.iloc[-1]), 2),
        "ema55": round(float(ema55.iloc[-1]), 2),
        "adx": round(adx_now, 1),
        "adx_slope": "up" if adx_now >= adx_prev else "down",
        "rsi": round(float(rsi_series.iloc[-1]), 1),
        "dist_ema55_pct": round((price / float(ema55.iloc[-1]) - 1) * 100, 2),
    }


def fetch_dollar_state(period: str = "5y") -> dict:
    """
    Filtro de liquidez del documento: el dolar como proxy 'gratis'.
    Regla de Cava: medias de 5 y 10 MENSUALES del indice dolar.
    Devolvemos la posicion del precio respecto a esas medias y su cruce.
    """
    if yf is None:
        raise RuntimeError("Falta la libreria yfinance. Instala: pip install yfinance")

    df = _download("DX-Y.NYB", period, interval="1mo")
    close = df["Close"]

    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    price = float(close.iloc[-1])
    m5 = float(sma5.iloc[-1])
    m10 = float(sma10.iloc[-1])

    # Direccion: por encima de ambas y subiendo = contraccion de liquidez (bajista bolsa)
    if price > m5 and price > m10 and m5 >= float(sma5.iloc[-2]):
        state = "up"      # dolar fuerte -> liquidez escasa
    elif price < m5 and price < m10:
        state = "down"    # dolar debil -> liquidez amplia
    else:
        state = "flat"

    return {
        "ticker": "DX-Y.NYB",
        "asof": str(df.index[-1].date()),
        "price": round(price, 2),
        "sma5_m": round(m5, 2),
        "sma10_m": round(m10, 2),
        "state": state,
    }


# ----------------------------------------------------------------------------
# Autodiagnostico: ejecutar `python cava_data.py` donde haya internet
# ----------------------------------------------------------------------------
def self_check():
    print("=== cava_data.py — autodiagnostico ===")
    if yf is None:
        print("[X] yfinance no instalado. Ejecuta: pip install yfinance pandas numpy")
        return 1
    ok = 0
    for name in ["Bitcoin", "S&P 500", "Nasdaq 100", "Oro (futuro)"]:
        try:
            s = fetch_snapshot(name)
            print(f"[OK] {name:14s} {s['ticker']:11s} {s['bars']} velas | "
                  f"precio {s['price']} EMA55 {s['ema55']} ADX {s['adx']}({s['adx_slope']}) RSI {s['rsi']}")
            ok += 1
        except Exception as e:
            print(f"[X]  {name:14s} -> {e}")
    try:
        d = fetch_dollar_state()
        print(f"[OK] Dolar DXY   {d['ticker']} | precio {d['price']} "
              f"SMA5m {d['sma5_m']} SMA10m {d['sma10_m']} estado={d['state']}")
        ok += 1
    except Exception as e:
        print(f"[X]  Dolar DXY -> {e}")
    print(f"=== {ok} comprobaciones OK ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(self_check())
