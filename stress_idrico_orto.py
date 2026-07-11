#!/usr/bin/env python3
import os
import requests
import sys
import json
from datetime import datetime, timedelta

# Gestione sicura del fuso orario di Roma (utile per i server UTC di GitHub)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    pass

LAT_RIVOLI = 45.06212957744542
LON_RIVOLI = 7.5336149995703625

def get_rome_time():
    try:
        return datetime.now(ZoneInfo("Europe/Rome"))
    except:
        return datetime.utcnow() + timedelta(hours=2) # Approssimazione per ora estiva

def controlla_pulsante_telegram(token):
    """Verifica se l'utente ha premuto il tasto di innaffiatura manuale."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    offset = 0
    if os.path.exists("tg_offset_orto.txt"):
        with open("tg_offset_orto.txt", "r") as f:
            try:
                offset = int(f.read().strip())
            except ValueError:
                pass

    try:
        res = requests.get(url, params={"offset": offset, "timeout": 5})
        data = res.json()
        
        if data.get("ok"):
            for update in data["result"]:
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    if update["callback_query"]["data"] == "reset_idrico":
                        cb_id = update["callback_query"]["id"]
                        requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", 
                                      data={"callback_query_id": cb_id, "text": "Memoria irrigazione aggiornata!"})
                        
                        with open("ultima_innaffiatura.txt", "w") as f:
                            f.write(datetime.now().isoformat())
            
            with open("tg_offset_orto.txt", "w") as f:
                f.write(str(offset))
    except Exception as e:
        print(f"Errore lettura Telegram API: {e}")

def valuta_stress(bilancio, pioggia_reale):
    """Calcola lo stress idrico forzando lo stato nullo se ha piovuto in modo significativo."""
    if pioggia_reale >= 5.0:
        return "🟢 SCARSO O NULLO"
    elif bilancio <= -15:
        return "🔴 ALTO"
    elif bilancio <= -5:
        return "🟡 INTERMEDIO"
    else:
        return "🟢 SCARSO O NULLO"

def calcola_dati_orto(forza_azzeramento):
    api_params_det = {
        "latitude": LAT_RIVOLI, "longitude": LON_RIVOLI,
        "hourly": "precipitation,et0_fao_evapotranspiration",
        "models": "icon_seamless",
        "past_days": 4, "forecast_days": 3, 
        "timezone": "Europe/Rome"
    }
    
    api_params_eps = dict(api_params_det)
    api_params_eps["hourly"] = "precipitation"
    
    try:
        dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params=api_params_det, timeout=30).json()["hourly"]
        dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params=api_params_eps, timeout=30).json()["hourly"]
    except Exception as e:
        print(f"Errore download dati: {e}")
        sys.exit(1)

    times = dati_det["time"]
    now_rome = get_rome_time()
    
    # Determinazione delle giornate di calendario
    oggi_str = now_rome.strftime("%Y-%m-%d")
    ieri_str = (now_rome - timedelta(days=1)).strftime("%Y-%m-%d")
    domani_str = (now_rome + timedelta(days=1)).strftime("%Y-%m-%d")
    dopo_str = (now_rome + timedelta(days=2)).strftime("%Y-%m-%d")

    def get_idx(time_str):
        try:
            return times.index(time_str)
        except ValueError:
            return None

    # Isolamento degli intervalli orari esatti
    idx_ieri_start = get_idx(f"{ieri_str}T00:00")
    idx_ieri_end = get_idx(f"{ieri_str}T23:00")
    idx_ieri_end = idx_ieri_end + 1 if idx_ieri_end else None

    idx_oggi_start = get_idx(f"{oggi_str}T00:00")
    idx_oggi_end = get_idx(f"{oggi_str}T18:00")
    idx_oggi_end = idx_oggi_end + 1 if idx_oggi_end else None

    idx_domani_start = get_idx(f"{domani_str}T00:00")
    idx_domani_end = get_idx(f"{domani_str}T23:00")
    idx_domani_end = idx_domani_end + 1 if idx_domani_end else None

    idx_dopo_start = get_idx(f"{dopo_str}T00:00")
    idx_dopo_end = get_idx(f"{dopo_str}T23:00")
    idx_dopo_end = idx_dopo_end + 1 if idx_dopo_end else None

    p_det = dati_det["precipitation"]
    e_det = dati_det["et0_fao_evapotranspiration"]

    # Base cumulativa per dare spessore al bilancio (guarda ai 3 giorni prima di ieri)
    idx_base_start = max(0, idx_ieri_start - 72) if idx_ieri_start else 0
    p_base = sum(p for p in p_det[idx_base_start:idx_ieri_start] if p is not None)
    e_base = sum(e for e in e_det[idx_base_start:idx_ieri_start] if e is not None)
    bil_base = p_base - e_base

    # Ieri (esatte 24h)
    p_ieri = sum(p for p in p_det[idx_ieri_start:idx_ieri_end] if p is not None)
    e_ieri = sum(e for e in e_det[idx_ieri_start:idx_ieri_end] if e is not None)
    bil_ieri = bil_base + p_ieri - e_ieri
    
    # Oggi (esattamente da 00:00 alle 18:00)
    p_oggi = sum(p for p in p_det[idx_oggi_start:idx_oggi_end] if p is not None)
    e_oggi = sum(e for e in e_det[idx_oggi_start:idx_oggi_end] if e is not None)
    bil_oggi = bil_ieri + p_oggi - e_oggi

    # Override in caso di pressione manuale del tasto Telegram
    if forza_azzeramento:
        bil_ieri = 0
        p_ieri = 10.0 
        bil_oggi = 0
        p_oggi = 10.0 

    stress_ieri = valuta_stress(bil_ieri, p_ieri)
    stress_oggi = valuta_stress(bil_oggi, p_oggi)

    # --- CALCOLO PREVISIONI ---
    membri_eps = [k for k in dati_eps.keys() if "precipitation_member" in k]
    
    def calcola_eps_giorno(start, end):
        p_media = 0.0
        if membri_eps and start and end:
            for i in range(start, end):
                vals = [dati_eps[m][i] for m in membri_eps if dati_eps[m][i] is not None]
                if vals:
                    p_media += sum(vals) / len(vals)
        elif start and end:
            p_media = sum(p for p in p_det[start:end] if p is not None)
        return p_media

    # Domani (24h)
    p_domani = calcola_eps_giorno(idx_domani_start, idx_domani_end)
    e_domani = sum(e for e in e_det[idx_domani_start:idx_domani_end] if e is not None) if idx_domani_start and idx_domani_end else 0
    bil_domani = bil_oggi + p_domani - e_domani
    stress_domani = valuta_stress(bil_domani, p_domani)

    # Dopodomani (24h)
    p_dopo = calcola_eps_giorno(idx_dopo_start, idx_dopo_end)
    e_dopo = sum(e for e in e_det[idx_dopo_start:idx_dopo_end] if e is not None) if idx_dopo_start and idx_dopo_end else 0
    bil_dopo = bil_domani + p_dopo - e_dopo
    stress_dopo = valuta_stress(bil_dopo, p_dopo)

    return {
        "ieri_stress": stress_ieri, "ieri_p": p_ieri, "ieri_e": e_ieri,
        "oggi_stress": stress_oggi, "oggi_p": p_oggi, "oggi_e": e_oggi,
        "domani_stress": stress_domani, "domani_p": p_domani, "domani_e": e_domani,
        "dopo_stress": stress_dopo, "dopo_p": p_dopo, "dopo_e": e_dopo,
        "azzerato": forza_azzeramento
    }

def genera_messaggio(d):
    nota_reset = "\n*(Storico forzato: irrigazione manuale rilevata)*\n" if d["azzerato"] else ""
    
    messaggio = f"""**BOLLETTINO SUOLO** 
