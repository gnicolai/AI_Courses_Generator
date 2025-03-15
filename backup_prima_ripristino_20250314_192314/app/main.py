from fastapi import FastAPI, Request, Form, Depends, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import yaml
import uuid
import traceback
import uvicorn
import logging
from typing import Dict, Any, List, Optional

from app.config import load_config, save_config, get_config_value
from app.api.ai_client import create_ai_client
from app.models.database import (
    init_db, 
    carica_corso, 
    carica_contenuti_corso,
    lista_corsi,
    elimina_corso
)
from app.api.controllers import (
    crea_corso, 
    genera_scaletta_corso, 
    genera_contenuto_capitolo,
    modifica_scaletta,
    modifica_contenuto_capitolo,
    esporta_corso,
    percento_completamento,
    carica_contenuto_capitolo,
    espandi_contenuti_corso,
    get_stato_espansione,
    pausa_espansione,
    riprendi_espansione,
    annulla_espansione
)

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crea l'app FastAPI
app = FastAPI(title="AI Course Generator")

# Configura i template
templates = Jinja2Templates(directory="app/templates")

# Configura i file statici
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Inizializza il database
os.makedirs("app/data/corsi", exist_ok=True)
os.makedirs("app/data/contenuti", exist_ok=True)
init_db()  # Inizializza esplicitamente il database

# Monta le rotte API
# app.include_router(api_router, prefix="/api")

