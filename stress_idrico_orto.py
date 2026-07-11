#!/usr/bin/env python3
import os
import requests
import sys
from datetime import datetime, timezone

LAT_RIVOLI = 45.0716
LON_RIVOLI = 7.5157

def calcola_bilancio_idrico():
    print("Scaricamento dati agrometeorologici orari (ICON-D2) in corso...")
    try:
        res = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT_RIVOLI,
            "longitude": LON_RIVOLI,
            "hourly": "precipitation,et0_fao_evapotranspiration,temperature_2m",
            "models": "icon_d2",
            "past_days": 4,  
            "forecast_days": 3, 
            "timezone": "UTC"
        }, timeout=30)
        res.raise_for_status()
        dati = res.json()["hourly"]
    except Exception as e:
        print(f"❌ Errore nel download dei dati: {e}")
        sys.exit(1)

    now_utc = datetime.now(timezone.utc)
    current_time_str = now_utc.strftime("%Y-%m-%dT%H:00")
    
    times = dati["time"]
    try:
        current_idx = times.index(current_time_str)
    except ValueError:
        print("⚠️ Ora attuale non trovata, uso approssimazione.")
        current_idx = 4 * 24 
    
    pioggia = dati["precipitation"]
    et0 = dati["et0_fao_evapotranspiration"]
    temp = dati["temperature_2m"]

    start_72h = max(0, current_idx - 72)
    start_48h = max(0, current_idx - 48)
    end_36h = min(len(pioggia), current_idx + 36)

    # DATI PASSATI STORICI
    pioggia_72h = sum(pioggia[start_72h:current_idx])
    et0_48h = sum(et0[start_48h:current_idx])
    et0_72h = sum(et0[start_72h:current_idx]) 
    bilancio_passato = pioggia_72h - et0_72h

    # DATI PREVISTI 
    pioggia_prevista_36h = sum(pioggia[current_idx:end_36h])
    et0_prevista_36h = sum(et0[current_idx:end_36h])
    
    array_temp_future = temp[current_idx:end_36h]
    t_max_prevista = max(array_temp_future) if array_temp_future else 0

    # BILANCIO TOTALE
    bilancio_totale = bilancio_passato + pioggia_prevista_36h - et0_prevista_36h

    return bilancio_totale, bilancio_passato, pioggia_72h, et0_48h, pioggia_prevista_36h, t_max_prevista

def genera_messaggio(bilancio_totale, bilancio_passato, pioggia_72h, et0_48h, pioggia_prevista, t_max_prevista):
    
    # Classificazione essenziale dello stress idrico
    if bilancio_totale <= -15:
        stato = "🔴 **ALTO STRESS IDRICO**"
    elif bilancio_totale <= -5:
        stato = "🟡 **STRESS IDRICO INTERMEDIO**"
    else:
        stato = "🟢 **SCARSO O NULLO STRESS IDRICO**"

    avviso_calore = ""
    if t_max_prevista >= 32:
        avviso_calore = f"\n\n⚠️ **Allerta Calore:** Previsti picchi fino a {t_max_prevista:.1f}°C nelle prossime 36 ore."

    messaggio = f"""🌱 **BOLLETTINO SUOLO (ICON-D2)** 🌱
📍 Rivoli (TO)

{stato}

🔙 **STORICO RECENTE:**
🌧️ Pioggia caduta (ultime 72h): {pioggia_72h:.1f} mm
☀️ Evaporazione suolo (ultime 48h): {et0_48h:.1f} mm
⚖️ Bilancio effettivo 3 giorni: {bilancio_passato:.1f} mm

🔜 **PROSSIME 36 ORE:**
🌧️ Pioggia prevista: {pioggia_prevista:.1f} mm
📈 Bilancio Totale Stimato: {bilancio_totale:.1f} mm{avviso_calore}"""

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
    bilancio_totale, bilancio_passato, pioggia_72h, et0_48h, pioggia_prevista, t_max_prevista = calcola_bilancio_idrico()
    messaggio = genera_messaggio(bilancio_totale, bilancio_passato, pioggia_72h, et0_48h, pioggia_prevista, t_max_prevista)
    print(messaggio)
    invia_telegram(messaggio)

if __name__ == "__main__":
    main()
