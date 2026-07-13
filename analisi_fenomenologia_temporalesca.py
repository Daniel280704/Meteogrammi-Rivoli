#!/usr/bin/env python3
import os
import sys
import math
import requests
from datetime import datetime, timedelta
from groq import Groq

# Coordinate - Rivoli (TO)
LAT = 45.0734521841099
LON = 7.543386286825349

def scomposizione_vettoriale(speed_kmh, direction_deg):
    """Converte velocità e direzione in vettori U e V (m/s)."""
    if speed_kmh is None or direction_deg is None:
        return 0.0, 0.0
    speed_ms = speed_kmh / 3.6
    rad = math.radians(direction_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return u, v

def calcola_magnitudo_direzione(u, v):
    """Riconverte i vettori U e V in velocità (km/h) e direzione (gradi)."""
    speed_ms = math.sqrt(u**2 + v**2)
    speed_kmh = speed_ms * 3.6
    direction_deg = (math.degrees(math.atan2(-u, -v)) + 360) % 360
    return speed_kmh, direction_deg

def magnitudo_shear(u1, v1, u2, v2):
    """Calcola la magnitudo (m/s) della differenza vettoriale."""
    if None in (u1, v1, u2, v2):
        return None
    return math.sqrt((u2 - u1)**2 + (v2 - v1)**2)

def get_finestre_innesco_ensemble():
    """
    Analizza i membri EPS di D2 e CH2 per trovare i giorni in cui
    c'è concordanza di innesco (almeno 1 spago >= 1mm su entrambi i modelli, 
    o almeno 2 spaghi se CH2 è offline) tra le 12:00 e le 06:00 del giorno dopo.
    """
    try:
        params_base = {
            "latitude": LAT, "longitude": LON,
            "hourly": "precipitation",
            "timezone": "Europe/Rome", "forecast_days": 3
        }
        
        # Fetch Ensemble D2
        resp_d2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", 
                               params={**params_base, "models": "icon_d2"}, timeout=30)
        resp_d2.raise_for_status()
        dati_d2 = resp_d2.json()

        # Fetch Ensemble CH2 con fallback
        ch2_disponibile = False
        dati_ch2 = {}
        try:
            resp_ch2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", 
                                    params={**params_base, "models": "icon_ch2"}, timeout=30)
            if resp_ch2.status_code == 200:
                dati_ch2 = resp_ch2.json()
                if 'hourly' in dati_ch2:
                    ch2_disponibile = True
        except:
            pass
        
        orari = dati_d2.get('hourly', {}).get('time', [])
        
        def conta_membri_sopra_soglia(hourly_data, indice_ora, soglia):
            if not hourly_data: return 0
            count = 0
            for key, lst in hourly_data.items():
                if key.startswith("precipitation_member") and indice_ora < len(lst):
                    val = lst[indice_ora]
                    if val is not None and val >= soglia:
                        count += 1
            return count

        finestre_attive = {}
        
        # Raggruppa l'analisi per "giorni di partenza" (dalle 12:00 alle 06:00 del giorno dopo)
        giorni_unici = sorted(list(set([time_str.split("T")[0] for time_str in orari])))
        
        for data_str in giorni_unici:
            dt_start = datetime.strptime(f"{data_str}T12:00", "%Y-%m-%dT%H:%M")
            dt_end = dt_start + timedelta(hours=18) # Fino alle 06:00 del giorno dopo
            
            indici_finestra = []
            innesco_valido = False
            
            for i, time_str in enumerate(orari):
                dt_ora = datetime.fromisoformat(time_str)
                if dt_start <= dt_ora <= dt_end:
                    # Contiamo quanti scenari vedono almeno 1 mm nell'ora specifica
                    membri_d2 = conta_membri_sopra_soglia(dati_d2.get('hourly', {}), i, 1.0)
                    membri_ch2 = conta_membri_sopra_soglia(dati_ch2.get('hourly', {}), i, 1.0) if ch2_disponibile else 0
                    
                    # Contiamo quanti vedono un segnale debole per costruire la finestra oraria da analizzare
                    membri_d2_deboli = conta_membri_sopra_soglia(dati_d2.get('hourly', {}), i, 0.2)
                    membri_ch2_deboli = conta_membri_sopra_soglia(dati_ch2.get('hourly', {}), i, 0.2) if ch2_disponibile else 0

                    if membri_d2_deboli >= 1 or membri_ch2_deboli >= 1:
                        indici_finestra.append(i)
                        
                    # Verifica condizione di innesco forte
                    if ch2_disponibile:
                        # Modificato: servono almeno 3 spaghi D2 e 3 spaghi CH2
                        if membri_d2 >= 3 and membri_ch2 >= 3: 
                            innesco_valido = True
                    else:
                        # Modificato: fallback a 5 spaghi D2 se CH2 è offline
                        if membri_d2 >= 5: 
                            innesco_valido = True

            # Salviamo la finestra solo se la condizione di trigger è scattata in almeno una di queste ore
            if innesco_valido and indici_finestra:
                finestre_attive[data_str] = indici_finestra

        return finestre_attive
    except Exception as e:
        print(f"⚠️ Errore nel download Ensemble: {e}")
        return {}