# Rotte principali
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Pagina principale dell'applicazione."""
    try:
        # Carica la lista dei corsi
        corsi = lista_corsi()
        
        # Rendering del template
        return templates.TemplateResponse(
            "home.html", 
            {"request": request, "title": "AI Course Generator", "corsi": corsi}
        )
    except Exception as e:
        print(f"ERRORE in home(): {str(e)}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise

@app.get("/miei-corsi", response_class=HTMLResponse)
async def miei_corsi_page(request: Request):
    """Pagina che mostra tutti i corsi disponibili dell'utente."""
    
    logger.info("Accesso alla pagina /miei-corsi richiesto - usando template dedicato")
    
    try:
        # Carica tutti i corsi disponibili
        logger.info("Tentativo di caricare la lista dei corsi (route /miei-corsi)")
        corsi = lista_corsi()
        logger.info(f"Corsi caricati in /miei-corsi: {len(corsi)} trovati")
        
        # Prepara i dati per il template
        percentuale_completamento = {}
        capitoli_generati = {}
        num_capitoli = {}
        
        # Calcola lo stato di completamento per ogni corso
        for corso_item in corsi:
            corso_id = corso_item["id"]
            percentuale = percento_completamento(corso_id)
            percentuale_completamento[corso_id] = percentuale
            
            # Carica il corso completo per ottenere informazioni sui capitoli
            corso_completo = carica_corso(corso_id)
            
            # Verifica attentamente la struttura del corso
            if (corso_completo and 
                corso_completo.get("scaletta") is not None and 
                isinstance(corso_completo["scaletta"], dict) and 
                "capitoli" in corso_completo["scaletta"]):
                
                num_capitoli_totali = len(corso_completo["scaletta"]["capitoli"])
                num_capitoli[corso_id] = num_capitoli_totali
                
                # Conta i capitoli già generati
                contenuti = carica_contenuti_corso(corso_id)
                capitoli_con_contenuto = 0
                for capitolo in corso_completo["scaletta"]["capitoli"]:
                    if capitolo["id"] in contenuti:
                        capitoli_con_contenuto += 1
                
                capitoli_generati[corso_id] = capitoli_con_contenuto
            else:
                # Se non c'è una scaletta valida, imposta i valori predefiniti
                num_capitoli[corso_id] = 0
                capitoli_generati[corso_id] = 0

        logger.info("Rendering del template miei_corsi.html da /miei-corsi")
        return templates.TemplateResponse("miei_corsi.html", {
            "request": request,
            "title": "I Miei Corsi",
            "corsi": corsi,
            "percentuale_completamento": percentuale_completamento,
            "capitoli_generati": capitoli_generati,
            "num_capitoli": num_capitoli
        })
    except Exception as e:
        logger.error(f"Errore nella pagina /miei-corsi: {str(e)}")
        logger.error(f"Tracciamento: {traceback.format_exc()}")
        raise

@app.get("/corsi", response_class=HTMLResponse)
async def lista_corsi_page(request: Request):
    """Pagina che mostra tutti i corsi disponibili."""
    
    logger.info("Accesso alla pagina /corsi richiesto")
    
    try:
        # Carica tutti i corsi disponibili
        logger.info("Tentativo di caricare la lista dei corsi (route /corsi)")
        corsi = lista_corsi()
        logger.info(f"Corsi caricati in /corsi: {len(corsi)} trovati")
        
        # Prepara i dati per il template
        percentuale_completamento = {}
        capitoli_generati = {}
        num_capitoli = {}
        
        # Calcola lo stato di completamento per ogni corso
        for corso_item in corsi:
            corso_id = corso_item["id"]
            percentuale = percento_completamento(corso_id)
            percentuale_completamento[corso_id] = percentuale
            
            # Carica il corso completo per ottenere informazioni sui capitoli
            corso_completo = carica_corso(corso_id)
            
            # Verifica attentamente la struttura del corso
            if (corso_completo and 
                corso_completo.get("scaletta") is not None and 
                isinstance(corso_completo["scaletta"], dict) and 
                "capitoli" in corso_completo["scaletta"]):
                
                num_capitoli_totali = len(corso_completo["scaletta"]["capitoli"])
                num_capitoli[corso_id] = num_capitoli_totali
                
                # Conta i capitoli già generati
                contenuti = carica_contenuti_corso(corso_id)
                capitoli_con_contenuto = 0
                for capitolo in corso_completo["scaletta"]["capitoli"]:
                    if capitolo["id"] in contenuti:
                        capitoli_con_contenuto += 1
                
                capitoli_generati[corso_id] = capitoli_con_contenuto
            else:
                # Se non c'è una scaletta valida, imposta i valori predefiniti
                num_capitoli[corso_id] = 0
                capitoli_generati[corso_id] = 0

        logger.info("Rendering del template corsi.html da /corsi")
        return templates.TemplateResponse("corsi.html", {
            "request": request,
            "title": "I Miei Corsi",
            "corsi": corsi,
            "percentuale_completamento": percentuale_completamento,
            "capitoli_generati": capitoli_generati,
            "num_capitoli": num_capitoli
        })
    except Exception as e:
        logger.error(f"Errore nella pagina /corsi: {str(e)}")
        logger.error(f"Tracciamento: {traceback.format_exc()}")
        raise

@app.get("/nuovo-corso", response_class=HTMLResponse)
async def nuovo_corso_form(request: Request):
    """Form per la creazione di un nuovo corso."""
    return templates.TemplateResponse(
        "nuovo_corso.html", 
        {"request": request, "title": "Nuovo Corso"}
    )

@app.post("/nuovo-corso")
async def nuovo_corso_submit(
    request: Request,
    titolo: str = Form(...),
    descrizione: str = Form(...),
    pubblico_target: str = Form(...),
    livello_complessita: str = Form(...),
    tono: str = Form(...),
    requisiti_specifici: str = Form(""),
    stile_scrittura: str = Form("")
):
    """Gestisce la creazione di un nuovo corso."""
    # Crea un dizionario con i parametri del corso
    parametri = {
        "titolo": titolo,
        "descrizione": descrizione,
        "pubblico_target": pubblico_target,
        "livello_complessita": livello_complessita,
        "tono": tono,
        "requisiti_specifici": requisiti_specifici,
        "stile_scrittura": stile_scrittura
    }
    
    # Crea il corso
    risultato = await crea_corso(parametri)
    
    if risultato["success"]:
        # Reindirizza alla pagina del corso
        return RedirectResponse(url=f"/corso/{risultato['corso_id']}", status_code=303)
    else:
        # Mostra un errore
        return templates.TemplateResponse(
            "nuovo_corso.html", 
            {
                "request": request, 
                "title": "Nuovo Corso",
                "error": risultato["message"],
                "parametri": parametri
            }
        )

@app.get("/corso/{corso_id}", response_class=HTMLResponse)
async def visualizza_corso(request: Request, corso_id: str):
    """Visualizza i dettagli di un corso."""
    # Carica il corso dal database
    corso = carica_corso(corso_id)
    
    if not corso:
        raise HTTPException(status_code=404, detail="Corso non trovato")
    
    # Verifica se la scaletta è stata generata
    has_scaletta = corso.get("scaletta") is not None
    
    # Estrai i parametri del corso per il template
    parametri = corso["parametri"]
    
    return templates.TemplateResponse(
        "corso_creato.html", 
        {
            "request": request, 
            "title": parametri["titolo"],
            "corso_id": corso_id,
            "has_scaletta": has_scaletta,
            "titolo": parametri["titolo"],
            "descrizione": parametri["descrizione"],
            "pubblico_target": parametri["pubblico_target"],
            "livello_complessita": parametri["livello_complessita"],
            "tono_corso": parametri["tono"],  # Nota: tono viene mappato a tono_corso nel template
            "requisiti": parametri.get("requisiti_specifici", ""),
            "stile_scrittura": parametri.get("stile_scrittura", "")
        }
    )

@app.get("/corso/{corso_id}/generazione", response_class=HTMLResponse)
async def generazione_contenuti(request: Request, corso_id: str):
    """Pagina per la generazione progressiva dei contenuti."""
    # Carica il corso dal database
    corso = carica_corso(corso_id)
    
    if not corso:
        raise HTTPException(status_code=404, detail="Corso non trovato")
    
    # Verifica se la scaletta è stata generata
    if not corso.get("scaletta"):
        return RedirectResponse(url=f"/corso/{corso_id}", status_code=303)
    
    # Carica i contenuti già generati
    contenuti = carica_contenuti_corso(corso_id)
    
    # Prepara i dati dei capitoli con lo stato di generazione
    capitoli = []
    for cap in corso["scaletta"]["capitoli"]:
        # Gestisci sia il vecchio formato (sottoargomenti) che il nuovo (sottocapitoli)
        if "sottocapitoli" in cap:
            num_elementi = len(cap["sottocapitoli"])
        elif "sottoargomenti" in cap:
            num_elementi = len(cap["sottoargomenti"])
        else:
            num_elementi = 0
            
        capitoli.append({
            "id": cap["id"],
            "titolo": cap["titolo"],
            "num_sottoargomenti": num_elementi,
            "generato": cap["id"] in contenuti
        })
    
    # Calcola la percentuale di completamento
    percentuale = percento_completamento(corso_id)
    
    return templates.TemplateResponse(
        "generazione.html", 
        {
            "request": request, 
            "title": corso["parametri"]["titolo"],
            "corso_id": corso_id,
            "corso_titolo": corso["parametri"]["titolo"],
            "capitoli": capitoli,
            "percentuale_completamento": percentuale
        }
    )

@app.get("/corso/{corso_id}/scaletta", response_class=HTMLResponse)
async def visualizza_scaletta(request: Request, corso_id: str):
    """Visualizza e consente di modificare la scaletta di un corso."""
    # Carica il corso dal database
    corso = carica_corso(corso_id)
    
    if not corso:
        raise HTTPException(status_code=404, detail="Corso non trovato")
    
    # Verifica se la scaletta è stata generata
    if not corso.get("scaletta"):
        # Se la scaletta non è stata generata, reindirizza alla pagina del corso
        return RedirectResponse(url=f"/corso/{corso_id}", status_code=303)
    
    return templates.TemplateResponse(
        "scaletta.html", 
        {
            "request": request, 
            "title": corso["parametri"]["titolo"],
            "corso_id": corso_id,
            "corso_titolo": corso["parametri"]["titolo"],
            "scaletta": corso["scaletta"],
            "requisiti_specifici": corso["parametri"].get("requisiti_specifici", ""),
            "stile_scrittura": corso["parametri"].get("stile_scrittura", "")
        }
    )

@app.get("/corso/{corso_id}/capitolo/{capitolo_id}", response_class=HTMLResponse)
async def visualizza_capitolo(request: Request, corso_id: str, capitolo_id: str):
    """Visualizza un singolo capitolo del corso."""
    # Carica il corso dal database
    corso = carica_corso(corso_id)
    
    if not corso:
        raise HTTPException(status_code=404, detail="Corso non trovato")
    
    # Verifica se la scaletta è stata generata
    if not corso.get("scaletta"):
        return RedirectResponse(url=f"/corso/{corso_id}", status_code=303)
    
    # Trova il capitolo nella scaletta
    capitolo = None
    for cap in corso["scaletta"]["capitoli"]:
        if cap["id"] == capitolo_id:
            capitolo = cap
            break
            
    if not capitolo:
        raise HTTPException(status_code=404, detail="Capitolo non trovato")
    
    # Controlla se il contenuto è già stato generato
    contenuto = carica_contenuto_capitolo(corso_id, capitolo_id)
    has_contenuto = contenuto is not None
    
    # Carica il modello utilizzato per la generazione, se disponibile
    modello_utilizzato = None
    if hasattr(capitolo, "modello_utilizzato"):
        modello_utilizzato = capitolo.get("modello_utilizzato")
    
    return templates.TemplateResponse(
        "capitolo.html", 
        {
            "request": request, 
            "title": capitolo["titolo"],
            "corso_id": corso_id,
            "titolo_corso": corso["parametri"]["titolo"],
            "capitolo": capitolo,
            "capitolo_id": capitolo_id,
            "has_contenuto": has_contenuto,
            "contenuto": contenuto or "",
            "scaletta": corso["scaletta"],
            "modello_utilizzato": modello_utilizzato
        }
    )

@app.get("/impostazioni")
async def impostazioni_form(request: Request):
    """Mostra la pagina delle impostazioni."""
    config = load_config()
    
    # Verifica se le chiavi API sono configurate
    openai_configured = bool(config.get("openai_api_key", ""))
    deepseek_configured = bool(config.get("deepseek_api_key", ""))
    
    # Provider attualmente in uso
    current_provider = config.get("ai_provider", "openai")
    # Non mostriamo più l'opzione mock, quindi assicuriamoci che il provider sia valido
    if current_provider == "mock":
        current_provider = "openai"
        config["ai_provider"] = current_provider
        save_config(config)
    
    is_using_mock = current_provider == "mock" or (
        (current_provider == "openai" and not openai_configured) or 
        (current_provider == "deepseek" and not deepseek_configured)
    )
    
    # Creiamo versioni mascherate delle chiavi API
    openai_api_key = config.get("openai_api_key", "")
    deepseek_api_key = config.get("deepseek_api_key", "")
    
    config["openai_api_key_masked"] = mask_api_key(openai_api_key)
    config["deepseek_api_key_masked"] = mask_api_key(deepseek_api_key)
    
    api_status = {
        "current_provider": current_provider,
        "using_mock": is_using_mock,
        "openai_configured": openai_configured,
        "deepseek_configured": deepseek_configured
    }
    
    return templates.TemplateResponse(
        "impostazioni.html",
        {
            "request": request,
            "title": "Impostazioni",
            "config": config,
            "success": False,
            "api_status": api_status
        }
    )

@app.post("/impostazioni")
async def impostazioni_submit(
    request: Request, 
    ai_provider: str = Form(...),
    openai_model: str = Form(None),
    deepseek_model: str = Form(None)
):
    """
    Gestisce il salvataggio delle impostazioni.
    """
    try:
        # Carica la configurazione attuale
        config = load_config()
        
        # Verifica che il provider selezionato sia valido
        if ai_provider not in ["openai", "deepseek"]:
            return templates.TemplateResponse(
                "impostazioni.html",
                {
                    "request": request,
                    "title": "Impostazioni",
                    "config": config,
                    "error": "Provider AI non valido"
                }
            )
        
        # Aggiorna il provider
        config["ai_provider"] = ai_provider
        logger.info(f"Impostato provider AI a: {ai_provider}")
        
        # Aggiorna il modello OpenAI se specificato
        if openai_model:
            config["openai_model"] = openai_model
        
        # Aggiorna il modello DeepSeek se specificato
        if deepseek_model:
            config["deepseek_model"] = deepseek_model
            logger.info(f"Impostato modello DeepSeek a: {deepseek_model}")
        
        # Salva le impostazioni
        success = save_config(config)
        
        # Ricrea il client AI con le nuove impostazioni
        create_ai_client()
        logger.info(f"Client AI ricreato con il provider: {ai_provider}")
        
        # Prepara i dati per la risposta
        openai_configured = bool(config.get("openai_api_key", ""))
        deepseek_configured = bool(config.get("deepseek_api_key", ""))
        
        # Provider attualmente in uso
        current_provider = config.get("ai_provider", "openai")
        is_using_mock = current_provider == "mock" or (
            (current_provider == "openai" and not openai_configured) or 
            (current_provider == "deepseek" and not deepseek_configured)
        )
        
        # Creiamo versioni mascherate delle chiavi API
        openai_api_key = config.get("openai_api_key", "")
        deepseek_api_key = config.get("deepseek_api_key", "")
        
        config["openai_api_key_masked"] = mask_api_key(openai_api_key)
        config["deepseek_api_key_masked"] = mask_api_key(deepseek_api_key)
        
        api_status = {
            "current_provider": current_provider,
            "using_mock": is_using_mock,
            "openai_configured": openai_configured,
            "deepseek_configured": deepseek_configured
        }
        
        return templates.TemplateResponse(
            "impostazioni.html",
            {
                "request": request,
                "title": "Impostazioni",
                "config": config,
                "success": success,
                "api_status": api_status
            }
        )
    except Exception as e:
        logger.exception(f"Errore durante il salvataggio delle impostazioni: {str(e)}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request, 
                "title": "Errore", 
                "message": f"Si è verificato un errore durante il salvataggio delle impostazioni: {str(e)}"
            }
        )

