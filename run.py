import uvicorn
import os
from pathlib import Path

# Assicurati che le directory necessarie esistano
def setup_directories():
    # Directory dati
    Path("app/data").mkdir(parents=True, exist_ok=True)
    Path("app/data/corsi").mkdir(parents=True, exist_ok=True)
    Path("app/data/contenuti").mkdir(parents=True, exist_ok=True)
    
    # Directory configurazione
    Path("app/config").mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    # Crea le directory necessarie
    setup_directories()
    
    # Avvia l'applicazione
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True) 