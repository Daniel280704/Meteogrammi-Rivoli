#!/usr/bin/env python3
import os
import requests
import sys
import json
from datetime import datetime, timedelta

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
        return datetime.utcnow() + timedelta(hours=2)

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
                        
                        # Salviamo la data dell'innaffiatura
                        with open("ultima_innaffiatura.txt", "w") as f:
                            f.write(get_rome_time().strftime("%Y-%m-%d"))
            
            with open("tg_offset_orto.txt", "w") as f:
                f.write(str(offset))
    except Exception as e:
        print(f"Errore lettura Telegram API: {e}")

def valuta_stress(bilancio):
    """
    Calcola lo stress in base alla sommatoria dell'evaporazione netta (deficit).
    Meno di 5: Nullo, 5-15: Intermedio, 15-20: Alto, >20: Estremo.
    """
    deficit = -bilancio  # Trasforma il bilancio negativo in deficit positivo
    
    if deficit < 5.0:
        return "🟢 SCARSO O NULLO"
    elif deficit <= 15.0:
        return "🟡 INTERMEDIO"
    elif deficit <= 20.0:
        return "🔴 ALTO"
    else:
        return "🟣 ESTREMO"

def calcola_dati_orto():
    # Chiediamo ben 10 giorni di storico per avere una simulazione accurata del suolo
    api_params_det = {
        "latitude": LAT_RIVOLI, "longitude": LON_RIVOLI,
        "hourly": "precipitation,et0_fao_evapotranspiration",
        "models": "icon_seamless",
        "past_days": 10, "forecast_days": 3, 
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
    
    oggi_str = now_rome.strftime("%Y-%m-%d")
    ieri_str = (now_rome - timedelta(days=1)).strftime("%Y-%m-%d")
    domani_str = (now_rome + timedelta(days=1)).strftime("%Y-%m-%d")
    dopo_str = (now_rome + timedelta(days=2)).strftime("%Y-%m-%d")

    # Controlliamo in quale data è stato premuto il tasto Telegram
    data_reset_manuale = None
    if os.path.exists("ultima_innaffiatura.txt"):
        with open("ultima_innaffiatura.txt", "r") as f:
            data_reset_manuale = f.read().strip()

    def get_idx(time_str):
        try:
            return times.index(time_str)
        except ValueError:
            return None

    p_det = dati_det["precipitation"]
    e_det = dati_det["et0_fao_evapotranspiration"]

    # --- SIMULATORE STORICO IN MEMORIA ---
    # Partiamo da 10 giorni fa e ricostruiamo la storia dell'orto giorno per giorno
    bilancio = 0.0
    
    for i in range(10, 0, -1):
        data_storica = (now_rome - timedelta(days=i)).strftime("%Y-%m-%d")
        idx_s = get_idx(f"{data_storica}T00:00")
        idx_e = get_idx(f"{data_storica}T23:00")
        
        if idx_s is not None and idx_e is not None:
            p_giorno = sum(p for p in p_det[idx_s:idx_e+1] if p is not None)
            e_giorno = sum(e for e in e_det[idx_s:idx_e+1] if e is not None)
            
            bilancio += (p_giorno - e_giorno)
            
            # Se ha piovuto in modo utile (>3.5mm) o hai premuto il tasto, il terreno si satura (azzera deficit)
            if p_giorno >= 3.5 or data_storica == data_reset_manuale:
                bilancio = 0.0
            
            # Il terreno non può trattenere acqua infinita (se il bilancio va in positivo, l'eccesso drena)
            if bilancio > 0.0:
                bilancio = 0.0

            # Salviamo specificatamente i dati di IERI per il messaggio
            if data_storica == ieri_str:
                p_ieri = p_giorno
                e_ieri = e_giorno
                bil_ieri = bilancio

    # --- OGGI (Prime 19 ore: 00:00 -> 18:00 inclusive) ---
    idx_oggi_s = get_idx(f"{oggi_str}T00:00")
    idx_oggi_e = get_idx(f"{oggi_str}T18:00")
    
    p_oggi = sum(p for p in p_det[idx_oggi_s:idx_oggi_e+1] if p is not None)
    e_oggi = sum(e for e in e_det[idx_oggi_s:idx_oggi_e+1] if e is not None)
    
    bilancio += (p_oggi - e_oggi)
    if p_oggi >= 3.5 or oggi_str == data_reset_manuale:
        bilancio = 0.0
    if bilancio > 0.0:
        bilancio = 0.0
    bil_oggi = bilancio

    # --- PREVISIONI (Ensemble) ---
    membri_eps = [k for k in dati_eps.keys() if "precipitation_member" in k]
    
    def calcola_eps_giorno(start, end):
        p_media = 0.0
        if membri_eps and start and end:
            for i in range(start, end + 1):
                vals = [dati_eps[m][i] for m in membri_eps if dati_eps[m][i] is not None]
                if vals:
                    p_media += sum(vals) / len(vals)
        elif start and end:
            p_media = sum(p for p in p_det[start:end+1] if p is not None)
        return p_media

    # Domani
    idx_domani_s = get_idx(f"{domani_str}T00:00")
    idx_domani_e = get_idx(f"{domani_str}T23:00")
    p_domani = calcola_eps_giorno(idx_domani_s, idx_domani_e)
    e_domani = sum(e for e in e_det[idx_domani_s:idx_domani_e+1] if e is not None)
    
    bil_domani = bil_oggi + p_domani - e_domani
    if p_domani >= 3.5: bil_domani = 0.0
    if bil_domani > 0.0: bil_domani = 0.0

    # Dopodomani
    idx_dopo_s = get_idx(f"{dopo_str}T00:00")
    idx_dopo_e = get_idx(f"{dopo_str}T23:00")
    p_dopo = calcola_eps_giorno(idx_dopo_s, idx_dopo_e)
    e_dopo = sum(e for e in e_det[idx_dopo_s:idx_dopo_e+1] if e is not None)
    
    bil_dopo = bil_domani + p_dopo - e_dopo
    if p_dopo >= 3.5: bil_dopo = 0.0
    if bil_dopo > 0.0: bil_dopo = 0.0

    return {
        "ieri_stress": valuta_stress(bil_ieri), "ieri_p": p_ieri, "ieri_e": e_ieri,
        "oggi_stress": valuta_stress(bil_oggi), "oggi_p": p_oggi, "oggi_e": e_oggi,
        "domani_stress": valuta_stress(bil_domani), "domani_p": p_domani, "domani_e": e_domani,
        "dopo_stress": valuta_stress(bil_dopo), "dopo_p": p_dopo, "dopo_e": e_dopo,
        "data_reset": data_reset_manuale, "oggi_str": oggi_str, "ieri_str": ieri_str
    }

def genera_messaggio(d):
    # Segnalazione discreta se il reset manuale ha influito sullo storico
    nota_reset = ""
    if d["data_reset"] in [d["ieri_str"], d["oggi_str"]]:
        nota_reset = "\n*(Storico bilanciato: irrigazione manuale registrata)*\n"
    
    messaggio = f"""**BOLLETTINO SUOLO** 
Rivoli (TO)
{nota_reset}
**STORICO RECENTE:**
Ieri
Stato: {d['ieri_stress']}
- Pioggia caduta: {d['ieri_p']:.1f} mm
- Evaporazione avvenuta: {d['ieri_e']:.1f} mm

Oggi (fino alle 19:00)
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

    # Tastiera interattiva
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

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    # Controlliamo i click avvenuti dal bollettino precedente
    if token:
        controlla_pulsante_telegram(token)

    dati = calcola_dati_orto()
    messaggio = genera_messaggio(dati)
    print(messaggio)
    invia_telegram(messaggio, token, chat_id)

if __name__ == "__main__":
    main()