# Funzione di utilità per mascherare le chiavi API
def mask_api_key(api_key: str) -> str:
    """Maschera una chiave API mostrando solo i primi e gli ultimi 4 caratteri."""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]

# API Endpoints
@app.post("/api/corso/{corso_id}/genera-scaletta")
async def api_genera_scaletta(corso_id: str, request: Request):
    """API per generare la scaletta di un corso."""
    try:
        print(f"Ricevuta richiesta per generare scaletta per corso: {corso_id}")
        # Ottieni il corpo della richiesta se presente
        body = {}
        try:
            body = await request.json()
            print(f"Body della richiesta: {body}")
        except:
            # Se non c'è un corpo o non è JSON, procedi comunque
            print("Nessun body JSON nella richiesta")
            pass
            
        result = await genera_scaletta_corso(corso_id)
        print(f"Risultato: {result}")
        return result
    except Exception as e:
        print(f"Errore in api_genera_scaletta: {str(e)}")
        logger.error(f"Errore in api_genera_scaletta: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/corso/{corso_id}/capitolo/{capitolo_id}/genera-contenuto")
async def api_genera_contenuto(corso_id: str, capitolo_id: str):
    """API per generare il contenuto di un capitolo."""
    return await genera_contenuto_capitolo(corso_id, capitolo_id)