Rivoli (TO)
{nota_reset}
**STORICO RECENTE:**
Ieri
Stato: {d['ieri_stress']}
- Pioggia caduta: {d['ieri_p']:.1f} mm
- Evaporazione avvenuta: {d['ieri_e']:.1f} mm

Oggi (fino alle 18:00)
Stato: {d['oggi_stress']}
- Pioggia caduta: {d['oggi_p']:.1f} mm
- Evaporazione avvenuta: {d['oggi_e']:.1f} mm

**PREVISIONI:**
Domani
Stato previsto: {d['domani_stress']}
- Pioggia prevista: {d['domani_p']:.1f} mm
- Evaporazione prevista: {d['domani_e']:.1f} mm

Dopodomani
Stato previsto: {d['dopo_stress']}
- Pioggia prevista: {d['dopo_p']:.1f} mm
- Evaporazione prevista: {d['dopo_e']:.1f} mm"""
    
    return messaggio

def invia_telegram(messaggio, token, chat_id):
    if not token or not chat_id:
        print("Token o Chat ID mancanti.")
        return

    # Tastiera interattiva ripulita per l'azzeramento manuale
    tastiera = {
        "inline_keyboard": [
            [{"text": "Ho bagnato l'orto! (Azzera)", "callback_data": "reset_idrico"}]
        ]
    }

    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": messaggio, "parse_mode": "Markdown", "reply_markup": json.dumps(tastiera)})
        print("Bollettino agrometeorologico inviato con successo!")
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def verifica_irrigazione_manuale():
    """Controlla se esiste il segnale di reset manuale avvenuto nelle ultime 48 ore."""
    if os.path.exists("ultima_innaffiatura.txt"):
        with open("ultima_innaffiatura.txt", "r") as f:
            try:
                data_reset = datetime.fromisoformat(f.read().strip())
                if datetime.now() - data_reset < timedelta(hours=48):
                    return True
            except:
                pass
    return False

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token:
        controlla_pulsante_telegram(token)

    forza_azzeramento = verifica_irrigazione_manuale()

    dati = calcola_dati_orto(forza_azzeramento)
    messaggio = genera_messaggio(dati)
    print(messaggio)
    invia_telegram(messaggio, token, chat_id)

if __name__ == "__main__":
    main()
