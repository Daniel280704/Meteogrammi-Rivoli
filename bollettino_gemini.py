#!/usr/bin/env python3
import os
import requests
import sys

LAT = 45.0716
LON = 7.5157

# Dizionario dei modelli: Nome per la lettura -> ID per l'API
MODELLI = {
    "ICON-D2": "icon_d2",
    "AROME": "arome_france",
    "ICON-CH1": "icon_ch1",
    "ICON-CH2": "icon_ch2",
    "ICON-2I": "icon_2i"
}

def interpella_gemini(dati_meteo):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY mancante! Inseriscila nei Secrets di GitHub.")
        sys.exit(1)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = f"""
    Sei un meteorologo esperto e un divulgatore scientifico. Scrivi il bollettino meteo di nowcasting per oggi a Rivoli (Piemonte).
    Il testo deve essere discorsivo, professionale ma accessibile, perfetto per essere letto da una community di decine di migliaia di appassionati. 
    Usa le emoji in modo appropriato.

    Dividi la cronaca in 4 fasce orarie:
    - Mattino (06-12)
    - Pomeriggio (12-18)
    - Sera (18-24)
    - Notte (00-06)

    Ecco i millimetri di pioggia previsti ora per ora dai 5 modelli ad altissima risoluzione.
    Analizza i dati: se tutti i modelli prevedono pioggia in una fascia oraria, dichiara una probabilità altissima (es. 100%).
    Se solo alcuni la vedono (es. temporali termici isolati), parla di "previsione incerta" o "possibilità al X%".
    Menziona i modelli per nome per dare autorevolezza tecnica. Non stampare la tabella dei dati grezzi, scrivi solo il bollettino narrativo.

    DATI GREZZI DEI MODELLI:
    {dati_meteo}
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2} 
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        risultato = resp.json()
        return risultato["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"❌ Errore API Gemini: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print("Dettaglio errore Gemini:", e.response.text)
        sys.exit(1)

def invia_telegram(testo):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": testo, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def main():
    print("📥 Scaricamento modelli meteo individuali (Multi-Threading simulato)...")
    dati_modelli = {}
    orari = []
    
    for nome, id_api in MODELLI.items():
        print(f"   - Interrogo i server per {nome}...")
        params = {
            "latitude": LAT,
            "longitude": LON,
            "hourly": "precipitation",
            "models": id_api,
            "timezone": "Europe/Rome",
            "forecast_days": 1
        }
        try:
            resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
            resp.raise_for_status()
            dati = resp.json()
            
            # Salviamo l'asse dei tempi solo la prima volta
            if not orari:
                orari = dati["hourly"]["time"]
                
            # Trova la chiave corretta della pioggia dinamicamente
            chiavi_hourly = dati["hourly"].keys()
            chiave_pioggia = next((k for k in chiavi_hourly if "precipitation" in k), "precipitation")
            
            dati_modelli[nome] = [p if p is not None else 0.0 for p in dati["hourly"][chiave_pioggia]]
        except Exception as e:
            print(f"   ⚠️ Errore o timeout con {nome}. Verrà impostato a zero per sicurezza. Dettaglio: {e}")
            dati_modelli[nome] = [0.0] * 24
    
    print("📊 Assemblaggio della Tabellona Dati...")
    # Intestazione della tabella
    riassunto_dati = "Ora | " + " | ".join(MODELLI.keys()) + "\n"
    
    # Riempimento della tabella riga per riga
    for i in range(24):
        if i < len(orari):
            ora = orari[i][-5:]
        else:
            ora = f"{i:02d}:00"
            
        riga = f"{ora} | "
        valori = [f"{dati_modelli[m][i]}mm" if i < len(dati_modelli[m]) else "0.0mm" for m in MODELLI.keys()]
        riga += " | ".join(valori)
        riassunto_dati += riga + "\n"
        
    print("🧠 Elaborazione analisi tramite Gemini 1.5 Flash...")
    bollettino_narrativo = interpella_gemini(riassunto_dati)
    
    print("✈️ Invio della cronaca su Telegram...")
    invia_telegram(bollettino_narrativo)
    print("✅ Finito! Il meteorologo virtuale ha concluso il turno.")

if __name__ == "__main__":
    main()