@app.get("/api/corso/{corso_id}/capitolo/{capitolo_id}/contenuto")
async def api_get_contenuto(corso_id: str, capitolo_id: str):
    """API per ottenere il contenuto di un capitolo."""
    contenuto = carica_contenuto_capitolo(corso_id, capitolo_id)
    
    if not contenuto:
        return {"success": False, "message": "Contenuto non trovato"}
    
    return {"success": True, "contenuto": contenuto}

@app.put("/api/corso/{corso_id}/capitolo/{capitolo_id}/contenuto/edit")
async def api_modifica_contenuto(corso_id: str, capitolo_id: str, dati: dict = Body(...)):
    """API per modificare il contenuto di un capitolo."""
    contenuto = dati.get("contenuto", "")
    if not contenuto:
        return {"success": False, "message": "Contenuto mancante"}
        
    risultato = await modifica_contenuto_capitolo(corso_id, capitolo_id, contenuto)
    return risultato

@app.post("/api/corso/{corso_id}/genera-scaletta-redirect")
async def api_genera_scaletta_redirect(corso_id: str, request: Request):
    """API per generare la scaletta di un corso con reindirizzamento diretto."""
    try:
        # Genera la scaletta
        result = await genera_scaletta_corso(corso_id)
        
        if result.get("success", False):
            # Reindirizza alla pagina della scaletta
            return RedirectResponse(url=f"/corso/{corso_id}/scaletta", status_code=303)
        else:
            # Torna alla pagina del corso con un messaggio di errore
            return RedirectResponse(url=f"/corso/{corso_id}", status_code=303)
    except Exception as e:
        logger.error(f"Errore in api_genera_scaletta_redirect: {str(e)}")
        # Torna alla pagina del corso con un messaggio di errore
        return RedirectResponse(url=f"/corso/{corso_id}", status_code=303)

