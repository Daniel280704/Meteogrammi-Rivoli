#!/usr/bin/env python3
import os
import requests
import sys
from datetime import datetime, timezone

LAT_RIVOLI = 45.06212957744542
LON_RIVOLI = 7.5336149995703625

def calcola_bilancio_idrico():
    print("Scaricamento dati agrometeorologici (DETERMINISTICO + ENSEMBLE) in corso...")
    
    # 1. DATI DETERMINISTICI (Passato, Evapotraspirazione, Temperature)
    try:
        res_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT_RIVOLI,
            "longitude": LON_RIVOLI,
            "hourly": "precipitation,et0_fao_evapotranspiration,temperature_2m",
            "models": "icon_seamless",
            "past_days": 4,  
            "forecast_days": 3, 
            "timezone": "UTC"
        }, timeout=30)
        res_det.raise_for_status()
        dati_det = res_det.json()["hourly"]
    except Exception as e:
        print(f"❌ Errore nel download dei dati deterministici: {e}")
        sys.exit(1)

    # 2. DATI ENSEMBLE / EPS (Precipitazioni future probabilistiche)
    try:
        res_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT_RIVOLI,
            "longitude": LON_RIVOLI,
            "hourly": "precipitation",
            "models": "icon_seamless",
            "past_days": 4,  # Manteniamo stesso time-frame per allineare perfettamente gli indici orari
            "forecast_days": 3, 
            "timezone": "UTC"
        }, timeout=30)
        res_eps.raise_for_status()
        dati_eps = res_eps.json()["hourly"]
    except Exception as e:
        print(f"❌ Errore nel download dei dati ensemble: {e}")
        sys.exit(1)

    now_utc = datetime.now(timezone.utc)
    current_time_str = now_utc.strftime("%Y-%m-%dT%H:00")
    
    times = dati_det["time"]
    try:
        current_idx = times.index(current_time_str)
    except ValueError:
        print("⚠️ Ora attuale non trovata, uso approssimazione.")
        current_idx = 4 * 24 
    
    # Estrazione array deterministici
    pioggia_det = dati_det["precipitation"]
    et0 = dati_det["et0_fao_evapotranspiration"]
    temp = dati_det["temperature_2m"]

    start_72h = max(0, current_idx - 72)
    end_48h = min(len(pioggia_det), current_idx + 48)

    # DATI PASSATI STORICI (Ultime 72h dal deterministico - funge da rianalisi affidabile)
    pioggia_72h = sum(p for p in pioggia_det[start_72h:current_idx] if p is not None)
    et0_72h = sum(e for e in et0[start_72h:current_idx] if e is not None) 
    bilancio_passato = pioggia_72h - et0_72h

    # DATI PREVISTI - PRECIPITAZIONE (Media Ensemble / EPS per le prossime 48h)
    membri_eps = [k for k in dati_eps.keys() if "precipitation_member" in k]
    pioggia_prevista_48h = 0.0
    
    if membri_eps:
        # Calcoliamo la pioggia media dell'ensemble per ogni singola ora
        for i in range(current_idx, end_48h):
            valori_ora = [dati_eps[m][i] for m in membri_eps if i < len(dati_eps[m]) and dati_eps[m][i] is not None]
            if valori_ora:
                media_ora = sum(valori_ora) / len(valori_ora)
                pioggia_prevista_48h += media_ora
    else:
        # Fallback di sicurezza se le ensemble non fossero disponibili
        pioggia_prevista_48h = sum(p for p in pioggia_det[current_idx:end_48h] if p is not None)

    # DATI PREVISTI - EVAPOTRASPIRAZIONE E TEMP (Deterministico)
    et0_prevista_48h = sum(e for e in et0[current_idx:end_48h] if e is not None)
    
    array_temp_future = [t for t in temp[current_idx:end_48h] if t is not None]
    t_max_prevista = max(array_temp_future) if array_temp_future else 0

    # BILANCIO TOTALE STIMATO A FINE PERIODO
    bilancio_totale = bilancio_passato + pioggia_prevista_48h - et0_prevista_48h

    return bilancio_totale, bilancio_passato, pioggia_72h, et0_72h, pioggia_prevista_48h, et0_prevista_48h, t_max_prevista

def genera_messaggio(bilancio_totale, bilancio_passato, pioggia_72h, et0_72h, pioggia_prevista, et0_prevista, t_max_prevista):
    
    if bilancio_totale <= -15:
        stato = "🔴 **ALTO STRESS IDRICO PREVISTO**"
    elif bilancio_totale <= -5:
        stato = "🟡 **STRESS IDRICO INTERMEDIO PREVISTO**"
    else:
        stato = "🟢 **SCARSO O NULLO STRESS IDRICO PREVISTO**"

    differenza = bilancio_totale - bilancio_passato
    if differenza > 0.5:
        tendenza_stress = "📉 **In calo** (miglioramento delle condizioni)"
    elif differenza < -0.5:
        tendenza_stress = "📈 **In aumento** (peggioramento del deficit)"
    else:
        tendenza_stress = "⏸️ **Stabile** (nessuna variazione netta)"

    avviso_calore = ""
    if t_max_prevista >= 32:
        avviso_calore = f"\n\n⚠️ **Allerta Calore:** Previsti picchi fino a {t_max_prevista:.1f}°C nelle prossime 48 ore."

    messaggio = f"""🌱 **BOLLETTINO SUOLO** 🌱
📍 Rivoli (TO)

{stato}

🔙 **STORICO RECENTE (ultime 72 ore):**
🌧️ Pioggia caduta: {pioggia_72h:.1f} mm
☀️ Evaporazione suolo: {et0_72h:.1f} mm
⚖️ Bilancio effettivo attuale: {bilancio_passato:.1f} mm

🔜 **PROSSIME 48 ORE:**
🌧️ Pioggia prevista: {pioggia_prevista:.1f} mm
☀️ Evaporazione prevista: {et0_prevista:.1f} mm
📈 Bilancio totale stimato: {bilancio_totale:.1f} mm

📊 **TENDENZA STRESS IDRICO:** {tendenza_stress}{avviso_calore}"""

    return messaggio

def invia_telegram(messaggio):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Token o Chat ID mancanti.")
        return

    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": messaggio, "parse_mode": "Markdown"})
        print("✅ Bollettino agrometeorologico inviato!")
    except Exception as e:
        print(f"❌ Errore invio Telegram: {e}")

def main():
    bilancio_totale, bilancio_passato, pioggia_72h, et0_72h, pioggia_prevista, et0_prevista, t_max_prevista = calcola_bilancio_idrico()
    messaggio = genera_messaggio(bilancio_totale, bilancio_passato, pioggia_72h, et0_72h, pioggia_prevista, et0_prevista, t_max_prevista)
    print(messaggio)
    invia_telegram(messaggio)

if __name__ == "__main__":
    main()
