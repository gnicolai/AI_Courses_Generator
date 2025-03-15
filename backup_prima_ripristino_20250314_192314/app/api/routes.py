from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

from app.models.corso import ParametriCorso
from app.api.controllers import (
    crea_corso,
    genera_scaletta_corso,
    genera_contenuto_capitolo,
    modifica_scaletta,
    modifica_contenuto_capitolo,
    esporta_corso
)

# Definizione dei modelli di richiesta/risposta API
class CorsoResponse(BaseModel):
    success: bool
    corso_id: Optional[str] = None
    message: str

class ScalettaResponse(BaseModel):
    success: bool
    scaletta: Optional[Dict[str, Any]] = None
    scaletta_text: Optional[str] = None
    parsing_error: Optional[str] = None
    message: str

class ContenutoResponse(BaseModel):
    success: bool
    contenuto: Optional[str] = None
    message: str

class ScalettaData(BaseModel):
    capitoli: List[Dict[str, Any]]

class ContenutoData(BaseModel):
    contenuto: str

class EsportaResponse(BaseModel):
    success: bool
    message: str
    content: Optional[str] = None
    filename: Optional[str] = None
    url: Optional[str] = None

router = APIRouter(prefix="/api", tags=["API"])

@router.post("/corsi", response_model=CorsoResponse)
async def crea_nuovo_corso(parametri: ParametriCorso):
    """Crea un nuovo corso."""
    return await crea_corso(parametri.dict())

@router.post("/corsi/{corso_id}/scaletta", response_model=ScalettaResponse)
async def genera_scaletta(corso_id: str):
    """Genera la scaletta per un corso esistente."""
    return await genera_scaletta_corso(corso_id)

@router.post("/corso/{corso_id}/capitolo/{capitolo_id}/genera-contenuto")
async def api_genera_contenuto(corso_id: str, capitolo_id: str) -> Dict[str, Any]:
    """API per generare il contenuto di un capitolo."""
    result = await genera_contenuto_capitolo(corso_id, capitolo_id)
    
    # Assicuriamoci di includere il modello utilizzato nella risposta JSON
    if "modello_utilizzato" in result:
        return {
            "success": result.get("success", False),
            "contenuto": result.get("contenuto", ""),
            "message": result.get("message", ""),
            "modello_utilizzato": result.get("modello_utilizzato", "non specificato")
        }
    
    return result

@router.put("/corsi/{corso_id}/scaletta/edit", response_model=ScalettaResponse)
async def modifica_scaletta_corso(corso_id: str, dati: ScalettaData):
    """
    Aggiorna la scaletta di un corso con i dati forniti.
    """
    risultato = await modifica_scaletta(corso_id, dati.dict())
    
    if risultato["success"]:
        return {
            "success": True,
            "scaletta": risultato["scaletta"],
            "message": risultato["message"],
            "parsing_error": None,
            "scaletta_text": None
        }
    else:
        return {
            "success": False,
            "scaletta": None,
            "message": risultato["message"],
            "parsing_error": None,
            "scaletta_text": None
        }

@router.put("/corsi/{corso_id}/capitoli/{capitolo_id}/contenuto/edit", response_model=ContenutoResponse)
async def modifica_contenuto(corso_id: str, capitolo_id: str, dati: ContenutoData):
    """
    Aggiorna il contenuto di un capitolo specifico.
    """
    risultato = await modifica_contenuto_capitolo(corso_id, capitolo_id, dati.contenuto)
    
    return {
        "success": risultato["success"],
        "contenuto": risultato.get("contenuto"),
        "message": risultato["message"]
    }

@router.get("/corsi/{corso_id}/esporta", response_model=EsportaResponse)
async def esporta_corso_endpoint(corso_id: str, formato: str):
    """
    Esporta il corso nel formato specificato.
    """
    risultato = await esporta_corso(corso_id, formato)
    
    # Aggiungiamo l'URL per il download se l'esportazione è avvenuta con successo
    if risultato["success"] and "content" in risultato:
        return risultato
    else:
        return {
            "success": risultato["success"],
            "message": risultato["message"],
            "content": None,
            "filename": None,
            "url": None
        } 