@app.get("/api/status", response_class=JSONResponse)
async def api_status():
    """Verifica lo stato e la configurazione delle API."""
    config = load_config()
    
    # Rimuovi le chiavi API complete per sicurezza
    safe_config = config.copy()
    if "openai_api_key" in safe_config and safe_config["openai_api_key"]:
        safe_config["openai_api_key"] = f"{safe_config['openai_api_key'][:5]}...{safe_config['openai_api_key'][-4:]}"
    if "deepseek_api_key" in safe_config and safe_config["deepseek_api_key"]:
        safe_config["deepseek_api_key"] = f"{safe_config['deepseek_api_key'][:5]}...{safe_config['deepseek_api_key'][-4:]}"
    
    # Verifica se le chiavi API sono configurate
    openai_configured = bool(config.get("openai_api_key", ""))
    deepseek_configured = bool(config.get("deepseek_api_key", ""))
    
    # Provider attualmente in uso
    current_provider = config.get("ai_provider", "mock")
    is_using_mock = current_provider == "mock" or (
        (current_provider == "openai" and not openai_configured) or 
        (current_provider == "deepseek" and not deepseek_configured)
    )
    
    return {
        "status": "online",
        "current_provider": current_provider,
        "using_mock": is_using_mock,
        "api_configuration": {
            "openai": {
                "configured": openai_configured,
                "base_url": config.get("openai_base_url", "")
            },
            "deepseek": {
                "configured": deepseek_configured,
                "base_url": config.get("deepseek_base_url", "")
            }
        },
        "config": safe_config
    }

