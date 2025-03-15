from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ParametriCorso(BaseModel):
    """Parametri iniziali del corso forniti dall'utente."""
    titolo: str
    descrizione: str
    pubblico_target: str
    livello_complessita: str
    tono: str
    requisiti: Optional[str] = None
    stile_scrittura: Optional[str] = None

class CapitoloBase(BaseModel):
    """Classe base per i capitoli e sottocapitoli."""
    id: str
    titolo: str
    ordine: int

class Sottocapitolo(CapitoloBase):
    """Rappresenta un sottocapitolo del corso."""
    contenuto: Optional[str] = None
    generato: bool = False
    ultimo_aggiornamento: Optional[datetime] = None

class Capitolo(CapitoloBase):
    """Rappresenta un capitolo del corso."""
    sottocapitoli: List[Sottocapitolo] = []
    contenuto: Optional[str] = None
    generato: bool = False
    ultimo_aggiornamento: Optional[datetime] = None

class Scaletta(BaseModel):
    """Rappresenta la scaletta completa del corso."""
    capitoli: List[Capitolo] = []
    creata: datetime = datetime.now()
    ultimo_aggiornamento: Optional[datetime] = None

class Corso(BaseModel):
    """Rappresenta un corso completo."""
    id: str
    parametri: ParametriCorso
    scaletta: Optional[Scaletta] = None
    creato: datetime = datetime.now()
    ultimo_aggiornamento: Optional[datetime] = None
    completato: bool = False 