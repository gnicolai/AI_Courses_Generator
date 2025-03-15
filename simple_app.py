from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import json
import traceback
from typing import Dict, Any, List, Optional
import sqlite3
from pathlib import Path

# Inizializzazione dell'app
app = FastAPI()

# Configura i template e i file statici
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Configura il database
DB_PATH = Path("app/data/corsi.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def init_db():
    """Inizializza il database creando le tabelle necessarie."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabella per i corsi
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS corsi (
        id TEXT PRIMARY KEY,
        parametri TEXT NOT NULL,
        scaletta TEXT,
        creato TEXT NOT NULL,
        ultimo_aggiornamento TEXT,
        completato INTEGER DEFAULT 0
    )
    ''')
    
    # Tabella per i contenuti dei capitoli
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS contenuti_capitoli (
        id TEXT PRIMARY KEY,
        corso_id TEXT NOT NULL,
        capitolo_id TEXT NOT NULL,
        contenuto TEXT,
        generato INTEGER DEFAULT 0,
        ultimo_aggiornamento TEXT,
        FOREIGN KEY (corso_id) REFERENCES corsi(id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Inizializza il database
init_db()

# Rotte principali
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Pagina principale dell'applicazione."""
    return templates.TemplateResponse(
        "home.html", 
        {"request": request, "title": "AI Course Generator"}
    )

@app.get("/nuovo-corso", response_class=HTMLResponse)
async def nuovo_corso_form(request: Request):
    """Form per la creazione di un nuovo corso."""
    return templates.TemplateResponse(
        "nuovo_corso.html", 
        {"request": request, "title": "Crea Nuovo Corso"}
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
    """Gestisce l'invio del form per la creazione di un nuovo corso."""
    try:
        print(f"DEBUG: Ricezione dati nuovo corso: {titolo}")
        
        # Crea un dizionario con i parametri del corso
        parametri_corso = {
            "titolo": titolo,
            "descrizione": descrizione,
            "pubblico_target": pubblico_target,
            "livello_complessita": livello_complessita,
            "tono": tono,
            "requisiti_specifici": requisiti_specifici,
            "stile_scrittura": stile_scrittura
        }
        
        # Salva il corso nel database
        corso_id = salva_corso(parametri_corso)
        
        # Redirect alla pagina del corso
        return RedirectResponse(url=f"/corso/{corso_id}", status_code=303)
    except Exception as e:
        print(f"ERRORE in nuovo_corso_submit: {str(e)}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise

# Funzione per salvare un corso nel database
def salva_corso(parametri: Dict[str, Any]) -> str:
    """Salva un nuovo corso nel database e restituisce l'ID generato."""
    import uuid
    from datetime import datetime
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    corso_id = str(uuid.uuid4())
    ora = datetime.now().isoformat()
    
    cursor.execute(
        "INSERT INTO corsi (id, parametri, creato) VALUES (?, ?, ?)",
        (corso_id, json.dumps(parametri), ora)
    )
    
    conn.commit()
    conn.close()
    
    return corso_id

@app.get("/corso/{corso_id}", response_class=HTMLResponse)
async def visualizza_corso(request: Request, corso_id: str):
    """Visualizza la pagina di un corso."""
    try:
        print(f"DEBUG: Visualizzazione corso: {corso_id}")
        
        # Carica il corso dal database
        corso = carica_corso(corso_id)
        if not corso:
            raise HTTPException(status_code=404, detail="Corso non trovato")
        
        # Prepara i dati per il template
        title = corso['parametri']['titolo']
        
        # Rendering del template
        return templates.TemplateResponse(
            "corso_creato.html", 
            {"request": request, "title": title, "corso": corso}
        )
    except Exception as e:
        print(f"ERRORE in visualizza_corso: {str(e)}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise

@app.post("/api/corso/{corso_id}/genera-scaletta")
async def api_genera_scaletta(corso_id: str):
    """API per generare la scaletta di un corso."""
    try:
        print(f"DEBUG: Generazione scaletta corso: {corso_id}")
        
        # Simula la generazione di una scaletta (in realtà, usiamo dati di esempio)
        scaletta = {
            "titolo": "Corso di esempio",
            "descrizione": "Questo è un corso di esempio generato automaticamente",
            "durata_stimata": "4 ore",
            "capitoli": [
                {
                    "id": "cap1",
                    "titolo": "Introduzione",
                    "descrizione": "Capitolo introduttivo",
                    "sottoargomenti": [
                        {
                            "titolo": "Concetti di base",
                            "punti_chiave": ["Punto 1", "Punto 2", "Punto 3"]
                        }
                    ]
                },
                {
                    "id": "cap2",
                    "titolo": "Argomento principale",
                    "descrizione": "Capitolo principale",
                    "sottoargomenti": [
                        {
                            "titolo": "Aspetti avanzati",
                            "punti_chiave": ["Punto A", "Punto B", "Punto C"]
                        }
                    ]
                }
            ]
        }
        
        # Salva la scaletta nel database
        salva_scaletta(corso_id, scaletta)
        
        return {"success": True, "message": "Scaletta generata con successo"}
    except Exception as e:
        print(f"ERRORE in api_genera_scaletta: {str(e)}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        return {"success": False, "message": str(e)}

def carica_corso(corso_id: str) -> Optional[Dict[str, Any]]:
    """Carica un corso dal database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM corsi WHERE id = ?", (corso_id,))
    corso_row = cursor.fetchone()
    
    if not corso_row:
        conn.close()
        return None
    
    corso = dict(corso_row)
    corso['parametri'] = json.loads(corso['parametri'])
    
    if corso.get('scaletta'):
        corso['scaletta'] = json.loads(corso['scaletta'])
    
    conn.close()
    return corso

def salva_scaletta(corso_id: str, scaletta: Dict[str, Any]) -> bool:
    """Salva la scaletta di un corso nel database."""
    from datetime import datetime
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    ora = datetime.now().isoformat()
    
    try:
        cursor.execute(
            "UPDATE corsi SET scaletta = ?, ultimo_aggiornamento = ? WHERE id = ?",
            (json.dumps(scaletta), ora, corso_id)
        )
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Errore nel salvataggio della scaletta: {e}")
        return False
    finally:
        conn.close()

# Middleware per catturare le eccezioni
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        error_detail = str(e)
        stack_trace = traceback.format_exc()
        print(f"ERRORE: {error_detail}")
        print(f"STACK TRACE: {stack_trace}")
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Errore</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .error {{ background-color: #ffeeee; padding: 20px; border: 1px solid #ff0000; }}
                    .stack-trace {{ background-color: #eeeeee; padding: 20px; overflow: auto; }}
                </style>
            </head>
            <body>
                <h1>Errore nell'applicazione</h1>
                <div class="error">
                    <h2>Dettagli errore:</h2>
                    <p>{error_detail}</p>
                </div>
                <h2>Stack Trace:</h2>
                <div class="stack-trace">
                    <pre>{stack_trace}</pre>
                </div>
            </body>
            </html>
            """,
            status_code=500
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000) 