@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        error_detail = str(e)
        stack_trace = traceback.format_exc()
        print(f"ERRORE 500: {error_detail}")
        print(f"STACK TRACE: {stack_trace}")
        return templates.TemplateResponse(
            "error.html", 
            {"request": request, "error": error_detail, "stack_trace": stack_trace},
            status_code=500
        )

@app.get("/corso/{corso_id}/finalizza", response_class=HTMLResponse)
async def finalizza_corso_page(request: Request, corso_id: str):
    """Pagina per finalizzare ed esportare un corso."""
    # Carica il corso dal database
    corso = carica_corso(corso_id)
    
    if not corso:
        raise HTTPException(status_code=404, detail="Corso non trovato")
    
    # Verifica se la scaletta è stata generata
    if not corso.get("scaletta"):
        return RedirectResponse(url=f"/corso/{corso_id}", status_code=303)
    
    # Carica i contenuti già generati
    contenuti = carica_contenuti_corso(corso_id)
    
    # Verifica se tutti i capitoli sono stati generati
    capitoli_mancanti = []
    for cap in corso["scaletta"]["capitoli"]:
        if cap["id"] not in contenuti:
            capitoli_mancanti.append(cap["titolo"])
    
    # Calcola la percentuale di completamento
    percentuale = percento_completamento(corso_id)
    
    return templates.TemplateResponse(
        "finalizza.html", 
        {
            "request": request, 
            "title": "Finalizza - " + corso["parametri"]["titolo"],
            "corso_id": corso_id,
            "corso": corso,
            "percentuale_completamento": percentuale,
            "capitoli_mancanti": capitoli_mancanti,
            "completato": len(capitoli_mancanti) == 0
        }
    )

