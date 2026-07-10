    #!/usr/bin/env python3
import os
import requests
import sys
import google.generativeai as genai

LAT = 45.0716
LON = 7.5157

def interpella_gemini(dati_meteo):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY mancante! Inseriscila nei Secrets di GitHub.")
        sys.exit(1)

    # Configurazione della libreria ufficiale Google
    genai.configure(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo esperto e un divulgatore scientifico. Scrivi il bollettino meteo di nowcasting per oggi a Rivoli (Piemonte).
    Il testo deve essere discorsivo, accattivante e professionale, perfetto per la tua pagina Facebook di meteorologia.

    Dividi la cronaca in 4 fasce orarie:
    - Mattino (06-12)
    - Pomeriggio (12-18)
    - Sera (18-24)
    - Notte (00-06)

    Analizza i seguenti dati di pioggia (in mm) forniti dai modelli ad altissima risoluzione. 
    Hai a disposizione:
    - ICON-D2 (Deterministico tedesco)
    - AROME (Deterministico francese)
    - ICON-D2 EPS Media (La media dei 20 scenari dell'ensemble, indica la tendenza generale)
    - ICON-D2 EPS Max (Il picco massimo tra i 20 scenari, indica il "rischio peggiore" in caso di temporali intensi)

    Se l'EPS Max è alto ma la Media è bassa, significa che c'è rischio di fenomeni intensi ma molto localizzati o incerti. Fallo notare ai lettori usando termini probabilistici.
    Non incollare la tabella dei dati grezzi, scrivi solo il testo narrativo del bollettino usando emoji adatte.

    DATI GREZZI DEI MODELLI:
    {dati_meteo}
    """

    try:
        # Usiamo l'alias 'gemini-1.5-flash-latest' che è più robusto per le chiamate API
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.25,
            )
        )
        return response.text
    except Exception as e:
        print(f"❌ Errore Google Generative AI: {e}")
        sys.exit(1)

def invia_telegram(testo):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": testo, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def fetch_api(url, params):
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ Errore fetch API ({url}): {e}")
        return None

def main():
    print("📥 1. Scaricamento Deterministici (ICON-D2, AROME)...")
    dati_det = fetch_api(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": LAT, "longitude": LON,
            "hourly": "precipitation",
            "models": "icon_d2,arome_france",
            "timezone": "Europe/Rome",
            "forecast_days": 1
        }
    )

    print("📥 2. Scaricamento Ensemble (ICON-D2 EPS 20 membri)...")
    dati_eps = fetch_api(
        "https://ensemble-api.open-meteo.com/v1/ensemble",
        {
            "latitude": LAT, "longitude": LON,
            "hourly": "precipitation",
            "models": "icon_d2",
            "timezone": "Europe/Rome",
            "forecast_days": 1
        }
    )

    if not dati_det or not dati_eps:
        print("❌ Impossibile recuperare i dati meteo. Uscita.")
        sys.exit(1)

    orari = dati_det["hourly"]["time"]
    
    pioggia_d2 = [p if p is not None else 0.0 for p in dati_det["hourly"].get("precipitation_icon_d2", [0]*24)]
    pioggia_arome = [p if p is not None else 0.0 for p in dati_det["hourly"].get("precipitation_arome_france", [0]*24)]

    print("🧮 Calcolo Media e Max sui 20 scenari EPS...")
    pioggia_eps_media = []
    pioggia_eps_max = []
    
    for i in range(24):
        valori_ora_eps = []
        for membro in range(1, 21):
            chiave = f"precipitation_member{membro:02d}"
            if chiave in dati_eps["hourly"]:
                valore = dati_eps["hourly"][chiave][i]
                if valore is not None:
                    valori_ora_eps.append(valore)
        
        if valori_ora_eps:
            media = sum(valori_ora_eps) / len(valori_ora_eps)
            massimo = max(valori_ora_eps)
            pioggia_eps_media.append(round(media, 2))
            pioggia_eps_max.append(round(massimo, 2))
        else:
            pioggia_eps_media.append(0.0)
            pioggia_eps_max.append(0.0)

    print("📊 Assemblaggio della Tabellona Dati per l'Intelligenza Artificiale...")
    riassunto_dati = "Ora | ICON-D2 | AROME | EPS-Media | EPS-Max\n"
    
    for i in range(24):
        ora = orari[i][-5:]
        riassunto_dati += f"{ora} | {pioggia_d2[i]}mm | {pioggia_arome[i]}mm | {pioggia_eps_media[i]}mm | {pioggia_eps_max[i]}mm\n"
        
    print("🧠 Elaborazione analisi tramite Gemini 1.5 Flash...")
    bollettino_narrativo = interpella_gemini(riassunto_dati)
    
    print("✈️ Invio della cronaca su Telegram...")
    invia_telegram(bollettino_narrativo)
    print("✅ Finito! EPS integrato con successo.")

if __name__ == "__main__":
    main()
