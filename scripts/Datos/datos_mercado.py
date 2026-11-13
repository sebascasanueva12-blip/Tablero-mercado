"""
Motor de datos del tablero.
Baja precios, último trimestre y noticias de cada emisora desde Yahoo Finance
y los guarda en la carpeta data/ como archivos JSON.
"""
import json
import os
from datetime import datetime, timezone

import yfinance as yf

# ===== EDITA AQUÍ TUS EMISORAS =====
# Mexicanas llevan el sufijo .MX
NACIONALES = ["POSADASA.MX", "HCITY.MX", "FINN13.MX", "CIDMEGA.MX",
              "HOTEL.MX", "FIHO12.MX", "RLHA.MX"]
INTERNACIONALES = ["MAR", "HLT", "H", "IHG", "AC.PA", "CHH"]
EXTRAS_BENCHMARK = ["EURUSD=X"]  # solo para el benchmark (tipo de cambio)
# ====================================

CARPETA = "data"


def numero(valor):
    """Convierte a número normal (o None) para que se pueda guardar en JSON."""
    try:
        if valor is None:
            return None
        v = float(valor)
        return None if v != v else round(v, 4)  # v != v detecta NaN
    except (TypeError, ValueError):
        return None


def datos_mercado(ticker):
    t = yf.Ticker(ticker)
    hist = t.history(period="2mo")
    if hist.empty:
        return {"ticker": ticker, "error": "sin datos"}

    ultimo = hist.iloc[-1]
    anterior = hist.iloc[-2] if len(hist) > 1 else ultimo
    precio = numero(ultimo["Close"])
    variacion = numero((ultimo["Close"] / anterior["Close"] - 1) * 100)
    volumen = numero(ultimo["Volume"])
    vol_prom_30 = numero(hist["Volume"].tail(30).mean())
    vol_relativo = numero(volumen / vol_prom_30) if volumen and vol_prom_30 else None

    try:
        cap = numero(t.fast_info.get("marketCap"))
    except Exception:
        cap = None

    return {
        "ticker": ticker,
        "fecha": str(hist.index[-1].date()),
        "precio": precio,
        "variacion_pct": variacion,
        "volumen": volumen,
        "volumen_relativo_30d": vol_relativo,
        "cap_mercado": cap,
        "trimestre": datos_trimestre(t),
    }


def datos_trimestre(t):
    """Cifras del último trimestre reportado (para validar contra reportes oficiales)."""
    try:
        estado = t.quarterly_income_stmt
        if estado is None or estado.empty:
            return None
        col = estado.columns[0]
        fila = lambda nombre: numero(estado.at[nombre, col]) if nombre in estado.index else None
        return {
            "periodo": str(col.date()),
            "ingresos": fila("Total Revenue"),
            "ebitda": fila("EBITDA"),
            "utilidad_neta": fila("Net Income"),
        }
    except Exception:
        return None


def noticias(ticker, maximo=5):
    salida = []
    try:
        for n in (yf.Ticker(ticker).news or [])[:maximo]:
            c = n.get("content", n)  # Yahoo cambió el formato; esto cubre ambos
            url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
            fuente = (c.get("provider") or {}).get("displayName") or c.get("publisher")
            salida.append({
                "titulo": c.get("title"),
                "fuente": fuente,
                "fecha": c.get("pubDate") or c.get("providerPublishTime"),
                "url": url,
            })
    except Exception:
        pass
    return salida


def guardar(nombre, contenido):
    with open(os.path.join(CARPETA, nombre), "w", encoding="utf-8") as f:
        json.dump(contenido, f, ensure_ascii=False, indent=2)


def benchmark(tickers):
    """Archivos con el mismo formato que usa el benchmark de Claude."""
    precios, semanales = [], []
    for tk in tickers:
        print("Benchmark", tk)
        try:
            t = yf.Ticker(tk)
            diario = t.history(period="1y")
            if diario.empty:
                continue
            # Emisoras poco bursátiles: precio = última operación real (volumen > 0)
            operados = diario if tk.endswith("=X") else diario[diario["Volume"] > 0]
            if operados.empty:
                operados = diario
            cierres = diario["Close"]
            precios.append({
                "ticker": tk,
                "precio": numero(operados["Close"].iloc[-1]),
                "min_52s": numero(cierres.min()),
                "max_52s": numero(cierres.max()),
                "mediana_52s": numero(cierres.median()),
                "fecha": str(operados.index[-1].date()),
            })
            semanal = t.history(period="1y", interval="1wk")["Close"].dropna()
            for fecha, cierre in semanal.items():
                semanales.append({"ticker": tk, "semana": str(fecha.date()), "cierre": numero(cierre)})
        except Exception as e:
            print("Error en", tk, e)
    guardar("benchmark_precios.json", precios)
    guardar("benchmark_semanales.json", semanales)


def main():
    os.makedirs(CARPETA, exist_ok=True)
    ahora = datetime.now(timezone.utc).isoformat()

    for nombre, lista in [("nacionales.json", NACIONALES), ("internacionales.json", INTERNACIONALES)]:
        emisoras = []
        for tk in lista:
            print("Descargando", tk)
            try:
                emisoras.append(datos_mercado(tk))
            except Exception as e:
                emisoras.append({"ticker": tk, "error": str(e)})
        # Ordena por capitalización (mayor relevancia primero)
        emisoras.sort(key=lambda e: e.get("cap_mercado") or 0, reverse=True)
        guardar(nombre, {"actualizado": ahora, "emisoras": emisoras})

    guardar("noticias.json", {
        "actualizado": ahora,
        "emisoras": {tk: noticias(tk) for tk in NACIONALES + INTERNACIONALES},
    })
    benchmark(NACIONALES + INTERNACIONALES + EXTRAS_BENCHMARK)
    print("Listo")


if __name__ == "__main__":
    main()