@app.get("/api/corso/{corso_id}/esporta")
async def api_esporta_corso(corso_id: str, formato: str = "markdown"):
    """API per esportare un corso nel formato specificato."""
    return await esporta_corso(corso_id, formato)

@app.delete("/api/corso/{corso_id}", response_class=JSONResponse)
async def api_elimina_corso(corso_id: str):
    """Elimina un corso e tutti i suoi contenuti associati."""
    logger.info(f"Richiesta eliminazione corso con ID: {corso_id}")
    
    try:
        success = elimina_corso(corso_id)
        if success:
            logger.info(f"Corso {corso_id} eliminato con successo")
            return {"success": True, "message": "Corso eliminato con successo"}
        else:
            logger.error(f"Errore nell'eliminazione del corso {corso_id}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Errore durante l'eliminazione del corso"}
            )
    except Exception as e:
        logger.error(f"Eccezione durante l'eliminazione del corso {corso_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Errore: {str(e)}"}
        )

@app.post("/api/corso/{corso_id}/elimina", response_class=JSONResponse)
async def api_elimina_corso_post(corso_id: str):
    """Endpoint alternativo per eliminare un corso (via POST)."""
    logger.info(f"Richiesta eliminazione corso con ID: {corso_id} (via POST)")
    
    try:
        success = elimina_corso(corso_id)
        if success:
            logger.info(f"Corso {corso_id} eliminato con successo (via POST)")
            return {"success": True, "message": "Corso eliminato con successo"}
        else:
            logger.error(f"Errore nell'eliminazione del corso {corso_id} (via POST)")
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Errore durante l'eliminazione del corso"}
            )
    except Exception as e:
        logger.error(f"Eccezione durante l'eliminazione del corso {corso_id} (via POST): {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Errore: {str(e)}"}
        )

# Endpoint per l'eliminazione tramite form HTML standard
@app.post("/corso/{corso_id}/elimina")
async def elimina_corso_action(corso_id: str, request: Request):
    """Endpoint per eliminare un corso tramite form standard."""
    logger.info(f"Richiesta eliminazione corso con ID: {corso_id} tramite form")
    
    try:
        success = elimina_corso(corso_id)
        if success:
            logger.info(f"Corso {corso_id} eliminato con successo")
            # Redirect alla pagina dei corsi
            return RedirectResponse(url="/miei-corsi", status_code=303)
        else:
            logger.error(f"Errore nell'eliminazione del corso {corso_id}")
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Errore durante l'eliminazione del corso",
                "stack_trace": "Operazione non riuscita"
            }, status_code=500)
    except Exception as e:
        logger.error(f"Eccezione durante l'eliminazione del corso {corso_id}: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Errore: {str(e)}",
            "stack_trace": traceback.format_exc()
        }, status_code=500)

@app.post("/api/corso/{corso_id}/espandi", response_class=JSONResponse)
async def api_espandi_contenuti_corso(corso_id: str, parametri: Dict[str, Any] = Body(...)):
    """
    Espande i contenuti di tutti i capitoli di un corso.
    
    Args:
        corso_id: ID del corso
        parametri: Parametri per l'espansione
        
    Returns:
        Risultato dell'operazione
    """
    try:
        # Estrai i parametri di controllo del flusso
        continua_dopo_errore = parametri.get("continua_dopo_errore", False)
        pausa_tra_capitoli = parametri.get("pausa_tra_capitoli", 0)
        
        # Aggiungi i parametri di controllo del flusso
        parametri_completi = {
            **parametri,
            "continua_dopo_errore": continua_dopo_errore,
            "pausa_tra_capitoli": pausa_tra_capitoli
        }
        
        # Chiama il controller per l'espansione
        risultato = await espandi_contenuti_corso(corso_id, parametri_completi)
        return risultato
    except Exception as e:
        logging.exception(f"Errore nell'espansione dei contenuti del corso {corso_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nell'espansione dei contenuti: {str(e)}"
        }

