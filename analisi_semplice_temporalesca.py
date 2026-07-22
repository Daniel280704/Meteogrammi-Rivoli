import os
import sys
import math
import requests
from datetime import datetime

# Coordinate - Rivoli (TO)
LAT = 45.0734521841099
LON = 7.543386286825349

def scomposizione_vettoriale(speed_kmh, direction_deg):
    """Converte velocità e direzione di provenienza in vettori U e V (m/s)."""
    if speed_kmh is None or direction_deg is None:
        return 0.0, 0.0
    speed_ms = speed_kmh / 3.6
    rad = math.radians(direction_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return u, v

def calcola_vettore_traslazione(u, v):
    """Calcola velocità (km/h) e direzione VERSO CUI punta il vettore (gradi)."""
    speed_ms = math.sqrt(u**2 + v**2)
    speed_kmh = speed_ms * 3.6
    direction_deg = (math.degrees(math.atan2(u, v)) + 360) % 360
    return speed_kmh, direction_deg

def classificazione_traslazione(kmh):
    if kmh < 15: return "molto lento, quasi stazionario"
    if kmh < 30: return "lento"
    if kmh < 50: return "rapido"
    return "molto rapido"

def check_probabilita_precipitazione():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT, "longitude": LON,
        "daily": "precipitation_probability_max",
        "models": "dwd_icon_d2,meteoswiss_icon_ch2",
        "timezone": "Europe/Rome",
        "forecast_days": 3
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        times = daily.get("time", [])
        prob_d2 = daily.get("precipitation_probability_max_dwd_icon_d2", [])
        prob_ch2 = daily.get("precipitation_probability_max_meteoswiss_icon_ch2", [])
        giorni_validi = []
        for i in range(min(2, len(times))):
            d2_val = prob_d2[i] if len(prob_d2) > i and prob_d2[i] is not None else 0
            ch2_val = prob_ch2[i] if len(prob_ch2) > i and prob_ch2[i] is not None else 0
            if (d2_val >= 15 or ch2_val >= 15) or (d2_val >= 10 and ch2_val >= 10):
                giorni_validi.append(times[i])
        return giorni_validi
    except: return []

def fetch_dati_termodinamici():
    url = "https://api.open-meteo.com/v1/forecast"
    hourly_params = "precipitation_probability,temperature_2m,dew_point_2m,wind_gusts_10m,lightning_potential,updraft,convective_cloud_base,convective_cloud_top,cape,freezing_level_height,wind_speed_1000hPa,wind_direction_1000hPa,wind_speed_850hPa,wind_direction_850hPa,wind_speed_700hPa,wind_direction_700hPa,wind_speed_500hPa,wind_direction_500hPa"
    params = {"latitude": LAT, "longitude": LON, "models": "dwd_icon_d2,meteoswiss_icon_ch2", "hourly": hourly_params, "timezone": "Europe/Rome", "forecast_days": 3}
    return requests.get(url, params=params, timeout=40).json()['hourly']

def media_sicura(lista):
    valori = [x for x in lista if x is not None]
    return sum(valori) / len(valori) if valori else None

def max_sicuro(lista):
    valori = [x for x in lista if x is not None]
    return max(valori) if valori else None

def stima_grandine(cape, updraft, spessore):
    if cape > 2500 or updraft > 15: return "Livello 5 su 5, con chicchi di grandi dimensioni (> 5 cm)"
    if cape > 1500: return "Livello 4 su 5, con chicchi di dimensioni medie (3 - 5 cm)"
    if cape > 800: return "Livello 3 su 5, con chicchi di piccole dimensioni (1.5 - 3 cm)"
    if cape > 400: return "Livello 2 su 5, con chicchi molto piccoli o grandine fine (< 1.5 cm)"
    return "Livello 0 su 5, assente"

def stima_downburst(gust):
    if gust > 80: return "Livello 5 su 5, molto intenso"
    if gust > 60: return "Livello 4 su 5, intenso"
    if gust > 50: return "Livello 3 su 5, moderato"
    return "Livello 1 su 5, debole"

def interpella_groq_semplice(report, giorno_str, fascia, traslazione, grandine, downburst):
    api_key = os.getenv("GROQ_API_KEY")
    client = Groq(api_key=api_key)
    prompt = f"""
    Sei un meteorologo che parla al pubblico. Il {giorno_str} a Rivoli sono previsti fenomeni.
    DATI: {report}.
    TRASLAZIONE: {traslazione}.
    GRANDINE: {grandine}.
    DOWNBURST: {downburst}.

    REGOLE:
    1. INIZIA ESATTAMENTE COSÌ: "Dagli ultimi aggiornamenti sembrerebbero possibili rovesci o temporali tra {fascia}, potenzialmente accompagnati da pioggia forte e raffiche di vento fino a {report.split('Max Gust: ')[1].split(' ')[0]} km/h."
    2. CONTINUAZIONE: Aggiungi che la grandine è {grandine.split('- ')[1].split('(')[0].lower().strip()} e che il sistema traslerà in modo {traslazione} verso il settore indicato dai dati.
    3. TIPO: Descrivi se sarà un temporale a cella singola, multicellulare o supercella. Non usare "squall line".
    4. CONCLUSIONE OBBLIGATORIA: "Attenzione: considera che si tratta di fenomenologia localizzata e difficilmente prevedibile, non è dunque da escludere che le precipitazioni interessino maggiormente i comuni limitrofi o lascino addirittura completamente all'asciutto la tua zona."
    5. NO HTML, NO JARGON, NO LISTE.
    """
    return client.chat.completions.create(messages=[{"role":"user","content":prompt}], model="llama-3.3-70b-versatile", temperature=0.3).choices[0].message.content

def main():
    FILE_LOCK = "lock_temporali.txt"
    oggi = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi: sys.exit(0)

    giorni = check_probabilita_precipitazione()
    if not giorni: return
    
    hourly = fetch_dati_termodinamici()
    
    for data_str in giorni:
        idx_g = [i for i, t in enumerate(hourly['time']) if t.startswith(data_str)]
        idx_picco = -1
        for i in idx_g:
            if (hourly['precipitation_probability_dwd_icon_d2'][i] >= 15 or hourly['precipitation_probability_meteoswiss_icon_ch2'][i] >= 15):
                idx_picco = i
                break
        
        idx_picco = idx_picco if idx_picco != -1 else [i for i in idx_g if hourly['time'][i].endswith("16:00")][0]
        indici = [idx for idx in range(idx_picco - 3, idx_picco + 1) if 0 <= idx < len(hourly['time'])]
        
        # Dati per Groq
        cape = max_sicuro([hourly['cape_dwd_icon_d2'][i] for i in indici])
        gust = max_sicuro([hourly['wind_gusts_10m_dwd_icon_d2'][i] for i in indici])
        updraft = max_sicuro([hourly['updraft_dwd_icon_d2'][i] for i in indici])
        min_base = min_sicuro([hourly['convective_cloud_base_dwd_icon_d2'][i] for i in indici])
        max_top = max_sicuro([hourly['convective_cloud_top_dwd_icon_d2'][i] for i in indici])
        spessore = (max_top - min_base) if min_base and max_top else 0
        
        # Vettori per traslazione
        u_850, v_850 = scomposizione_vettoriale(hourly['wind_speed_850hPa_dwd_icon_d2'][idx_picco], hourly['wind_direction_850hPa_dwd_icon_d2'][idx_picco])
        u_700, v_700 = scomposizione_vettoriale(hourly['wind_speed_700hPa_dwd_icon_d2'][idx_picco], hourly['wind_direction_700hPa_dwd_icon_d2'][idx_picco])
        u_500, v_500 = scomposizione_vettoriale(hourly['wind_speed_500hPa_dwd_icon_d2'][idx_picco], hourly['wind_direction_500hPa_dwd_icon_d2'][idx_picco])
        trasl_kmh, trasl_dir = calcola_vettore_traslazione((u_850+u_700+u_500)/3, (v_850+v_700+v_500)/3)
        
        trasl_str = f"{classificazione_traslazione(trasl_kmh)} in direzione {trasl_dir:.0f}°"
        grandine_str = stima_grandine(cape, updraft, 15, 3000, spessore)
        downburst_str = stima_downburst(100, 100, 5, gust, 15)
        
        report_dati = f"Max Gust: {gust} km/h, CAPE: {cape}"
        
        fascia = f"{(idx_picco-1)%24} e {(idx_picco+1)%24}"
        testo = interpella_groq_semplice(report_dati, data_str, fascia, trasl_str, grandine_str, downburst_str)
        
        messaggio = f"⛈ <b>Avviso per possibili temporali</b>\n\n📅 {datetime.strptime(data_str, '%Y-%m-%d').strftime('%d/%m/%Y')}\n\n{testo.replace('<', '&lt;').replace('>', '&gt;')}"
        
        requests.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage", data={
            "chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": messaggio, "parse_mode": "HTML"
        })
        with open(FILE_LOCK, "w") as f: f.write(oggi)

if __name__ == "__main__":
    main()
