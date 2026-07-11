#!/usr/bin/env python3
"""
Meteogramma per Rivoli (TO) basato su modelli ICON e AROME.
- Versione 13.3: Integrazione Ibrida Ensemble PEARO per AROME (Météo-France EPS).
- Scarica spaghi per T, Prec e Vento; fallback al deterministico per RH e Dew Point.
- Estensione automatica a 3 giorni di calendario per D2 e AROME (copertura 48h reali).
- Layout a tre livelli (6 pannelli EPS, 5 pannelli DET con Zero Termico, 4 pannelli per AROME).
- Esclusione della richiesta di Zero Termico per l'API di AROME (sia det che eps).
- Sistema Anti-Crash con auto-retry per errore 503.
- Integrazione Bot Telegram per invio automatico dei grafici generati.

Uso:
    python3 meteogramma_rivoli_gemini_13_bot.py --modello arome
"""

import argparse
import math
import sys
import os
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

LAT_RIVOLI = 45.0716
LON_RIVOLI = 7.5157

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

MODELLI = {
    "ch1": {
        "id_api": "meteoswiss_icon_ch1_ensemble",
        "id_api_det": "meteoswiss_icon_ch1",
        "nome": "ICON-CH1-EPS",
        "orizzonte_ore": 33,
        "is_ensemble": True
    },
    "ch2": {
        "id_api": "meteoswiss_icon_ch2_ensemble",
        "id_api_det": "meteoswiss_icon_ch2",
        "nome": "ICON-CH2-EPS",
        "orizzonte_ore": 120,
        "is_ensemble": True
    },
    "d2": {
        "id_api": "icon_d2",
        "id_api_det": "icon_d2",
        "nome": "ICON-D2-EPS",
        "orizzonte_ore": 48,
        "is_ensemble": True
    },
    "arome": {
        "id_api": "meteofrance_ensemble", 
        "id_api_det": "meteofrance_arome_france_hd",
        "nome": "AROME-France EPS (1.5km/2.5km)",
        "orizzonte_ore": 48, 
        "is_ensemble": True
    },
    "icon2i": {
        "id_api": "",
        "id_api_det": "italia_meteo_arpae_icon_2i",
        "nome": "ICON-2I (ItaliaMeteo/ARPAE 2.2km)",
        "orizzonte_ore": 72,
        "is_ensemble": False
    }
}

VARIABILI = [
    "temperature_2m", 
    "precipitation", 
    "wind_speed_10m",
    "wind_gusts_10m",
    "dew_point_2m",
    "relative_humidity_2m",
    "freezing_level_height"
]
SOGLIE_PIOGGIA_1H = [0.2, 1.0, 5.0]


def stima_run_attuale(modello: str):
    now_utc = datetime.now(timezone.utc)
    ora_utc = now_utc.hour + now_utc.minute / 60.0
    
    if modello == "d2":
        run_disponibili = [0, 3, 6, 9, 12, 15, 18, 21]
        delay = 1.5 
    elif modello == "arome":
        # Le Ensemble francesi PEARO girano tipicamente 4 volte al giorno
        run_disponibili = [0, 6, 12, 18]
        delay = 4.0
    elif modello == "icon2i":
        run_disponibili = [0, 12]
        delay = 3.5 
    else:
        run_disponibili = [0, 6, 12, 18]
        delay = 2.5 if modello == "ch2" else 2.0
        
    run_stimato = run_disponibili[-1] 
    for run in sorted(run_disponibili, reverse=True):
        if ora_utc >= (run + delay):
            run_stimato = run
            break
            
    return run_stimato, f"{run_stimato:02d}Z"


def fetch_con_retry(url: str, params: dict, max_retries: int = 3) -> dict:
    for tentativo in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code in [502, 503, 504]:
                print(f"\n⚠️ Il server di Open-Meteo è occupato (Errore {resp.status_code}).", file=sys.stderr)
                print(f"⏳ Attendo 4 secondi e ritento... (Tentativo {tentativo + 1} di {max_retries})", file=sys.stderr)
                time.sleep(4)
            else:
                raise e
        except requests.exceptions.RequestException as e:
            print(f"\n❌ Errore di connessione a internet: {e}", file=sys.stderr)
            time.sleep(2)
            
    raise Exception("Impossibile scaricare i dati: il server è rimasto bloccato. Riprova più tardi.")