@app.get("/api/corso/{corso_id}/espansione-stato", response_class=JSONResponse)
async def api_stato_espansione(corso_id: str):
    """
    Restituisce lo stato corrente dell'espansione per un corso.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        Stato dell'espansione
    """
    try:
        # Recupera lo stato dell'espansione dal database o dalla cache
        stato = get_stato_espansione(corso_id)
        return stato
    except Exception as e:
        logging.exception(f"Errore nel recupero dello stato dell'espansione per il corso {corso_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nel recupero dello stato dell'espansione: {str(e)}",
            "stato": "errore"
        }

@app.post("/api/corso/{corso_id}/espansione-pausa", response_class=JSONResponse)
async def api_pausa_espansione(corso_id: str):
    """
    Mette in pausa l'espansione di un corso.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        Risultato dell'operazione
    """
    try:
        # Metti in pausa l'espansione
        success = pausa_espansione(corso_id)
        return {
            "success": success,
            "message": "Espansione messa in pausa" if success else "Impossibile mettere in pausa l'espansione"
        }
    except Exception as e:
        logging.exception(f"Errore nella pausa dell'espansione per il corso {corso_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nella pausa dell'espansione: {str(e)}"
        }

@app.post("/api/corso/{corso_id}/espansione-riprendi", response_class=JSONResponse)
async def api_riprendi_espansione(corso_id: str):
    """
    Riprende l'espansione di un corso precedentemente messa in pausa.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        Risultato dell'operazione
    """
    try:
        # Riprendi l'espansione
        success = riprendi_espansione(corso_id)
        return {
            "success": success,
            "message": "Espansione ripresa" if success else "Impossibile riprendere l'espansione"
        }
    except Exception as e:
        logging.exception(f"Errore nella ripresa dell'espansione per il corso {corso_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nella ripresa dell'espansione: {str(e)}"
        }

@app.post("/api/corso/{corso_id}/espansione-annulla", response_class=JSONResponse)
async def api_annulla_espansione(corso_id: str):
    """
    Annulla l'espansione di un corso in corso.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        Risultato dell'operazione
    """
    try:
        # Annulla l'espansione
        success = annulla_espansione(corso_id)
        return {
            "success": success,
            "message": "Espansione annullata" if success else "Impossibile annullare l'espansione"
        }
    except Exception as e:
        logging.exception(f"Errore nell'annullamento dell'espansione per il corso {corso_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nell'annullamento dell'espansione: {str(e)}"
        }

@app.get("/api/verifica-chiave-api", response_class=JSONResponse)
async def api_verifica_chiave_api():
    """
    Verifica la validità della chiave API di OpenAI.
    
    Returns:
        Risultato della verifica
    """
    try:
        # Inizializza il client AI
        ai_client = create_ai_client()
        
        # Verifica la chiave API
        risultato = await ai_client.verifica_chiave_api()
        return risultato
    except Exception as e:
        logging.exception(f"Errore nella verifica della chiave API: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nella verifica della chiave API: {str(e)}"
        }

@app.get("/api/modelli-disponibili", response_class=JSONResponse)
async def api_modelli_disponibili():
    """
    Ottiene la lista dei modelli disponibili per l'account OpenAI.
    
    Returns:
        Lista dei modelli disponibili
    """
    try:
        # Inizializza il client AI
        ai_client = create_ai_client()
        
        # Ottieni la lista dei modelli disponibili
        modelli = await ai_client.get_available_models()
        
        # Filtra i modelli di alta qualità
        modelli_alta_qualita = [m for m in modelli if any(m.startswith(prefix) for prefix in ["o1-preview", "o1", "gpt-4o", "gpt-4-turbo"])]
        
        return {
            "success": True,
            "modelli": modelli,
            "modelli_alta_qualita": modelli_alta_qualita
        }
    except Exception as e:
        logging.exception(f"Errore nel recupero dei modelli disponibili: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nel recupero dei modelli disponibili: {str(e)}"
        }

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 