def fetch_dati_convezione_d2():
    """Scarica il profilo verticale dal modello deterministico ICON-D2."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT, "longitude": LON, "models": "icon_d2",
        "hourly": "temperature_2m,dew_point_2m,cape,lifted_index,freezing_level_height,"
                  "wind_speed_10m,wind_direction_10m,"
                  "temperature_850hPa,temperature_500hPa,"
                  "geopotential_height_850hPa,geopotential_height_500hPa,"
                  "wind_speed_850hPa,wind_direction_850hPa,"
                  "wind_speed_500hPa,wind_direction_500hPa,"
                  "relative_humidity_700hPa",
        "timezone": "Europe/Rome", "forecast_days": 3
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()['hourly']

def formatta_sicuro(valore, template="{:.1f}"):
    return "N/D" if valore is None else template.format(valore)

def stima_grandine_python(cape, dls, lapse_rate, zero_termico):
    """Calcolo matematico della dimensione potenziale della grandine."""
    if None in (cape, dls, lapse_rate, zero_termico):
        return "N/D (Dati insufficienti per il calcolo)"
    if cape < 500: return "Assente o trascurabile."
    if zero_termico > 4200 and cape < 1200 and dls < 12:
        return "Rischio basso (Fusione prevalente in caduta dato lo zero termico alto)."
    if cape >= 1500 and (dls >= 20 or lapse_rate >= 7.0):
        return "GROSSA (> 3-4 cm) - Supportata da forti updraft e shear marcato."
    if cape >= 1000 and dls >= 12:
        return "MEDIA (1.5 - 3 cm) - Possibile in strutture multicellulari."
    if cape >= 500 and dls < 12:
        return "PICCOLA (< 1.5 cm) - Rapido collasso della colonna precipitante."
    return "Assente o di piccole dimensioni."

def interpella_groq(report_tecnico, giorno_str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return "Errore: Manca la chiave API di Groq."
        
    client = Groq(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo che deve comunicare un avviso rapido al pubblico generale. Il tuo compito è stilare un BREVE riassunto discorsivo sui rischi principali in caso di temporali per il giorno {giorno_str} a Rivoli (TO).

    DATI ESTRATTI NELLA FINESTRA PRECIPITATIVA (Media dei parametri):
    {report_tecnico}

    REGOLE RIGOROSE:
    1. CONDIZIONALITÀ ASSOLUTA: Inizia e mantieni sempre il discorso evidenziando l'incertezza dell'innesco (es. "Nella giornata di {giorno_str}, nel caso in cui dovesse verificarsi un temporale...", "Qualora si formassero dei rovesci..."). I temporali non sono una certezza.
    2. LINGUAGGIO PER L'UTENTE MEDIO: Non usare ASSOLUTAMENTE NESSUN termine tecnico. Zero riferimenti a CAPE, DLS, LLS, Lapse Rate, Vettore Traslazione, Base Nubi, ecc.
    3. FOTOGRAFA LE CRITICITÀ PRINCIPALI traducendo i dati in fenomeni pratici:
       - Se il "Vettore Traslazione" è basso (< 20 km/h), evidenzia il rischio di "locali allagamenti" o "possibili accumuli ingenti per precipitazioni stazionarie".
       - Se la "Stima grandine" del modello indica "MEDIA" o "GROSSA", segnala esplicitamente il rischio di "grandine anche di grosse dimensioni".
       - Se il "Deep Layer Shear" è alto (> 20 m/s) o l'umidità a 700hPa è bassa (< 50%), avvisa della possibilità di "forti raffiche di vento lineare (downburst)".
    4. SINTESI ESTREMA: Scrivi un solo paragrafo fluido di massimo due/tre frasi. Esempio di tono: "Nella giornata di mercoledì, nel caso in cui dovessero svilupparsi dei temporali, le criticità maggiori potrebbero derivare da locali allagamenti per le piogge stazionarie e possibili forti raffiche di vento."
    5. NESSUNA raccomandazione comportamentale o di protezione civile, limitati a descrivere puramente l'intensità dei fenomeni attesi.
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.25,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Errore AI Groq: {e}"

def main():
    FILE_LOCK = "lock_temporali.txt"
    oggi_str_lock = datetime.now().strftime("%Y-%m-%d")
    
    # CONTROLLO SEMAFORO: Se ha già inviato un'analisi oggi, si stoppa subito[cite: 3]
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi_str_lock:
                print("✅ Analisi temporali già inviata oggi. Esecuzione terminata per evitare spam.")
                sys.exit(0)

    print("Analisi in corso: ricerca inneschi da scenari Ensemble D2/CH2...")
    finestre_attive = get_finestre_innesco_ensemble()
    
    if not finestre_attive:
        print("Analisi terminata: Nessun segnale precipitativo rilevante fiutato dagli scenari per i prossimi giorni.")
        return

    print("Scaricamento profili termodinamici deterministici ICON-D2...")
    hourly = fetch_dati_convezione_d2()
    
    # Usiamo il tag HTML <b> coerentemente con il prompt pulito di Groq
    messaggio_telegram = "🌩 <b>AVVISO PER POSSIBILI TEMPORALI</b>\n\n"
    inviato_almeno_uno = False

    for data_str, indici_ore in finestre_attive.items():
        # Estraiamo i parametri medi nella finestra in cui è attesa la fenomenologia
        capes, cins, lrs = [], [], []
        u_10, v_10, u_850, v_850, u_500, v_500 = [], [], [], [], [], []
        lcls, rh700s, zts = [], [], []
        
        for idx in indici_ore:
            t2m = hourly['temperature_2m'][idx]
            tdew = hourly['dew_point_2m'][idx]
            t850, t500 = hourly['temperature_850hPa'][idx], hourly['temperature_500hPa'][idx]
            z850, z500 = hourly['geopotential_height_850hPa'][idx], hourly['geopotential_height_500hPa'][idx]
            
            if None not in (t2m, tdew): lcls.append(125 * (t2m - tdew))
            if None not in (t850, t500, z850, z500) and (z500 - z850) != 0:
                lrs.append((t850 - t500) / ((z500 - z850) / 1000.0))
                
            c_cape = hourly['cape'][idx]
            if c_cape is not None: capes.append(c_cape)
            c_cin = hourly.get('cin', [])[idx] if 'cin' in hourly else 0
            if c_cin is not None: cins.append(c_cin)
                
            rh = hourly['relative_humidity_700hPa'][idx]
            if rh is not None: rh700s.append(rh)
            
            zt = hourly['freezing_level_height'][idx]
            if zt is not None: zts.append(zt)

            # Vettori Vento
            u, v = scomposizione_vettoriale(hourly['wind_speed_10m'][idx], hourly['wind_direction_10m'][idx])
            u_10.append(u); v_10.append(v)
            u, v = scomposizione_vettoriale(hourly['wind_speed_850hPa'][idx], hourly['wind_direction_850hPa'][idx])
            u_850.append(u); v_850.append(v)
            u, v = scomposizione_vettoriale(hourly['wind_speed_500hPa'][idx], hourly['wind_direction_500hPa'][idx])
            u_500.append(u); v_500.append(v)

        if not capes or max(capes) < 200:
            print(f"[{data_str}] Saltato: Segnale precipitativo previsto, ma profilo termico stabile (Max CAPE < 200).")
            continue

        # Medie di finestra e picchi
        max_cape = max(capes)
        media_cin = sum(cins)/len(cins) if cins else 0
        media_lr = sum(lrs)/len(lrs) if lrs else None
        media_lcl = sum(lcls)/len(lcls) if lcls else None
        media_rh700 = sum(rh700s)/len(rh700s) if rh700s else None
        media_zt = sum(zts)/len(zts) if zts else None
        
        avg_u10, avg_v10 = sum(u_10)/len(u_10), sum(v_10)/len(v_10)
        avg_u850, avg_v850 = sum(u_850)/len(u_850), sum(v_850)/len(v_850)
        avg_u500, avg_v500 = sum(u_500)/len(u_500), sum(v_500)/len(v_500)
        
        dls = magnitudo_shear(avg_u10, avg_v10, avg_u500, avg_v500)
        lls = magnitudo_shear(avg_u10, avg_v10, avg_u850, avg_v850)
        
        u_cbl = (avg_u850 + avg_u500) / 2
        v_cbl = (avg_v850 + avg_u500) / 2
        traslazione_kmh, traslazione_dir = calcola_magnitudo_direzione(u_cbl, v_cbl)

        stima_g = stima_grandine_python(max_cape, dls, media_lr, media_zt)

        report_dati = f"""
        Finestra analizzata: Da {datetime.fromisoformat(hourly['time'][indici_ore[0]]).strftime('%H:%M')} a {datetime.fromisoformat(hourly['time'][indici_ore[-1]]).strftime('%H:%M')}
        Max CAPE: {formatta_sicuro(max_cape, "{:.0f}")} J/kg
        CIN Medio: {formatta_sicuro(media_cin, "{:.0f}")} J/kg
        LCL (Base Nubi): {formatta_sicuro(media_lcl, "{:.0f}")} m
        Lapse Rate Medio (850-500hPa): {formatta_sicuro(media_lr, "{:.1f}")} °C/km
        Deep Layer Shear (0-6km): {formatta_sicuro(dls, "{:.1f}")} m/s
        Low Level Shear (0-1.5km): {formatta_sicuro(lls, "{:.1f}")} m/s
        Vettore Traslazione (CBL Wind): {formatta_sicuro(traslazione_kmh, "{:.1f}")} km/h con provenienza da {formatta_sicuro(traslazione_dir, "{:.0f}")}°
        Umidità media 700hPa: {formatta_sicuro(media_rh700, "{:.0f}")}%
        Modello matematico grandine: {stima_g}
        """
        
        # Traduzione manuale e sicura della data in formato discorsivo italiano
        dt_giorno = datetime.strptime(data_str, "%Y-%m-%d")
        giorni_it = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
        mesi_it = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
        
        giorno_formattato = f"{giorni_it[dt_giorno.weekday()]} {dt_giorno.day} {mesi_it[dt_giorno.month]}"
        print(f"[{giorno_formattato}] Elaborazione responso diagnostico tramite Groq...")
        responso = interpella_groq(report_dati, giorno_formattato)
        
        messaggio_telegram += f"📅 <b>Target: {giorno_formattato}</b>\n\n{responso}\n\n➖➖➖➖➖➖➖➖➖➖\n\n"
        inviato_almeno_uno = True

    # Invio Telegram condizionato all'effettivo innesco di almeno un giorno valido[cite: 3]
    if inviato_almeno_uno:
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if token and chat_id:
            res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={"chat_id": chat_id, "text": messaggio_telegram, "parse_mode": "HTML"})
            if res.status_code == 200:
                print("Analisi convettiva inviata con successo su Telegram!")
                # SCRITTURA DEL SEMAFORO: Salva lo sblocco avvenuto[cite: 3]
                with open(FILE_LOCK, "w") as f:
                    f.write(oggi_str_lock)
            else:
                print(f"Errore invio Telegram: {res.text}")
        else:
            print(messaggio_telegram)
    else:
        print("Scenari analizzati ma nessun setup ha superato la soglia di criticità termodinamica (Max CAPE < 200).")

if __name__ == "__main__":
    main()