def fetch_data(lat: float, lon: float, giorni: int, modello: str) -> dict:
    if not MODELLI[modello]["is_ensemble"]:
        return {"hourly": {"time": []}}
        
    vars_filtrate = list(VARIABILI)
    
    # Selettore specifico per le Ensemble francesi: chiediamo solo i parametri base supportati dall'API
    if modello == "arome":
        variabili_vietate_eps = ["freezing_level_height", "dew_point_2m", "relative_humidity_2m"]
        for v in variabili_vietate_eps:
            if v in vars_filtrate:
                vars_filtrate.remove(v)
    # Per gli altri modelli EPS, togliamo solo lo zero termico se non disponibile
    elif modello == "arome" and "freezing_level_height" in vars_filtrate:
        vars_filtrate.remove("freezing_level_height")
        
    params = {
        "latitude": lat,
        "longitude": lon,
        "models": MODELLI[modello]["id_api"],
        "hourly": ",".join(vars_filtrate),
        "forecast_days": giorni,
        "timezone": "Europe/Rome",
    }
    return fetch_con_retry(ENSEMBLE_URL, params)


def fetch_deterministico(lat: float, lon: float, giorni: int, modello: str) -> dict:
    # Escludiamo lo zero termico per Arome prima di inviare i parametri all'API
    vars_filtrate = list(VARIABILI)
    if modello == "arome" and "freezing_level_height" in vars_filtrate:
        vars_filtrate.remove("freezing_level_height")

    params = {
        "latitude": lat,
        "longitude": lon,
        "models": MODELLI[modello]["id_api_det"],
        "hourly": ",".join(vars_filtrate),
        "forecast_days": giorni,
        "timezone": "Europe/Rome",
    }
    return fetch_con_retry(FORECAST_URL, params)


def raggruppa_membri(hourly: dict) -> dict:
    gruppi = defaultdict(dict)
    for chiave, valori in hourly.items():
        if chiave == "time": continue
        if "_member" in chiave:
            base, membro = chiave.rsplit("_member", 1)
        else:
            base, membro = chiave, "00"
        gruppi[base][membro] = valori
    return gruppi

def sanifica(valori: list) -> list:
    return [math.nan if v is None else v for v in valori]

def calcola_media(membri: dict, n_punti: int) -> list:
    media = []
    for i in range(n_punti):
        vals = [membri[m][i] for m in membri if membri[m][i] is not None]
        media.append(sum(vals) / len(vals) if vals else math.nan)
    return media

def calcola_probabilita_soglia_1h(membri: dict, n_punti: int, soglia: float) -> list:
    probabilita = []
    for i in range(n_punti):
        vals = [membri[m][i] for m in membri if membri[m][i] is not None]
        if not vals:
            probabilita.append(math.nan)
            continue
        n_sopra = sum(1 for v in vals if v >= soglia)
        probabilita.append(100 * n_sopra / len(vals))
    return probabilita


def formatta_assi(ax, y_label_step=None, x_interval=1):
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=x_interval))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
    ax.grid(which="major", axis="x", alpha=0.5, linewidth=0.8)
    ax.grid(which="minor", axis="x", alpha=0.2, linewidth=0.5)
    ax.grid(which="major", axis="y", alpha=0.4, linewidth=0.8)
    if y_label_step is not None:
        ax.yaxis.set_major_locator(mticker.MultipleLocator(y_label_step))
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    ax.grid(which="minor", axis="y", alpha=0.15, linewidth=0.5)


