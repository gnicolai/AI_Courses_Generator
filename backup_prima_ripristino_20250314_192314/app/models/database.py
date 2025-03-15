import sqlite3
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import os

DB_PATH = Path("app/data/corsi.db")

# Assicurati che la directory esista
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

def salva_corso(parametri: Dict[str, Any]) -> str:
    """Salva un nuovo corso nel database e restituisce l'ID generato."""
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

def salva_scaletta(corso_id: str, scaletta: Dict[str, Any]) -> bool:
    """Salva la scaletta di un corso nel database."""
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

def salva_contenuto_capitolo(corso_id: str, capitolo_id: str, contenuto: str, modello_utilizzato: str = None):
    """
    Salva il contenuto di un capitolo nel database.
    
    Args:
        corso_id: ID del corso
        capitolo_id: ID del capitolo
        contenuto: Contenuto del capitolo in formato Markdown
        modello_utilizzato: (Opzionale) Il modello AI utilizzato per generare il contenuto
    """
    try:
        # Carica il corso
        corso = carica_corso(corso_id)
        if not corso:
            return None
        
        # Trova il capitolo nella scaletta
        capitolo = None
        for cap in corso['scaletta']['capitoli']:
            if cap['id'] == capitolo_id:
                capitolo = cap
                break
                
        if not capitolo:
            return None
        
        # Crea una connessione al database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Salva il modello utilizzato nel capitolo, se fornito
        if modello_utilizzato:
            capitolo['modello_utilizzato'] = modello_utilizzato
            # Aggiorna la scaletta con questa nuova informazione
            c.execute("UPDATE corsi SET scaletta = ? WHERE id = ?", 
                    (json.dumps(corso['scaletta']), corso_id))
            
        # Aggiorna o inserisce record nella tabella contenuti_capitoli
        ora = datetime.now().isoformat()
        id_contenuto = f"{corso_id}_{capitolo_id}"
        
        # Controlla se esiste già un record per questo capitolo
        c.execute(
            "SELECT id FROM contenuti_capitoli WHERE corso_id = ? AND capitolo_id = ?",
            (corso_id, capitolo_id)
        )
        
        if c.fetchone():
            # Aggiorna il record esistente
            c.execute(
                """UPDATE contenuti_capitoli 
                   SET contenuto = ?, generato = 1, ultimo_aggiornamento = ? 
                   WHERE corso_id = ? AND capitolo_id = ?""",
                (contenuto, ora, corso_id, capitolo_id)
            )
        else:
            # Inserisce un nuovo record
            c.execute(
                """INSERT INTO contenuti_capitoli 
                   (id, corso_id, capitolo_id, contenuto, generato, ultimo_aggiornamento)
                   VALUES (?, ?, ?, ?, 1, ?)""",
                (id_contenuto, corso_id, capitolo_id, contenuto, ora)
            )
            
        # Commit delle modifiche
        conn.commit()
        conn.close()
            
        # Crea la directory per i contenuti se non esiste
        os.makedirs(f"app/data/contenuti/{corso_id}", exist_ok=True)
        
        # Salva il contenuto in un file
        with open(f"app/data/contenuti/{corso_id}/{capitolo_id}.md", "w", encoding="utf-8") as f:
            f.write(contenuto)
        
        return True
    except Exception as e:
        print(f"Errore nel salvataggio del contenuto: {str(e)}")
        return None

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

def carica_contenuti_corso(corso_id: str) -> Dict[str, str]:
    """Carica tutti i contenuti generati per un corso."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT capitolo_id, contenuto FROM contenuti_capitoli WHERE corso_id = ? AND generato = 1",
        (corso_id,)
    )
    
    contenuti = {}
    for row in cursor.fetchall():
        contenuti[row['capitolo_id']] = row['contenuto']
    
    conn.close()
    return contenuti

def lista_corsi() -> List[Dict[str, Any]]:
    """Restituisce una lista di tutti i corsi."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, parametri, creato, ultimo_aggiornamento, completato FROM corsi ORDER BY creato DESC")
    
    corsi = []
    for row in cursor.fetchall():
        corso = dict(row)
        corso['parametri'] = json.loads(corso['parametri'])
        corsi.append(corso)
    
    conn.close()
    return corsi

def elimina_corso(corso_id: str) -> bool:
    """Elimina un corso e tutti i suoi contenuti associati dal database.
    
    Args:
        corso_id: L'ID del corso da eliminare
        
    Returns:
        bool: True se l'eliminazione è avvenuta con successo, False altrimenti
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Inizia una transazione
        conn.execute("BEGIN TRANSACTION")
        
        # Elimina prima i contenuti dei capitoli associati
        cursor.execute("DELETE FROM contenuti_capitoli WHERE corso_id = ?", (corso_id,))
        
        # Elimina il corso
        cursor.execute("DELETE FROM corsi WHERE id = ?", (corso_id,))
        
        # Commit della transazione
        conn.commit()
        return True
    except Exception as e:
        # Rollback in caso di errore
        conn.rollback()
        print(f"Errore nell'eliminazione del corso: {e}")
        return False
    finally:
        conn.close() 