def plot_meteogramma(data: dict, dati_det: dict, out_path: str, modello: str, luogo: str = "Rivoli (TO)"):
    is_ensemble = MODELLI[modello]["is_ensemble"]
    has_zero = (modello != "arome")
    run_utc_int, run_str = stima_run_attuale(modello)
    
    asse_temporale_base = data["hourly"]["time"] if is_ensemble else dati_det["hourly"]["time"]
    
    indici_validi = []
    for i, t_str in enumerate(asse_temporale_base):
        t_loc = datetime.fromisoformat(t_str)
        if t_loc >= datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=3):
            indici_validi.append(i)

    inizio = indici_validi[0] if indici_validi else 0
    
    hourly_det = dati_det["hourly"]
    tempi_det = [datetime.fromisoformat(t) for t in hourly_det["time"]][inizio:]
    for k in hourly_det.keys():
        if k != "time":
            hourly_det[k] = hourly_det[k][inizio:]
            
    if is_ensemble:
        hourly = data["hourly"]
        tempi = [datetime.fromisoformat(t) for t in hourly["time"]][inizio:]
        n_punti = len(tempi)
        
        gruppi_completi = raggruppa_membri(hourly)
        gruppi = defaultdict(dict)
        for var, membri in gruppi_completi.items():
            for membro, valori in membri.items():
                gruppi[var][membro] = valori[inizio:]
    else:
        tempi = tempi_det
        n_punti = len(tempi)
        gruppi = defaultdict(dict)
        
    nome_modello = MODELLI[modello]["nome"]
    orizzonte_ore = MODELLI[modello]["orizzonte_ore"]
    quota_modello = dati_det.get("elevation", "N/D")
    
    x_interval = 1 if orizzonte_ore <= 48 else 3

    etichette = {
        "temperature_2m": "Temperatura (°C)",
        "precipitation": "Precipitazione (mm/h)",
        "wind_speed_10m": "Vento/Raffiche (km/h)",
        "relative_humidity_2m": "Umidità Relativa (%)",
        "freezing_level_height": "Zero Termico (m)"
    }
    
    passo_y = {
        "temperature_2m": 2,
        "precipitation": None,
        "wind_speed_10m": 10,
        "relative_humidity_2m": 20,
        "freezing_level_height": 100
    }

    if is_ensemble:
        fig, axes = plt.subplots(
            6, 1, figsize=(14, 18), sharex=True,
            gridspec_kw={"height_ratios": [2.5, 2, 1.3, 1.5, 1.8, 1.8]},
        )
        ax_temp, ax_prec, ax_prob, ax_wind, ax_rh, ax_zero = axes
        sottotitolo = "membri perturbati (grigio) + media ensemble (colore continuo) + run deterministico (nero tratteggiato)"
    elif has_zero:
        fig, axes = plt.subplots(
            5, 1, figsize=(14, 15), sharex=True,
            gridspec_kw={"height_ratios": [2.5, 2, 1.5, 1.8, 1.8]},
        )
        ax_temp, ax_prec, ax_wind, ax_rh, ax_zero = axes
        sottotitolo = "Corsa singola deterministica ad altissima risoluzione geografica"
    else:
        fig, axes = plt.subplots(
            4, 1, figsize=(14, 13), sharex=True,
            gridspec_kw={"height_ratios": [2.5, 2, 1.5, 1.8]},
        )
        ax_temp, ax_prec, ax_wind, ax_rh = axes
        sottotitolo = "Corsa singola deterministica ad altissima risoluzione geografica"
        
    fig.suptitle(
        f"{nome_modello} — {luogo} (Quota griglia: {quota_modello} m) | Run: {run_str}\n{sottotitolo}",
        fontsize=13, fontweight="bold",
    )

    if is_ensemble:
        membri = gruppi.get("temperature_2m", {})
        for valori in membri.values():
            ax_temp.plot(tempi, sanifica(valori), color="gray", alpha=0.35, linewidth=0.8, zorder=1)
        media_temp = calcola_media(membri, n_punti)
        ax_temp.plot(tempi, media_temp, color="crimson", linewidth=2.2, linestyle="-", zorder=3, label="Media Temp.")
        ax_temp.plot(tempi_det, sanifica(hourly_det["temperature_2m"]), color="black", linewidth=1.6, linestyle="--", zorder=4, label="Temp. det.")
        
        # LOGICA IBRIDA PER IL DEW POINT
        membri_dew = gruppi.get("dew_point_2m", {})
        if membri_dew:
            media_dew = calcola_media(membri_dew, n_punti)
            ax_temp.plot(tempi, media_dew, color="darkcyan", linewidth=1.8, linestyle="-", zorder=5, label="Media Dew Point")
        else:
            # Fallback per AROME: usa il dato deterministico
            ax_temp.plot(tempi_det, sanifica(hourly_det["dew_point_2m"]), color="darkcyan", linewidth=1.8, linestyle="-", zorder=5, label="Dew Point det.")
    else:
        ax_temp.plot(tempi_det, sanifica(hourly_det["temperature_2m"]), color="crimson", linewidth=2.5, zorder=4, label="Temperatura")
        ax_temp.plot(tempi_det, sanifica(hourly_det["dew_point_2m"]), color="darkcyan", linewidth=1.8, linestyle="-", zorder=5, label="Dew Point")
        
    ax_temp.set_ylabel(etichette["temperature_2m"])
    ax_temp.legend(loc="upper right", fontsize=8)
    formatta_assi(ax_temp, passo_y["temperature_2m"], x_interval)

    if is_ensemble:
        membri_prec = gruppi.get("precipitation", {})
        for valori in membri_prec.values():
            ax_prec.plot(tempi, sanifica(valori), color="gray", alpha=0.35, linewidth=0.8, zorder=1)
        media_prec = calcola_media(membri_prec, n_punti)
        ax_prec.plot(tempi, media_prec, color="royalblue", linewidth=2.2, linestyle="-", zorder=3, label="Media ensemble")
        ax_prec.plot(tempi_det, sanifica(hourly_det["precipitation"]), color="black", linewidth=1.6, linestyle="--", zorder=4, label="Run deterministico")
    else:
        vals_prec_det = sanifica(hourly_det["precipitation"])
        ax_prec.plot(tempi_det, vals_prec_det, color="royalblue", linewidth=2.5, zorder=4, label="Precipitazione")
        ax_prec.fill_between(tempi_det, 0, vals_prec_det, color="royalblue", alpha=0.2)
        
    ax_prec.set_ylabel(etichette["precipitation"])
    ax_prec.legend(loc="upper right", fontsize=8)
    formatta_assi(ax_prec, passo_y["precipitation"], x_interval)
    ax_prec.set_ylim(bottom=0)

    if is_ensemble:
        colori_soglia = {0.2: "#a6d8ff", 1.0: "#4a90d9", 5.0: "#0d2c6b"}
        for soglia in SOGLIE_PIOGGIA_1H:
            prob = calcola_probabilita_soglia_1h(membri_prec, n_punti, soglia)
            ax_prob.step(tempi, prob, where="post", color=colori_soglia.get(soglia, "black"), linewidth=1.8, label=f"P(precip >= {soglia:g} mm/h)")
            ax_prob.fill_between(tempi, prob, step="post", alpha=0.15, color=colori_soglia.get(soglia, "black"))
            
        ax_prob.set_ylabel("Probabilità (%)")
        ax_prob.set_ylim(0, 100)
        ax_prob.legend(loc="upper right", fontsize=8)
        formatta_assi(ax_prob, 20, x_interval)

    if is_ensemble:
        membri_raffiche = gruppi.get("wind_gusts_10m", {})
        for valori in membri_raffiche.values():
            ax_wind.plot(tempi, sanifica(valori), color="gray", alpha=0.35, linewidth=0.8, zorder=1)
        media_raffiche = calcola_media(membri_raffiche, n_punti)
        ax_wind.plot(tempi, media_raffiche, color="mediumvioletred", linewidth=2.2, linestyle="-", zorder=3, label="Media Raffiche")
        ax_wind.plot(tempi_det, sanifica(hourly_det["wind_gusts_10m"]), color="black", linewidth=1.6, linestyle="--", zorder=4, label="Raffiche det.")
        
        membri_vento = gruppi.get("wind_speed_10m", {})
        media_vento = calcola_media(membri_vento, n_punti)
        ax_wind.plot(tempi, media_vento, color="seagreen", linewidth=2.2, linestyle="-", zorder=5, label="Media Vento Base")
    else:
        ax_wind.plot(tempi_det, sanifica(hourly_det["wind_gusts_10m"]), color="mediumvioletred", linewidth=2.5, zorder=4, label="Raffiche")
        ax_wind.plot(tempi_det, sanifica(hourly_det["wind_speed_10m"]), color="seagreen", linewidth=2.5, zorder=5, label="Vento Base")
        
    ax_wind.set_ylabel(etichette["wind_speed_10m"])
    ax_wind.legend(loc="upper left", fontsize=8) 
    formatta_assi(ax_wind, passo_y["wind_speed_10m"], x_interval)

    if is_ensemble:
        # LOGICA IBRIDA PER L'UMIDITA' RELATIVA
        membri_rh = gruppi.get("relative_humidity_2m", {})
        if membri_rh:
            for valori in membri_rh.values():
                ax_rh.plot(tempi, sanifica(valori), color="gray", alpha=0.35, linewidth=0.8, zorder=1)
            media_rh = calcola_media(membri_rh, n_punti)
            ax_rh.plot(tempi, media_rh, color="purple", linewidth=2.2, linestyle="-", zorder=3, label="Media ensemble")
            ax_rh.plot(tempi_det, sanifica(hourly_det["relative_humidity_2m"]), color="black", linewidth=1.6, linestyle="--", zorder=4, label="Run deterministico")
        else:
            # Fallback per AROME: usa il dato deterministico
            ax_rh.plot(tempi_det, sanifica(hourly_det["relative_humidity_2m"]), color="purple", linewidth=2.5, zorder=4, label="Umidità Relativa det.")
    else:
        ax_rh.plot(tempi_det, sanifica(hourly_det["relative_humidity_2m"]), color="purple", linewidth=2.5, zorder=4, label="Umidità Relativa")
        
    ax_rh.set_ylabel(etichette["relative_humidity_2m"])
    ax_rh.set_ylim(0, 105) 
    ax_rh.legend(loc="upper right", fontsize=8)
    formatta_assi(ax_rh, passo_y["relative_humidity_2m"], x_interval)

    if has_zero:
        if is_ensemble:
            membri_zero = gruppi.get("freezing_level_height", {})
            for valori in membri_zero.values():
                ax_zero.plot(tempi, sanifica(valori), color="gray", alpha=0.35, linewidth=0.8, zorder=1)
            media_zero = calcola_media(membri_zero, n_punti)
            ax_zero.plot(tempi, media_zero, color="darkorange", linewidth=2.2, linestyle="-", zorder=3, label="Media ensemble")
            ax_zero.plot(tempi_det, sanifica(hourly_det["freezing_level_height"]), color="black", linewidth=1.6, linestyle="--", zorder=4, label="Run deterministico")
        else:
            ax_zero.plot(tempi_det, sanifica(hourly_det["freezing_level_height"]), color="darkorange", linewidth=2.5, zorder=4, label="Zero Termico")
            
        ax_zero.set_ylabel(etichette["freezing_level_height"])
        ax_zero.legend(loc="upper right", fontsize=8)
        formatta_assi(ax_zero, passo_y["freezing_level_height"], x_interval)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Hh - %d/%m"))
    plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=90, ha="center")

    ora_creazione = datetime.now().strftime("%d/%m/%Y alle %H:%M")
    fig.text(
        0.99, 0.005,
        f"Generato il {ora_creazione} | Fonte: Open-Meteo API",
        ha="right", va="bottom", fontsize=9, color="gray", fontstyle="italic"
    )

    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    plt.savefig(out_path, dpi=150)
    print(f"Meteogramma salvato in: {out_path}\n")


def invia_telegram(percorso_file: str, didascalia: str):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Credenziali Telegram mancanti. Salto l'invio.", file=sys.stderr)
        return

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(percorso_file, "rb") as foto:
            requests.post(url, data={"chat_id": chat_id, "caption": didascalia}, files={"photo": foto})
        print(f"✅ Inviato {percorso_file} su Telegram!")
    except Exception as e:
        print(f"❌ Errore invio Telegram: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Meteogrammi ad alta risoluzione a layout dinamico")
    parser.add_argument("--lat", type=float, default=LAT_RIVOLI, help="Latitudine")
    parser.add_argument("--lon", type=float, default=LON_RIVOLI, help="Longitudine")
    parser.add_argument("--modello", type=str, choices=["ch1", "ch2", "d2", "arome", "icon2i"], default="d2",
                         help="Modello (ch1, ch2, d2 per Ensemble, arome, icon2i per Deterministico)")
    parser.add_argument("--giorni", type=int, default=None, help="Giorni di previsione")
    parser.add_argument("--out", type=str, default=None, help="File immagine di output")
    args = parser.parse_args()

    giorni = args.giorni or (2 if args.modello == "ch1" else (3 if args.modello in ["d2", "arome", "icon2i"] else 5))
    out_path = args.out or f"meteogramma_rivoli_{args.modello}.png"

    try:
        dati = fetch_data(args.lat, args.lon, giorni, args.modello)
        dati_det = fetch_deterministico(args.lat, args.lon, giorni, args.modello)
    except Exception as e:
        print(f"❌ Elaborazione interrotta per il modello {args.modello.upper()}: {e}", file=sys.stderr)
        sys.exit(1)

    plot_meteogramma(dati, dati_det, out_path, args.modello)
    
    # --- Nuova esecuzione per invio Telegram ---
    ora_esecuzione = datetime.now().strftime("%d/%m/%Y %H:%M")
    titolo_modello = MODELLI[args.modello]["nome"]
    didascalia = f"📊 Meteogramma {titolo_modello}\n📍 Rivoli (TO) - Aggiornato il {ora_esecuzione}"
    invia_telegram(out_path, didascalia)

if __name__ == "__main__":
    main()
