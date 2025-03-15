import httpx
import json
import os
import random
import asyncio
import re
from typing import Dict, List, Any, Optional, Callable
import logging
from app.config import load_config, save_config, get_config_value
from app.api.model_support import prepare_messages, prepare_api_parameters, get_model_config

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def standardizza_markdown(testo: str, provider: str = "generic") -> str:
    """
    Standardizza la formattazione Markdown per garantire coerenza tra provider diversi.
    
    Args:
        testo: Il testo Markdown da standardizzare
        provider: Il provider AI che ha generato il testo ('openai', 'deepseek', o 'generic')
        
    Returns:
        Testo Markdown standardizzato
    """
    if not testo:
        return testo
    
    # Rimuovi eventuali tag di linguaggio markdown all'inizio del documento
    testo = re.sub(r'^```markdown\s*\n', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'^```\s*markdown\s*\n', '', testo, flags=re.IGNORECASE)
    
    # Rimuovi tag di chiusura backtick senza apertura
    testo = re.sub(r'^\s*```\s*$', '', testo, flags=re.MULTILINE)
    
    # Correzioni generali per tutti i provider
    # Rimuovi spazi bianchi multipli alla fine delle righe
    testo = re.sub(r' +$', '', testo, flags=re.MULTILINE)
    
    # Assicura che ci sia un solo newline tra paragrafi (non più di due)
    testo = re.sub(r'\n{3,}', '\n\n', testo)
    
    # Assicura che tutti i titoli abbiano uno spazio dopo #
    testo = re.sub(r'(#{1,6})([^ #])', r'\1 \2', testo)
    
    # Assicura che ci sia una riga vuota prima dei titoli (eccetto il primo)
    testo = re.sub(r'([^\n])\n(#{1,6} )', r'\1\n\n\2', testo)
    
    # Assicura che ci sia una riga vuota dopo i titoli
    testo = re.sub(r'(#{1,6} [^\n]+)\n([^#\n])', r'\1\n\n\2', testo)
    
    # Correzioni specifiche per DeepSeek
    if provider.lower() == "deepseek":
        # Migliora la formattazione degli elenchi puntati 
        testo = re.sub(r'\n\s*[-*+]\s', '\n- ', testo)
        
        # Aggiungi spazio dopo gli elenchi numerati
        testo = re.sub(r'\n\s*(\d+)\.\s*', r'\n\1. ', testo)
        
        # Assicura che gli elementi di un elenco siano separati da una sola riga
        testo = re.sub(r'(- [^\n]+)\n\n(- )', r'\1\n\2', testo)
        
        # Migliora la formattazione del grassetto e del corsivo
        testo = re.sub(r'(?<!\*)\*([^\s*][^*]*[^\s*])\*(?!\*)', r'*\1*', testo)  # Corsivo
        testo = re.sub(r'(?<!\*)\*\*([^\s*][^*]*[^\s*])\*\*(?!\*)', r'**\1**', testo)  # Grassetto
        
        # Aggiungi linee vuote prima delle citazioni
        testo = re.sub(r'([^\n])\n(> )', r'\1\n\n\2', testo)
    
    # Correzioni specifiche per OpenAI
    elif provider.lower() == "openai":
        # OpenAI tende a utilizzare strutture di titoli più complesse
        # Normalizziamo per avere consistenza con DeepSeek
        pass  # Aggiungi regole specifiche se necessario
    
    # Assicura che il documento inizi con un titolo principale
    if not testo.lstrip().startswith('# '):
        lines = testo.split('\n', 1)
        if len(lines) > 0 and lines[0].strip() and not lines[0].startswith('#'):
            testo = '# ' + lines[0] + ('\n' + lines[1] if len(lines) > 1 else '')
    
    # Assicura che il documento termini con una nuova riga
    if not testo.endswith('\n'):
        testo += '\n'
    
    return testo

async def retry_with_exponential_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True
) -> Any:
    """
    Esegue una funzione con retry e backoff esponenziale.
    
    Args:
        func: La funzione asincrona da eseguire
        max_retries: Numero massimo di tentativi
        initial_backoff: Tempo di attesa iniziale in secondi
        backoff_factor: Fattore di crescita del tempo di attesa
        jitter: Se aggiungere una componente casuale al tempo di attesa
        
    Returns:
        Il risultato della funzione o solleva l'ultima eccezione
    """
    retries = 0
    backoff = initial_backoff
    
    while True:
        try:
            return await func()
        except (httpx.TimeoutException, 
                httpx.ReadTimeout, 
                httpx.ConnectTimeout, 
                httpx.RemoteProtocolError) as e:
            retries += 1
            if retries > max_retries:
                logger.warning(f"Numero massimo di tentativi raggiunto ({max_retries}). Ultimo errore: {str(e)}")
                raise
            
            # Calcola il tempo di attesa con jitter se richiesto
            wait_time = backoff
            if jitter:
                wait_time = backoff * (0.5 + random.random())
                
            logger.info(f"Tentativo {retries}/{max_retries} fallito: {str(e)}. Riprovo tra {wait_time:.2f} secondi...")
            await asyncio.sleep(wait_time)
            
            # Aggiorna il backoff per il prossimo tentativo
            backoff *= backoff_factor

class AIClient:
    """Client base per le API di intelligenza artificiale."""
    
    def __init__(self, api_key: str, base_url: str, provider: str):
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
        logger.info(f"Inizializzato client {provider} con URL: {base_url}")
    
    async def genera_scaletta_corso(self, parametri: Dict[str, Any]) -> Dict[str, Any]:
        """Metodo astratto per la generazione della scaletta."""
        raise NotImplementedError("Questo metodo deve essere implementato nelle classi derivate")
    
    async def genera_contenuto_capitolo(self, parametri_corso: Dict[str, Any], 
                                     scaletta: Dict[str, Any], 
                                     capitolo_id: str,
                                     contenuto_precedente: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Metodo astratto per la generazione del contenuto di un capitolo."""
        raise NotImplementedError("Questo metodo deve essere implementato nelle classi derivate")

class DeepSeekClient(AIClient):
    """Client per l'API DeepSeek."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        super().__init__(api_key, base_url, "deepseek")
        # Carica la configurazione per il modello DeepSeek
        config = load_config()
        self.model = config.get("deepseek_model", "deepseek-chat")
        logger.info(f"Inizializzando DeepSeekClient con modello: {self.model}")
    
    async def genera_scaletta_corso(self, parametri: Dict[str, Any]) -> Dict[str, Any]:
        """Genera la scaletta di un corso usando l'API DeepSeek."""
        try:
            logger.info(f"Generazione scaletta corso con DeepSeek: {parametri['titolo']}")
            
            # Determina la complessità della scaletta in base al livello
            livello = parametri['livello_complessita'].lower()
            if livello == 'base' or livello == 'principiante':
                num_capitoli = "3-4"
                num_sottocapitoli = "2-3"
                profondita = "semplice e introduttiva"
            elif livello == 'intermedio':
                num_capitoli = "4-6"
                num_sottocapitoli = "3-5"
                profondita = "moderatamente dettagliata"
            else:  # avanzato o esperto
                num_capitoli = "6-10"
                num_sottocapitoli = "4-8"
                profondita = "molto approfondita e completa, con concetti avanzati, esempi pratici estesi, casi di studio e applicazioni reali"
            
            # Costruisci il prompt per la generazione della scaletta
            template_prompt = """
            Sei un assistente esperto nella creazione di corsi formativi. 
            
            Devi generare la scaletta dettagliata per un corso con i seguenti parametri:
            
            Titolo: {titolo}
            Descrizione: {descrizione}
            Pubblico: {pubblico_target}
            Livello di complessità: {livello_complessita}
            Tono: {tono}
            
            {requisiti_specifici}
            
            Genera una scaletta in formato JSON con la seguente struttura:
            {{
              "titolo": "Titolo del corso",
              "descrizione": "Breve descrizione del corso",
              "durata_stimata": "XX ore",
              "capitoli": [
                {{
                  "id": "cap1",
                  "titolo": "Titolo Capitolo 1",
                  "descrizione": "Descrizione dettagliata del capitolo",
                  "sottoargomenti": [
                    {{
                      "titolo": "Titolo Sottoargomento 1.1",
                      "punti_chiave": ["punto 1", "punto 2", "punto 3"]
                    }},
                    // altri sottoargomenti
                  ]
                }},
                // altri capitoli
              ]
            }}
            
            Crea una struttura logica e progressiva che faciliti l'apprendimento.
            
            ISTRUZIONI IMPORTANTI:
            - Se sono stati specificati requisiti o risorse particolari, assicurati di INCLUDERLI ESPLICITAMENTE nella scaletta. 
            - Se sono menzionate risorse, tecnologie, metodi o concetti specifici nei requisiti, dedicagli capitoli o sottocapitoli appropriati.
            - Ogni risorsa o concetto nei requisiti deve essere visibilmente incluso nella scaletta finale.
            
            Poiché questo corso è di livello {livello_complessita}, deve essere {profondita}.
            - Includi {num_capitoli} capitoli con {num_sottocapitoli} sottoargomenti ciascuno, mantenendo un'elevata coerenza tematica.
            - Assicurati che i sottoargomenti coprano adeguatamente tutti gli aspetti del tema, dagli aspetti teorici alle applicazioni pratiche.
            - I punti chiave devono essere specifici e dettagliati, non generici.
            - Per un corso avanzato sul prompting, copri a fondo aspetti come: tecniche avanzate, pattern di prompt, strategie per diversi modelli e task, ottimizzazione, debugging, casi d'uso specialistici, personalizzazione, risoluzione di problemi comuni, e valutazione dell'efficacia.
            
            Ogni capitolo deve avere un ID univoco (cap1, cap2, ecc.). Assicurati che il JSON sia ben formato e valido.
            """
            
            # Sostituisci i valori nel template
            requisiti = parametri.get('requisiti_specifici', '')
            if requisiti:
                requisiti = f"""REQUISITI SPECIFICI DA INCORPORARE NELLA SCALETTA:
-------------------------------------------------
{requisiti}
-------------------------------------------------"""
            
            stile_scrittura = parametri.get('stile_scrittura', '')
            if stile_scrittura:
                requisiti += f"""

STILE DI SCRITTURA DA ADOTTARE:
-------------------------------------------------
{stile_scrittura}
-------------------------------------------------"""
            
            prompt = template_prompt.format(
                titolo=parametri['titolo'],
                descrizione=parametri['descrizione'],
                pubblico_target=parametri['pubblico_target'],
                livello_complessita=parametri['livello_complessita'],
                tono=parametri['tono'],
                requisiti_specifici=requisiti,
                profondita=profondita,
                num_capitoli=num_capitoli,
                num_sottocapitoli=num_sottocapitoli
            )
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 4000
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    # Definiamo una funzione interna per effettuare la richiesta API con retry
                    async def make_api_request():
                        return await client.post(
                            f"{self.base_url}/v1/completions",
                            headers=headers,
                            json=payload,
                            timeout=120.0  # Aumentiamo il timeout a 2 minuti
                        )
                    
                    # Esegui la richiesta con retry automatico
                    response = await retry_with_exponential_backoff(
                        make_api_request,
                        max_retries=3,
                        initial_backoff=1.0,
                        backoff_factor=2.0
                    )
                except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
                    logger.error(f"Errore di connessione persistente all'API DeepSeek dopo diversi tentativi: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore di connessione persistente all'API: {str(e)}. Riprova più tardi."
                    }
                except httpx.RequestError as e:
                    logger.error(f"Errore di rete nella richiesta all'API DeepSeek: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore di rete durante la richiesta all'API: {str(e)}"
                    }
                
                try:
                    response_data = response.json()
                except Exception as e:
                    logger.error(f"Errore nel parsing della risposta JSON: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore nel parsing della risposta: {str(e)}"
                    }
                
                if response.status_code != 200:
                    error_msg = "Errore sconosciuto"
                    try:
                        error_msg = response_data.get('error', {}).get('message', 'Errore sconosciuto')
                    except Exception:
                        pass
                        
                    logger.error(f"Errore API DeepSeek: {response.status_code} - {error_msg}")
                    return {
                        "success": False,
                        "message": f"Errore nell'API DeepSeek: {error_msg}"
                    }
                
                try:
                    # Estrai la scaletta dal messaggio di risposta
                    content = response_data['choices'][0]['text']
                    
                    # Cerca il JSON nella risposta
                    import re
                    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
                    
                    if json_match:
                        scaletta_json = json_match.group(1)
                    else:
                        # Prova a trovare un oggetto JSON nella risposta
                        json_match = re.search(r'({[\s\S]*})', content)
                        if json_match:
                            scaletta_json = json_match.group(1)
                        else:
                            # Se non troviamo un JSON, riportiamo un errore
                            logger.error(f"Impossibile trovare un oggetto JSON nella risposta: {content[:200]}...")
                            return {
                                "success": False,
                                "message": "La risposta dell'API non contiene un oggetto JSON valido"
                            }
                    
                    # Pulisce il JSON da eventuali commenti o caratteri non validi
                    # Rimuove i commenti con // alla fine delle righe
                    scaletta_json = re.sub(r'//.*$', '', scaletta_json, flags=re.MULTILINE)
                    
                    try:
                        scaletta = json.loads(scaletta_json)
                    except json.JSONDecodeError as e:
                        logger.error(f"Errore nel parsing JSON: {str(e)}")
                        logger.error(f"JSON con errore: {scaletta_json[:200]}...")
                        
                        # Tentativo più aggressivo di pulizia del JSON
                        try:
                            # Rimuove i commenti con //
                            clean_json = re.sub(r'//.*?(\n|$)', '\n', scaletta_json)
                            # Rimuove le virgole trailing prima delle parentesi chiuse
                            clean_json = re.sub(r',\s*}', '}', clean_json)
                            clean_json = re.sub(r',\s*]', ']', clean_json)
                            
                            scaletta = json.loads(clean_json)
                            logger.info("Recupero JSON riuscito dopo pulizia aggressiva")
                        except Exception as inner_e:
                            logger.error(f"Errore nel secondo tentativo di parsing JSON: {str(inner_e)}")
                            return {
                                "success": False,
                                "message": f"Errore nel parsing del JSON: {str(e)}"
                            }
                    
                    # Verifica che la scaletta contenga i campi minimi necessari
                    if not all(k in scaletta for k in ['titolo', 'descrizione', 'capitoli']):
                        logger.error(f"JSON mancante di campi obbligatori: {scaletta.keys()}")
                        return {
                            "success": False,
                            "message": "La scaletta generata è incompleta o malformata"
                        }
                    
                    return {
                        "success": True,
                        "scaletta": scaletta
                    }
                except Exception as e:
                    logger.exception(f"Errore imprevisto durante l'elaborazione della risposta: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore durante la generazione della scaletta: {str(e)}"
                    }
                
        except Exception as e:
            logger.error(f"Errore durante la generazione della scaletta: {str(e)}")
            return {
                "success": False,
                "message": f"Errore durante la generazione della scaletta: {str(e)}"
            }
    
    async def genera_contenuto_capitolo(self, parametri_corso: Dict[str, Any], 
                                     scaletta: Dict[str, Any], 
                                     capitolo_id: str,
                                     contenuto_precedente: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Genera il contenuto di un capitolo specifico usando l'API DeepSeek."""
        try:
            logger.info(f"Generazione contenuto capitolo con DeepSeek: {capitolo_id}")
            
            # Trova il capitolo da generare
            capitolo = None
            for cap in scaletta['capitoli']:
                if cap['id'] == capitolo_id:
                    capitolo = cap
                    break
            
            if not capitolo:
                return {
                    "success": False,
                    "message": f"Capitolo con ID {capitolo_id} non trovato"
                }
            
            # Costruisci il prompt per la generazione del contenuto
            template_prompt = """
            Sei un assistente esperto nella creazione di contenuti didattici di alta qualità.
            
            Devi generare il contenuto dettagliato per un capitolo di un corso con i seguenti parametri:
            
            CORSO:
            Titolo: {titolo_corso}
            Descrizione: {descrizione_corso}
            Pubblico: {pubblico_target}
            Livello di complessità: {livello_complessita}
            Tono: {tono}
            
            {requisiti_specifici}
            
            CAPITOLO DA GENERARE:
            Titolo: {titolo_capitolo}
            Descrizione: {descrizione_capitolo}
            
            SOTTOARGOMENTI:
            {sottoargomenti}
            
            {contenuto_precedente}
            
            Genera il contenuto completo del capitolo in formato Markdown. 
            Includi un'introduzione generale al capitolo, e poi sviluppa in dettaglio ogni sottoargomento.
            Per ogni sottoargomento, crea una sezione con un titolo di secondo livello (##), seguito da un testo
            esplicativo dettagliato che copra tutti i punti chiave elencati.
            
            Il contenuto deve essere approfondito, accurato ed educativo, mantenendo il livello di complessità e il tono richiesti.
            Includi esempi pratici, analogie dove appropriato, e una conclusione che riassuma i concetti chiave del capitolo.
            
            LINEE GUIDA STILISTICHE IMPORTANTI:
            - Utilizza un linguaggio naturale e scorrevole, come se stessi spiegando i concetti a voce
            - Evita elenchi puntati eccessivi e frasi troppo brevi o schematiche
            - Preferisci uno stile discorsivo e coinvolgente, con paragrafi ben sviluppati
            - Usa gli elenchi puntati solo quando strettamente necessario, preferendo spiegazioni narrative
            - Collega i concetti tra loro con transizioni fluide
            - Includi esempi concreti e scenari reali per illustrare i concetti
            - Usa analogie e metafore per rendere più comprensibili i concetti complessi
            
            FORMATTAZIONE MARKDOWN:
            - Usa un titolo principale (#) per il titolo del capitolo
            - Usa titoli di secondo livello (##) per i sottoargomenti principali
            - Usa titoli di terzo livello (###) per suddividere i sottoargomenti
            - Inserisci spazi tra i paragrafi per migliorare la leggibilità
            - Usa il grassetto (**testo**) per enfatizzare concetti importanti
            - Usa il corsivo (*testo*) per termini specifici o citazioni
            - Usa le citazioni (> testo) per esempi o definizioni importanti
            - Utilizza una sezione di conclusione alla fine del capitolo
            """
            
            # Formatta i sottoargomenti
            sottoargomenti_str = ""
            
            # Gestisci sia il vecchio formato (sottoargomenti) che il nuovo (sottocapitoli)
            sotto_items = capitolo.get('sottoargomenti', capitolo.get('sottocapitoli', []))
            
            for i, sotto in enumerate(sotto_items):
                sottoargomenti_str += f"Sottoargomento {i+1}: {sotto['titolo']}\n"
                # Gestisci sia i punti_chiave che descrizioni più generiche
                if 'punti_chiave' in sotto:
                    sottoargomenti_str += "Punti chiave:\n"
                    for punto in sotto['punti_chiave']:
                        sottoargomenti_str += f"- {punto}\n"
                elif 'descrizione' in sotto:
                    sottoargomenti_str += f"Descrizione: {sotto['descrizione']}\n"
                sottoargomenti_str += "\n"
            
            # Formatta eventuali contenuti precedenti
            contenuto_precedente_str = ""
            if contenuto_precedente and len(contenuto_precedente) > 0:
                contenuto_precedente_str = "CONTENUTO DEI CAPITOLI PRECEDENTI (per mantenere la coerenza):\n"
                for prev_cap in contenuto_precedente:
                    contenuto_precedente_str += f"Capitolo: {prev_cap['titolo']}\n"
                    contenuto_precedente_str += f"Riassunto: {prev_cap['riassunto']}\n\n"
            
            # Sostituisci i valori nel template
            requisiti = parametri_corso.get('requisiti_specifici', '')
            if requisiti:
                requisiti = f"Requisiti specifici: {requisiti}"
            
            stile_scrittura = parametri_corso.get('stile_scrittura', '')
            if stile_scrittura:
                requisiti += f"\nStile di scrittura: {stile_scrittura}"
            
            prompt = template_prompt.format(
                titolo_corso=parametri_corso['titolo'],
                descrizione_corso=parametri_corso['descrizione'],
                pubblico_target=parametri_corso['pubblico_target'],
                livello_complessita=parametri_corso['livello_complessita'],
                tono=parametri_corso['tono'],
                requisiti_specifici=requisiti,
                titolo_capitolo=capitolo['titolo'],
                descrizione_capitolo=capitolo['descrizione'],
                sottoargomenti=sottoargomenti_str,
                contenuto_precedente=contenuto_precedente_str
            )
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 4000
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    # Definiamo una funzione interna per effettuare la richiesta API con retry
                    async def make_api_request():
                        return await client.post(
                            f"{self.base_url}/v1/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=180.0  # 3 minuti
                        )
                    
                    # Esegui la richiesta con retry automatico
                    response = await retry_with_exponential_backoff(
                        make_api_request,
                        max_retries=3,
                        initial_backoff=1.0,
                        backoff_factor=2.0
                    )
                except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
                    logger.error(f"Errore di connessione persistente all'API DeepSeek dopo diversi tentativi: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore di connessione persistente all'API: {str(e)}. Riprova più tardi."
                    }
                except httpx.RequestError as e:
                    logger.error(f"Errore di rete nella richiesta all'API DeepSeek: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore di rete durante la richiesta all'API: {str(e)}"
                    }
                
                try:
                    response_data = response.json()
                except Exception as e:
                    logger.error(f"Errore nel parsing della risposta JSON: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore nel parsing della risposta: {str(e)}"
                    }
                
                if response.status_code != 200:
                    error_msg = "Errore sconosciuto"
                    try:
                        error_msg = response_data.get('error', {}).get('message', 'Errore sconosciuto')
                    except Exception:
                        pass
                        
                    logger.error(f"Errore API DeepSeek: {response.status_code} - {error_msg}")
                    return {
                        "success": False,
                        "message": f"Errore nell'API DeepSeek: {error_msg}"
                    }
                
                try:
                    # Estrai il contenuto generato dall'API
                    contenuto_generato = response_data['choices'][0]['message']['content']
                    
                    # Applica la standardizzazione al markdown generato
                    contenuto_generato = standardizza_markdown(contenuto_generato, "deepseek")
                    
                    logger.info(f"Contenuto generato per il capitolo {capitolo_id}")
                    
                    return {
                        "success": True,
                        "contenuto": contenuto_generato,
                        "modello_utilizzato": self.model
                    }
                except Exception as e:
                    logger.exception(f"Errore imprevisto durante l'elaborazione della risposta: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore durante la generazione del contenuto: {str(e)}"
                    }
                
        except Exception as e:
            logger.error(f"Errore durante la generazione del contenuto: {str(e)}")
            return {
                "success": False,
                "message": f"Errore durante la generazione del contenuto: {str(e)}"
            }

    async def genera_contenuto_espanso(self, corso_id: str, capitolo_id: str, contenuto_originale: str, prompt_espansione: str) -> Dict[str, Any]:
        """
        Genera una versione espansa del contenuto di un capitolo usando l'API DeepSeek.
        
        Args:
            corso_id: ID del corso
            capitolo_id: ID del capitolo
            contenuto_originale: Contenuto originale da espandere
            prompt_espansione: Prompt con le istruzioni per l'espansione
            
        Returns:
            Dizionario con il risultato dell'operazione
        """
        logger.info(f"Generazione contenuto espanso per capitolo {capitolo_id} del corso {corso_id} con DeepSeek")
        
        # Funzione per fare la richiesta API con gestione dei tentativi
        async def make_api_request_with_retries(max_retries=3, backoff_factor=2):
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt_espansione}
                ],
                "temperature": 0.7,
                "max_tokens": 4000
            }
            
            for attempt in range(max_retries):
                try:
                    # Aumenta il timeout per le richieste di espansione
                    async with httpx.AsyncClient(timeout=300.0) as client:  # Timeout esteso a 5 minuti per l'espansione
                        logger.info(f"Tentativo {attempt+1}/{max_retries} di invio richiesta a DeepSeek per espansione del capitolo {capitolo_id}")
                        
                        response = await client.post(
                            f"{self.base_url}/v1/chat/completions",
                            json=payload,
                            headers=headers
                        )
                        
                        try:
                            response_data = response.json()
                        except Exception as e:
                            logger.error(f"Errore nel parsing della risposta JSON: {str(e)}")
                            if attempt == max_retries - 1:
                                return {
                                    "success": False,
                                    "message": f"Errore nel parsing della risposta: {str(e)}"
                                }
                            # Se non è l'ultimo tentativo, continuiamo con il backoff
                            continue
                        
                        if response.status_code != 200:
                            error_msg = "Errore sconosciuto"
                            try:
                                error_msg = response_data.get('error', {}).get('message', 'Errore sconosciuto')
                            except Exception:
                                pass
                                
                            logger.error(f"Errore API DeepSeek: {response.status_code} - {error_msg}")
                            if attempt == max_retries - 1:
                                return {
                                    "success": False,
                                    "message": f"Errore nell'API DeepSeek: {error_msg}"
                                }
                            # Se non è l'ultimo tentativo, continuiamo con il backoff
                            continue
                        
                        # Estrai il contenuto dal messaggio di risposta
                        contenuto_espanso = response_data['choices'][0]['message']['content']
                        
                        # Verifica lunghezza (deve essere maggiore dell'originale)
                        if len(contenuto_espanso) <= len(contenuto_originale):
                            logger.warning(f"Il contenuto espanso non è più lungo dell'originale, riprovo con istruzioni più esplicite")
                            
                            if attempt == max_retries - 1:
                                # Se è l'ultimo tentativo, restituisci comunque il risultato
                                # Standardizza il markdown prima di restituirlo
                                contenuto_standardizzato = standardizza_markdown(contenuto_espanso, "deepseek")
                                
                                return {
                                    "success": True,
                                    "contenuto": contenuto_standardizzato,
                                    "lunghezza_originale": len(contenuto_originale),
                                    "lunghezza_espansa": len(contenuto_standardizzato),
                                    "modello_utilizzato": self.model
                                }
                            
                            # Riprova con un prompt più esplicito
                            prompt_retry = prompt_espansione + "\n\nIMPORTANTE: Il testo espanso DEVE essere significativamente più lungo dell'originale. È fondamentale aggiungere esempi, spiegazioni più dettagliate e ampliamenti sostanziali ad ogni concetto."
                            
                            payload["messages"] = [{"role": "user", "content": prompt_retry}]
                            # Se non è l'ultimo tentativo, continuiamo con il backoff e un prompt più esplicito
                            continue
                        
                        # Standardizza il markdown prima di restituirlo
                        contenuto_standardizzato = standardizza_markdown(contenuto_espanso, "deepseek")
                        
                        return {
                            "success": True,
                            "contenuto": contenuto_standardizzato,
                            "lunghezza_originale": len(contenuto_originale),
                            "lunghezza_espansa": len(contenuto_standardizzato),
                            "modello_utilizzato": self.model
                        }
                
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ReadError, httpx.ConnectError) as e:
                    # Gestione specifica degli errori di timeout e connessione
                    logger.error(f"Errore di connessione/timeout durante l'espansione del capitolo {capitolo_id}: {str(e)}")
                    if attempt == max_retries - 1:
                        return {
                            "success": False,
                            "message": f"Errore di connessione durante l'espansione del contenuto: {str(e)}"
                        }
                    # Attendiamo prima di riprovare con backoff esponenziale
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.info(f"Attendo {wait_time} secondi prima di riprovare...")
                    await asyncio.sleep(wait_time)
                
                except Exception as e:
                    # Gestione generale delle eccezioni
                    logger.error(f"Eccezione generica durante l'espansione del capitolo {capitolo_id}: {str(e)}")
                    if attempt == max_retries - 1:
                        return {
                            "success": False,
                            "message": f"Errore durante l'espansione del contenuto: {str(e)}"
                        }
                    # Attendiamo prima di riprovare con backoff esponenziale
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.info(f"Attendo {wait_time} secondi prima di riprovare...")
                    await asyncio.sleep(wait_time)
        
        try:
            # Esegui la funzione con gestione dei tentativi
            result = await make_api_request_with_retries()
            return result
        except Exception as e:
            logger.error(f"Errore durante l'espansione del contenuto: {str(e)}")
            return {
                "success": False,
                "message": f"Errore durante l'espansione del contenuto: {str(e)}"
            }

    async def verifica_chiave_api(self) -> Dict[str, Any]:
        """
        Verifica la validità della chiave API DeepSeek effettuando una richiesta di test.
        
        Returns:
            Dizionario con il risultato della verifica
        """
        logger.info("Verifica della validità della chiave API DeepSeek")
        
        try:
            # Effettua una richiesta semplice per verificare la chiave API
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                # Usa una richiesta minima per verificare l'autenticazione
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": "Semplice test di connessione. Rispondi solo 'OK'."}
                    ],
                    "max_tokens": 10
                }
                
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    logger.info("Chiave API DeepSeek valida")
                    return {
                        "success": True,
                        "message": "Chiave API verificata con successo"
                    }
                elif response.status_code == 401 or response.status_code == 403:
                    logger.error(f"Chiave API DeepSeek non valida. Errore {response.status_code}")
                    return {
                        "success": False,
                        "message": "La chiave API non è valida o è scaduta"
                    }
                else:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', {}).get('message', f"Errore API {response.status_code}")
                        logger.error(f"Errore nel test della chiave API: {error_msg}")
                        return {
                            "success": False,
                            "message": f"Errore nell'API: {error_msg}"
                        }
                    except Exception as e:
                        logger.error(f"Errore generico nella verifica della chiave API: {str(e)}")
                        return {
                            "success": False,
                            "message": f"Errore nella verifica della chiave API: {str(e)}"
                        }
        except Exception as e:
            logger.error(f"Eccezione durante la verifica della chiave API: {str(e)}")
            return {
                "success": False,
                "message": f"Errore di connessione durante la verifica: {str(e)}"
            }

class OpenAIClient(AIClient):
    """Client per le API di OpenAI."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com"):
        """Inizializza il client OpenAI."""
        super().__init__(api_key, base_url, "openai")
        
        # Configurazione del modello da utilizzare (configurabile)
        config = load_config()
        # Imposta o1-preview come modello predefinito per massima qualità
        model_setting = config.get("openai_model", "o1-preview")  # Default a o1-preview per massima qualità
        
        # Forza l'uso di o1-preview come prima scelta quando la configurazione è o1
        if model_setting == "o1":
            logger.info("Modello 'o1' selezionato. Proveremo prima 'o1-preview' poiché offre la massima qualità.")
            self.model = "o1-preview"
        else:
            self.model = model_setting
        
        logger.info(f"OpenAI client configurato per utilizzare il modello: {self.model}")
        
        # Limitazione ai soli modelli di alta qualità per garantire output eccellenti
        # Nessun fallback a modelli di qualità inferiore come gpt-3.5
        self.fallback_models = [
            "o1-preview", "o1", "gpt-4o-1", "gpt-4o",   # Modelli di massima qualità
            "gpt-4-turbo", "gpt-4"                      # Modelli gpt-4 di alta qualità
        ]
        
        # Log all models we're going to try
        logger.info(f"Modelli di alta qualità disponibili: {', '.join(self.fallback_models)}")
        
        # Verifica i modelli disponibili all'avvio
        self.available_models = []
        self._check_models_sync()
    
    def _check_models_sync(self):
        """Verifica i modelli disponibili in modo sincrono (solo all'avvio)."""
        import requests  # Usiamo requests per la chiamata sincrona
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                models_data = response.json()
                available_models = [model["id"] for model in models_data.get("data", [])]
                self.available_models = available_models
                
                logger.info(f"Modelli OpenAI disponibili: {', '.join(available_models[:10])}...")
                logger.info(f"Totale modelli disponibili: {len(available_models)}")
                
                # Verifica quali modelli di alta qualità sono disponibili
                premium_models = [m for m in self.fallback_models if m in available_models]
                
                if premium_models:
                    # Filtra solo i modelli di alta qualità
                    logger.info(f"Modelli di alta qualità disponibili nell'API: {', '.join(premium_models)}")
                    self.fallback_models = premium_models
                    
                    # IMPORTANTE: Forza l'uso di o1-preview se disponibile
                    if "o1-preview" in premium_models:
                        self.model = "o1-preview"
                        logger.info("Forzato utilizzo di o1-preview come modello principale (massima qualità)")
                        # Aggiorna la configurazione salvata
                        config = load_config()
                        config["openai_model"] = "o1-preview"
                        save_config(config)
                    elif "o1" in premium_models:
                        self.model = "o1"
                        logger.info("Forzato utilizzo di o1 come modello principale (massima qualità)")
                        # Aggiorna la configurazione salvata
                        config = load_config()
                        config["openai_model"] = "o1"
                        save_config(config)
                else:
                    # Avvisa che nessun modello di alta qualità è disponibile
                    logger.warning("ATTENZIONE: Nessun modello di alta qualità è disponibile nel tuo account!")
                    logger.warning("Si consiglia di aggiornare la sottoscrizione OpenAI per accedere ai modelli premium.")
        except Exception as e:
            logger.error(f"Errore durante la verifica dei modelli disponibili: {str(e)}")
            # Continua con i modelli predefiniti
        
    async def check_available_models(self) -> List[str]:
        """Verifica quali modelli sono disponibili per questo progetto OpenAI."""
        if self.available_models:
            return self.available_models
            
        logger.info("Verificando i modelli disponibili nel progetto OpenAI...")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    models_data = response.json()
                    available_model_ids = [model["id"] for model in models_data.get("data", [])]
                    self.available_models = available_model_ids
                    
                    # Logga i modelli disponibili
                    logger.info(f"Modelli disponibili nel progetto: {', '.join(available_model_ids)}")
                    
                    # Aggiorna i modelli di fallback per includere solo quelli disponibili
                    self.fallback_models = [model for model in self.fallback_models if model in available_model_ids]
                    
                    if not self.fallback_models and available_model_ids:
                        # Se nessuno dei nostri modelli è disponibile ma ce ne sono altri,
                        # aggiungiamo quelli disponibili alla lista
                        self.fallback_models.extend(available_model_ids)
                        
                    logger.info(f"Modelli di fallback effettivamente disponibili: {', '.join(self.fallback_models)}")
                    
                    return available_model_ids
                else:
                    logger.error(f"Errore nell'ottenere la lista dei modelli: {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Eccezione durante la verifica dei modelli disponibili: {str(e)}")
            return []
            
    async def _call_api_with_fallback(self, prompt: str, capitolo_id: str) -> Dict[str, Any]:
        """Chiama l'API OpenAI con fallback automatico a modelli alternativi se necessario."""
        # Prima di tutto, verifica quali modelli sono disponibili
        available_models = await self.check_available_models()
        
        if not self.fallback_models:
            return {
                "success": False,
                "message": "Nessun modello di alta qualità disponibile. Per garantire risultati eccellenti, " +
                           "è necessario aggiornare la sottoscrizione OpenAI per accedere ai modelli premium (o1-preview, gpt-4o, ecc)."
            }
        
        # PRIORITÀ ASSOLUTA: Riorganizza la lista di fallback per dare priorità a o1-preview se disponibile
        if "o1-preview" in self.fallback_models:
            # Riorganizza la lista per mettere o1-preview come primo elemento
            self.fallback_models = ["o1-preview"] + [m for m in self.fallback_models if m != "o1-preview"]
            logger.info(f"Lista modelli riorganizzata per dare priorità a o1-preview: {', '.join(self.fallback_models)}")
            
            # Forza anche il modello corrente a o1-preview
            self.model = "o1-preview"
            # Aggiorna la configurazione
            config = load_config()
            config["openai_model"] = "o1-preview"
            save_config(config)
        elif "o1" in self.fallback_models:
            # Fallback a o1 se o1-preview non è disponibile
            self.fallback_models = ["o1"] + [m for m in self.fallback_models if m != "o1"]
            logger.info(f"Lista modelli riorganizzata per dare priorità a o1: {', '.join(self.fallback_models)}")
            self.model = "o1"
            # Aggiorna la configurazione
            config = load_config()
            config["openai_model"] = "o1"
            save_config(config)
            
        # Determina l'indice del modello corrente nella lista di fallback
        try:
            current_index = self.fallback_models.index(self.model)
        except ValueError:
            # Se il modello configurato non è nella lista dei modelli di alta qualità disponibili,
            # imposta il modello al primo della lista
            current_index = 0
            if self.fallback_models:
                self.model = self.fallback_models[current_index]
                logger.info(f"Modello configurato non disponibile o non di alta qualità, usando: {self.model}")
            else:
                return {
                    "success": False,
                    "message": "Nessun modello di alta qualità disponibile. L'applicazione richiede modelli premium " +
                               "come o1-preview o gpt-4o per garantire risultati eccellenti."
                }
        
        # Implementiamo un vero meccanismo di fallback, provando modelli in sequenza
        max_attempts = min(5, len(self.fallback_models))  # Limita a 5 tentativi
        attempt = 0
        
        # Lista completa per tentativi di emergenza, inclusi alcuni modelli di backup
        emergency_models = ["o3-mini", "gpt-4-vision-preview"]
        
        while attempt < max_attempts:
            # Usa il modello corrente dalla lista di fallback
            current_model = self.fallback_models[current_index]
            attempt += 1
            
            # Configurazione del payload in base al modello
            tokens_limit = 8000 if current_model.startswith("o1") else 4000
            logger.info(f"Tentativo #{attempt} con modello di alta qualità '{current_model}', limite token={tokens_limit}")
            
            # Adattamento del formato dei messaggi in base al modello
            messages = []
            
            # Alcuni modelli come o1-preview potrebbero non supportare il ruolo 'system'
            # Verifichiamo il modello e adattiamo il formato dei messaggi
            if current_model.startswith("o1-preview") or current_model.startswith("o1-mini"):
                # Per modelli che non supportano 'system', includiamo le istruzioni nel messaggio utente
                system_instruction = "Sei un esperto nella creazione di contenuti didattici di alta qualità.\n\n"
                messages = [
                    {"role": "user", "content": system_instruction + prompt}
                ]
                logger.info(f"Usando formato semplificato dei messaggi per il modello {current_model}")
            else:
                # Per modelli che supportano 'system', usiamo il formato standard
                messages = [
                    {"role": "system", "content": "Sei un esperto nella creazione di contenuti didattici di alta qualità."},
                    {"role": "user", "content": prompt}
                ]
            
            payload = {
                "model": current_model,
                "messages": messages,
            }
            
            # Alcuni modelli come o1-preview usano max_completion_tokens invece di max_tokens
            if current_model.startswith("o1-preview") or current_model.startswith("o1-mini"):
                payload["max_completion_tokens"] = tokens_limit
                logger.info(f"Usando 'max_completion_tokens' per il modello {current_model}")
                # o1-preview non supporta valori personalizzati per temperature
                logger.info(f"Rimuovendo 'temperature' per il modello {current_model} (usa solo valore predefinito)")
                payload.pop("temperature", None)  # Rimuove temperature se presente
            else:
                payload["max_tokens"] = tokens_limit
                payload["temperature"] = 0.7
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            try:
                async with httpx.AsyncClient() as client:
                    # Definisci una funzione interna per la chiamata API con retry
                    async def make_api_request():
                        return await client.post(
                            f"{self.base_url}/v1/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=180.0  # 3 minuti
                        )
                    
                    # Esegui la richiesta con retry automatici
                    logger.info(f"Invio richiesta a OpenAI per modello {current_model} con retry automatici")
                    response = await retry_with_exponential_backoff(
                        make_api_request,
                        max_retries=2,  # Solo 2 tentativi per modello, poi si prova un altro modello
                        initial_backoff=1.0,
                        backoff_factor=2.0
                    )
                    
                    # Processa la risposta
                    response_data = response.json()
                    
                    if response.status_code == 200:
                        # Richiesta riuscita, aggiorna il modello corrente se diverso
                        if self.model != current_model:
                            logger.info(f"Modello di alta qualità '{current_model}' funzionante. Aggiornando la configurazione...")
                            self.model = current_model
                            # Aggiorna la configurazione per le prossime chiamate
                            config = load_config()
                            config["openai_model"] = self.model
                            save_config(config)
                        
                        # Estrai il contenuto dal messaggio di risposta
                        content = response_data['choices'][0]['message']['content']
                        
                        logger.info(f"Contenuto generato con successo usando il modello '{current_model}'")
                        
                        # Restituisci il risultato
                        return {
                            "success": True,
                            "contenuto": content,
                            "modello_utilizzato": current_model
                        }
                    else:
                        # API ha restituito un errore, prova con il prossimo modello
                        error_msg = response_data.get('error', {}).get('message', 'Errore sconosciuto')
                        logger.error(f"Errore API OpenAI con modello '{current_model}': {response_data}")
                        logger.warning(f"Tentativo #{attempt} fallito: {error_msg}")
            except httpx.TimeoutException:
                logger.warning(f"Timeout nella richiesta con modello '{current_model}'. Provando un altro modello...")
            except httpx.ReadTimeout:
                logger.warning(f"Read timeout con modello '{current_model}' - il server ha impiegato troppo tempo per rispondere")
            except httpx.ConnectTimeout:
                logger.warning(f"Connect timeout con modello '{current_model}' - impossibile stabilire una connessione")
            except httpx.RemoteProtocolError:
                logger.warning(f"Errore di protocollo remoto con modello '{current_model}' - la connessione è stata chiusa inaspettatamente")
            except httpx.RequestError as e:
                logger.warning(f"Errore di rete con modello '{current_model}': {str(e)}")
            except Exception as e:
                logger.warning(f"Errore generico con modello '{current_model}': {str(e)}")
            
            # Se siamo qui, c'è stato un errore. Prova il prossimo modello
            current_index = (current_index + 1) % len(self.fallback_models)
            continue
        
        # Se tutti i modelli di alta qualità falliscono, proviamo con o3-mini come ultima risorsa
        logger.warning("Tutti i modelli di alta qualità hanno fallito. Provo con o3-mini come ultima risorsa...")
        
        for emergency_model in emergency_models:
            if emergency_model in self.available_models:
                logger.info(f"Tentativo di emergenza con modello {emergency_model}")
                
                emergency_payload = {
                    "model": emergency_model,
                    "messages": [
                        {"role": "system", "content": "Sei un esperto nella creazione di contenuti didattici di alta qualità."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4000
                }
                
                if emergency_model == "o3-mini":
                    emergency_payload["reasoning_effort"] = "high"
                
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{self.base_url}/v1/chat/completions",
                            headers=headers,
                            json=emergency_payload,
                            timeout=120.0
                        )
                        
                        if response.status_code == 200:
                            response_data = response.json()
                            content = response_data['choices'][0]['message']['content']
                            logger.warning(f"Utilizzato modello di emergenza {emergency_model}. Si consiglia di verificare la qualità del contenuto.")
                            return {
                                "success": True,
                                "contenuto": content,
                                "warning": "Contenuto generato con modello di emergenza. La qualità potrebbe essere inferiore.",
                                "modello_utilizzato": emergency_model
                            }
                except Exception as e:
                    logger.error(f"Anche il tentativo di emergenza con {emergency_model} è fallito: {str(e)}")
                    continue
        
        # Se siamo arrivati qui, tutti i tentativi sono falliti
        return {
            "success": False,
            "message": f"Impossibile generare contenuto con modelli di alta qualità. Si consiglia di verificare la sottoscrizione OpenAI per accedere ai modelli premium (o1-preview, gpt-4o)."
        }

    async def genera_scaletta_corso(self, parametri: Dict[str, Any]) -> Dict[str, Any]:
        """Genera la scaletta di un corso usando l'API OpenAI."""
        try:
            logger.info(f"Generazione scaletta corso con OpenAI: {parametri['titolo']}")
            
            # Determina la complessità della scaletta in base al livello
            livello = parametri['livello_complessita'].lower()
            if livello == 'base' or livello == 'principiante':
                num_capitoli = "3-4"
                num_sottocapitoli = "2-3"
                profondita = "semplice e introduttiva"
            elif livello == 'intermedio':
                num_capitoli = "4-6"
                num_sottocapitoli = "3-5"
                profondita = "moderatamente dettagliata"
            else:  # avanzato o esperto
                num_capitoli = "6-10"
                num_sottocapitoli = "4-8"
                profondita = "molto approfondita e completa, con concetti avanzati, esempi pratici estesi, casi di studio e applicazioni reali"
            
            # Costruisci il prompt per la generazione della scaletta
            template_prompt = """
            Sei un assistente esperto nella creazione di corsi formativi. 
            
            Devi generare la scaletta dettagliata per un corso con i seguenti parametri:
            
            Titolo: {titolo}
            Descrizione: {descrizione}
            Pubblico: {pubblico_target}
            Livello di complessità: {livello_complessita}
            Tono: {tono}
            
            {requisiti_specifici}
            
            Genera una scaletta in formato JSON con la seguente struttura:
            {{
              "titolo": "Titolo del corso",
              "descrizione": "Breve descrizione del corso",
              "durata_stimata": "XX ore",
              "capitoli": [
                {{
                  "id": "cap1",
                  "titolo": "Titolo Capitolo 1",
                  "descrizione": "Descrizione dettagliata del capitolo",
                  "sottoargomenti": [
                    {{
                      "titolo": "Titolo Sottoargomento 1.1",
                      "punti_chiave": ["punto 1", "punto 2", "punto 3"]
                    }},
                    // altri sottoargomenti
                  ]
                }},
                // altri capitoli
              ]
            }}
            
            Crea una struttura logica e progressiva che faciliti l'apprendimento.
            
            ISTRUZIONI IMPORTANTI:
            - Se sono stati specificati requisiti o risorse particolari, assicurati di INCLUDERLI ESPLICITAMENTE nella scaletta. 
            - Se sono menzionate risorse, tecnologie, metodi o concetti specifici nei requisiti, dedicagli capitoli o sottocapitoli appropriati.
            - Ogni risorsa o concetto nei requisiti deve essere visibilmente incluso nella scaletta finale.
            
            Poiché questo corso è di livello {livello_complessita}, deve essere {profondita}.
            - Includi {num_capitoli} capitoli con {num_sottocapitoli} sottoargomenti ciascuno, mantenendo un'elevata coerenza tematica.
            - Assicurati che i sottoargomenti coprano adeguatamente tutti gli aspetti del tema, dagli aspetti teorici alle applicazioni pratiche.
            - I punti chiave devono essere specifici e dettagliati, non generici.
            - Per un corso avanzato sul prompting, copri a fondo aspetti come: tecniche avanzate, pattern di prompt, strategie per diversi modelli e task, ottimizzazione, debugging, casi d'uso specialistici, personalizzazione, risoluzione di problemi comuni, e valutazione dell'efficacia.
            
            Ogni capitolo deve avere un ID univoco (cap1, cap2, ecc.). Assicurati che il JSON sia ben formato e valido.
            """
            
            # Sostituisci i valori nel template
            requisiti = parametri.get('requisiti_specifici', '')
            if requisiti:
                requisiti = f"""REQUISITI SPECIFICI DA INCORPORARE NELLA SCALETTA:
-------------------------------------------------
{requisiti}
-------------------------------------------------"""
            
            stile_scrittura = parametri.get('stile_scrittura', '')
            if stile_scrittura:
                requisiti += f"""

STILE DI SCRITTURA DA ADOTTARE:
-------------------------------------------------
{stile_scrittura}
-------------------------------------------------"""
            
            prompt = template_prompt.format(
                titolo=parametri['titolo'],
                descrizione=parametri['descrizione'],
                pubblico_target=parametri['pubblico_target'],
                livello_complessita=parametri['livello_complessita'],
                tono=parametri['tono'],
                requisiti_specifici=requisiti,
                profondita=profondita,
                num_capitoli=num_capitoli,
                num_sottocapitoli=num_sottocapitoli
            )
        
            # Usa uno dei modelli disponibili dal nostro sistema di fallback
            model_to_use = self.fallback_models[0] if self.fallback_models else self.model
            logger.info(f"Usando modello {model_to_use} per generare la scaletta")
            
            # Prepara i messaggi appropriati per il modello
            system_content = "Sei un esperto nella creazione di corsi formativi."
            messages = prepare_messages(model_to_use, system_content, prompt)
            
            # Prepara i parametri API appropriati per il modello
            payload = prepare_api_parameters(model_to_use, messages)
            
            # Log dettagliato dei parametri utilizzati
            logger.info(f"Parametri API per {model_to_use}: "
                      f"supports_system={get_model_config(model_to_use)['supports_system_role']}, "
                      f"max_tokens_param={get_model_config(model_to_use)['max_tokens_param']}, "
                      f"tokens={get_model_config(model_to_use)['default_max_tokens']}")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    # Definiamo una funzione interna per effettuare la richiesta API con retry
                    async def make_api_request():
                        return await client.post(
                            f"{self.base_url}/v1/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=180.0  # 3 minuti
                        )
                    
                    # Esegui la richiesta con retry automatico
                    response = await retry_with_exponential_backoff(
                        make_api_request,
                        max_retries=3,
                        initial_backoff=1.0,
                        backoff_factor=2.0
                    )
                except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
                    logger.error(f"Errore di connessione persistente all'API OpenAI dopo diversi tentativi: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore di connessione persistente all'API: {str(e)}. Riprova più tardi."
                    }
                except httpx.RequestError as e:
                    logger.error(f"Errore di rete nella richiesta all'API OpenAI: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore di rete durante la richiesta all'API: {str(e)}"
                    }
                
                try:
                    response_data = response.json()
                except Exception as e:
                    logger.error(f"Errore nel parsing della risposta JSON: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore nel parsing della risposta: {str(e)}"
                    }
                
                if response.status_code != 200:
                    error_msg = "Errore sconosciuto"
                    try:
                        error_msg = response_data.get('error', {}).get('message', 'Errore sconosciuto')
                    except Exception:
                        pass
                        
                    logger.error(f"Errore API OpenAI: {response.status_code} - {error_msg}")
                    return {
                        "success": False,
                        "message": f"Errore nell'API OpenAI: {error_msg}"
                    }
                
                try:
                    # Estrai la scaletta dal messaggio di risposta
                    content = response_data['choices'][0]['message']['content']
                    
                    # Cerca il JSON nella risposta
                    import re
                    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        # Prova a estrarre il JSON senza il formato markdown
                        json_match = re.search(r'({[\s\S]*})', content)
                        if json_match:
                            json_str = json_match.group(1)
                        else:
                            json_str = content
                    
                    # Pulisce il JSON da eventuali commenti o caratteri non validi
                    # Rimuove i commenti con // alla fine delle righe
                    json_str = re.sub(r'//.*$', '', json_str, flags=re.MULTILINE)
                    
                    try:
                        scaletta = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.error(f"Errore nel parsing JSON: {str(e)}")
                        logger.error(f"JSON con errore: {json_str[:200]}...")
                        
                        # Tentativo più aggressivo di pulizia del JSON
                        try:
                            # Rimuove i commenti con //
                            clean_json = re.sub(r'//.*?(\n|$)', '\n', json_str)
                            # Rimuove le virgole trailing prima delle parentesi chiuse
                            clean_json = re.sub(r',\s*}', '}', clean_json)
                            clean_json = re.sub(r',\s*]', ']', clean_json)
                            
                            scaletta = json.loads(clean_json)
                            logger.info("Recupero JSON riuscito dopo pulizia aggressiva")
                        except Exception as inner_e:
                            logger.error(f"Errore nel secondo tentativo di parsing JSON: {str(inner_e)}")
                            return {
                                "success": False,
                                "message": f"Errore nel parsing del JSON: {str(e)}",
                                "content": content
                            }
                    
                    # Verifica che la scaletta contenga i campi minimi necessari
                    if not all(k in scaletta for k in ['titolo', 'descrizione', 'capitoli']):
                        logger.error(f"JSON mancante di campi obbligatori: {scaletta.keys()}")
                        return {
                            "success": False,
                            "message": "La scaletta generata è incompleta o malformata"
                        }
                    
                    return {
                        "success": True,
                        "scaletta": scaletta
                    }
                    
                except Exception as e:
                    logger.exception(f"Errore imprevisto durante l'elaborazione della risposta: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Errore durante la generazione della scaletta: {str(e)}"
                    }
                
        except Exception as e:
            logger.error(f"Errore durante la generazione della scaletta: {str(e)}")
            return {
                "success": False,
                "message": f"Errore durante la generazione della scaletta: {str(e)}"
            }
            
    async def genera_contenuto_capitolo(self, parametri_corso: Dict[str, Any], 
                                     scaletta: Dict[str, Any], 
                                     capitolo_id: str,
                                     contenuto_precedente: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Genera il contenuto di un capitolo specifico usando l'API OpenAI."""
        try:
            logger.info(f"Generazione contenuto capitolo con OpenAI: {capitolo_id}")
            
            # Trova il capitolo da generare
            capitolo = None
            for cap in scaletta['capitoli']:
                if cap['id'] == capitolo_id:
                    capitolo = cap
                    break
            
            if not capitolo:
                return {
                    "success": False,
                    "message": f"Capitolo con ID {capitolo_id} non trovato"
                }
            
            # Costruisci il prompt per la generazione del contenuto
            template_prompt = """
            Sei un assistente esperto nella creazione di contenuti didattici di alta qualità.
            
            Devi generare il contenuto dettagliato per un capitolo di un corso con i seguenti parametri:
            
            CORSO:
            Titolo: {titolo_corso}
            Descrizione: {descrizione_corso}
            Pubblico: {pubblico_target}
            Livello di complessità: {livello_complessita}
            Tono: {tono}
            
            {requisiti_specifici}
            
            CAPITOLO DA GENERARE:
            Titolo: {titolo_capitolo}
            Descrizione: {descrizione_capitolo}
            
            SOTTOARGOMENTI:
            {sottoargomenti}
            
            {contenuto_precedente}
            
            Genera il contenuto completo del capitolo in formato Markdown. 
            Includi un'introduzione generale al capitolo, e poi sviluppa in dettaglio ogni sottoargomento.
            Per ogni sottoargomento, crea una sezione con un titolo di secondo livello (##), seguito da un testo
            esplicativo dettagliato che copra tutti i punti chiave elencati.
            
            Il contenuto deve essere approfondito, accurato ed educativo, mantenendo il livello di complessità e il tono richiesti.
            Includi esempi pratici, analogie dove appropriato, e una conclusione che riassuma i concetti chiave del capitolo.
            
            LINEE GUIDA STILISTICHE IMPORTANTI:
            - Utilizza un linguaggio naturale e scorrevole, come se stessi spiegando i concetti a voce
            - Evita elenchi puntati eccessivi e frasi troppo brevi o schematiche
            - Preferisci uno stile discorsivo e coinvolgente, con paragrafi ben sviluppati
            - Usa gli elenchi puntati solo quando strettamente necessario, preferendo spiegazioni narrative
            - Collega i concetti tra loro con transizioni fluide
            - Includi esempi concreti e scenari reali per illustrare i concetti
            - Usa analogie e metafore per rendere più comprensibili i concetti complessi
            
            FORMATTAZIONE MARKDOWN:
            - Usa un titolo principale (#) per il titolo del capitolo
            - Usa titoli di secondo livello (##) per i sottoargomenti principali
            - Usa titoli di terzo livello (###) per suddividere i sottoargomenti
            - Inserisci spazi tra i paragrafi per migliorare la leggibilità
            - Usa il grassetto (**testo**) per enfatizzare concetti importanti
            - Usa il corsivo (*testo*) per termini specifici o citazioni
            - Usa le citazioni (> testo) per esempi o definizioni importanti
            - Utilizza una sezione di conclusione alla fine del capitolo
            """
            
            # Formatta i sottoargomenti
            sottoargomenti_str = ""
            
            # Gestisci sia il vecchio formato (sottoargomenti) che il nuovo (sottocapitoli)
            sotto_items = capitolo.get('sottoargomenti', capitolo.get('sottocapitoli', []))
            
            for i, sotto in enumerate(sotto_items):
                sottoargomenti_str += f"Sottoargomento {i+1}: {sotto['titolo']}\n"
                # Gestisci sia i punti_chiave che descrizioni più generiche
                if 'punti_chiave' in sotto:
                    sottoargomenti_str += "Punti chiave:\n"
                    for punto in sotto['punti_chiave']:
                        sottoargomenti_str += f"- {punto}\n"
                elif 'descrizione' in sotto:
                    sottoargomenti_str += f"Descrizione: {sotto['descrizione']}\n"
                sottoargomenti_str += "\n"
            
            # Formatta eventuali contenuti precedenti
            contenuto_precedente_str = ""
            if contenuto_precedente and len(contenuto_precedente) > 0:
                contenuto_precedente_str = "CONTENUTO DEI CAPITOLI PRECEDENTI (per mantenere la coerenza):\n"
                for prev_cap in contenuto_precedente:
                    contenuto_precedente_str += f"Capitolo: {prev_cap['titolo']}\n"
                    contenuto_precedente_str += f"Riassunto: {prev_cap['riassunto']}\n\n"
            
            # Sostituisci i valori nel template
            requisiti = parametri_corso.get('requisiti_specifici', '')
            if requisiti:
                requisiti = f"Requisiti specifici: {requisiti}"
            
            stile_scrittura = parametri_corso.get('stile_scrittura', '')
            if stile_scrittura:
                requisiti += f"\nStile di scrittura: {stile_scrittura}"
            
            prompt = template_prompt.format(
                titolo_corso=parametri_corso['titolo'],
                descrizione_corso=parametri_corso['descrizione'],
                pubblico_target=parametri_corso['pubblico_target'],
                livello_complessita=parametri_corso['livello_complessita'],
                tono=parametri_corso['tono'],
                requisiti_specifici=requisiti,
                titolo_capitolo=capitolo['titolo'],
                descrizione_capitolo=capitolo['descrizione'],
                sottoargomenti=sottoargomenti_str,
                contenuto_precedente=contenuto_precedente_str
            )
            
            # Utilizza il metodo _call_api_with_fallback per gestire automaticamente la selezione del modello
            # e il fallback in caso di errori
            result = await self._call_api_with_fallback(prompt, capitolo_id)
            
            # Se il risultato è un successo, standardizziamo il markdown prima di restituirlo
            if result["success"] and "contenuto" in result:
                result["contenuto"] = standardizza_markdown(result["contenuto"], "openai")
                
            # Restituisci il risultato
            return result
                
        except Exception as e:
            logger.error(f"Errore durante la generazione del contenuto: {str(e)}")
            return {
                "success": False,
                "message": f"Errore durante la generazione del contenuto: {str(e)}"
            }

    async def genera_contenuto_espanso(self, corso_id: str, capitolo_id: str, contenuto_originale: str, prompt_espansione: str) -> Dict[str, Any]:
        """
        Genera una versione espansa del contenuto di un capitolo usando l'API DeepSeek.
        
        Args:
            corso_id: ID del corso
            capitolo_id: ID del capitolo
            contenuto_originale: Contenuto originale da espandere
            prompt_espansione: Prompt con le istruzioni per l'espansione
            
        Returns:
            Dizionario con il risultato dell'operazione
        """
        logger.info(f"Generazione contenuto espanso per capitolo {capitolo_id} del corso {corso_id} con DeepSeek")
        
        # Funzione per fare la richiesta API con gestione dei tentativi
        async def make_api_request_with_retries(max_retries=3, backoff_factor=2):
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt_espansione}
                ],
                "temperature": 0.7,
                "max_tokens": 4000
            }
            
            for attempt in range(max_retries):
                try:
                    # Aumenta il timeout per le richieste di espansione
                    async with httpx.AsyncClient(timeout=300.0) as client:  # Timeout esteso a 5 minuti per l'espansione
                        logger.info(f"Tentativo {attempt+1}/{max_retries} di invio richiesta a DeepSeek per espansione del capitolo {capitolo_id}")
                        
                        response = await client.post(
                            f"{self.base_url}/v1/chat/completions",
                            json=payload,
                            headers=headers
                        )
                        
                        try:
                            response_data = response.json()
                        except Exception as e:
                            logger.error(f"Errore nel parsing della risposta JSON: {str(e)}")
                            if attempt == max_retries - 1:
                                return {
                                    "success": False,
                                    "message": f"Errore nel parsing della risposta: {str(e)}"
                                }
                            # Se non è l'ultimo tentativo, continuiamo con il backoff
                            continue
                        
                        if response.status_code != 200:
                            error_msg = "Errore sconosciuto"
                            try:
                                error_msg = response_data.get('error', {}).get('message', 'Errore sconosciuto')
                            except Exception:
                                pass
                                
                            logger.error(f"Errore API DeepSeek: {response.status_code} - {error_msg}")
                            if attempt == max_retries - 1:
                                return {
                                    "success": False,
                                    "message": f"Errore nell'API DeepSeek: {error_msg}"
                                }
                            # Se non è l'ultimo tentativo, continuiamo con il backoff
                            continue
                        
                        # Estrai il contenuto dal messaggio di risposta
                        contenuto_espanso = response_data['choices'][0]['message']['content']
                        
                        # Verifica lunghezza (deve essere maggiore dell'originale)
                        if len(contenuto_espanso) <= len(contenuto_originale):
                            logger.warning(f"Il contenuto espanso non è più lungo dell'originale, riprovo con istruzioni più esplicite")
                            
                            if attempt == max_retries - 1:
                                # Se è l'ultimo tentativo, restituisci comunque il risultato
                                # Standardizza il markdown prima di restituirlo
                                contenuto_standardizzato = standardizza_markdown(contenuto_espanso, "deepseek")
                                
                                return {
                                    "success": True,
                                    "contenuto": contenuto_standardizzato,
                                    "lunghezza_originale": len(contenuto_originale),
                                    "lunghezza_espansa": len(contenuto_standardizzato),
                                    "modello_utilizzato": self.model
                                }
                            
                            # Riprova con un prompt più esplicito
                            prompt_retry = prompt_espansione + "\n\nIMPORTANTE: Il testo espanso DEVE essere significativamente più lungo dell'originale. È fondamentale aggiungere esempi, spiegazioni più dettagliate e ampliamenti sostanziali ad ogni concetto."
                            
                            payload["messages"] = [{"role": "user", "content": prompt_retry}]
                            # Se non è l'ultimo tentativo, continuiamo con il backoff e un prompt più esplicito
                            continue
                        
                        # Standardizza il markdown prima di restituirlo
                        contenuto_standardizzato = standardizza_markdown(contenuto_espanso, "deepseek")
                        
                        return {
                            "success": True,
                            "contenuto": contenuto_standardizzato,
                            "lunghezza_originale": len(contenuto_originale),
                            "lunghezza_espansa": len(contenuto_standardizzato),
                            "modello_utilizzato": self.model
                        }
                
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ReadError, httpx.ConnectError) as e:
                    # Gestione specifica degli errori di timeout e connessione
                    logger.error(f"Errore di connessione/timeout durante l'espansione del capitolo {capitolo_id}: {str(e)}")
                    if attempt == max_retries - 1:
                        return {
                            "success": False,
                            "message": f"Errore di connessione durante l'espansione del contenuto: {str(e)}"
                        }
                    # Attendiamo prima di riprovare con backoff esponenziale
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.info(f"Attendo {wait_time} secondi prima di riprovare...")
                    await asyncio.sleep(wait_time)
                
                except Exception as e:
                    # Gestione generale delle eccezioni
                    logger.error(f"Eccezione generica durante l'espansione del capitolo {capitolo_id}: {str(e)}")
                    if attempt == max_retries - 1:
                        return {
                            "success": False,
                            "message": f"Errore durante l'espansione del contenuto: {str(e)}"
                        }
                    # Attendiamo prima di riprovare con backoff esponenziale
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.info(f"Attendo {wait_time} secondi prima di riprovare...")
                    await asyncio.sleep(wait_time)
        
        try:
            # Esegui la funzione con gestione dei tentativi
            result = await make_api_request_with_retries()
            return result
        except Exception as e:
            logger.error(f"Errore durante l'espansione del contenuto: {str(e)}")
            return {
                "success": False,
                "message": f"Errore durante l'espansione del contenuto: {str(e)}"
            }

    async def verifica_chiave_api(self) -> Dict[str, Any]:
        """
        Verifica la validità della chiave API effettuando una richiesta di test.
        
        Returns:
            Dizionario con il risultato della verifica
        """
        logger.info("Verifica della validità della chiave API")
        
        try:
            # Effettua una richiesta semplice per verificare la chiave API
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}"
                }
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=headers
                )
                
                if response.status_code == 200:
                    logger.info("Chiave API valida")
                    
                    # Verifica l'accesso ai modelli di alta qualità
                    try:
                        modelli_data = response.json()
                        modelli_disponibili = [model["id"] for model in modelli_data.get("data", [])]
                        
                        # Modelli di alta qualità che vogliamo verificare
                        modelli_alta_qualita = ["o1-preview", "o1", "gpt-4o", "gpt-4-turbo"]
                        modelli_disponibili_alta_qualita = [m for m in modelli_disponibili if any(m.startswith(prefix) for prefix in modelli_alta_qualita)]
                        
                        if modelli_disponibili_alta_qualita:
                            logger.info(f"Account ha accesso ai seguenti modelli di alta qualità: {', '.join(modelli_disponibili_alta_qualita)}")
                            return {
                                "success": True,
                                "message": f"Chiave API valida. Modelli di alta qualità disponibili: {', '.join(modelli_disponibili_alta_qualita)}",
                                "modelli_disponibili": modelli_disponibili_alta_qualita
                            }
                        else:
                            logger.warning("Account non ha accesso a modelli di alta qualità")
                            return {
                                "success": False,
                                "message": "La chiave API è valida, ma l'account non ha accesso ai modelli di alta qualità necessari (o1-preview, o1, gpt-4o, gpt-4-turbo). Aggiorna il tuo account OpenAI per accedere a questi modelli."
                            }
                    except Exception as e:
                        logger.error(f"Errore nell'analisi dei modelli disponibili: {str(e)}")
                        return {
                            "success": True,
                            "message": "Chiave API valida, ma non è stato possibile verificare l'accesso ai modelli di alta qualità."
                        }
                elif response.status_code == 403:
                    error_msg = "Chiave API non valida o senza permessi sufficienti"
                    try:
                        error_data = response.json()
                        if "error" in error_data and "message" in error_data["error"]:
                            error_msg = f"Errore di autorizzazione: {error_data['error']['message']}"
                    except:
                        pass
                    
                    logger.error(f"Errore 403 durante la verifica della chiave API: {error_msg}")
                    return {
                        "success": False,
                        "message": error_msg
                    }
                else:
                    logger.error(f"Errore {response.status_code} durante la verifica della chiave API")
                    return {
                        "success": False,
                        "message": f"Errore {response.status_code} durante la verifica della chiave API"
                    }
        except Exception as e:
            logger.error(f"Eccezione durante la verifica della chiave API: {str(e)}")
            return {
                "success": False,
                "message": f"Errore durante la verifica della chiave API: {str(e)}"
            }

    async def get_available_models(self) -> List[str]:
        """
        Ottiene la lista dei modelli disponibili per l'account.
        
        Returns:
            Lista dei modelli disponibili
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}"
                }
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers=headers
                )
                
                if response.status_code == 200:
                    modelli_data = response.json()
                    return [model["id"] for model in modelli_data.get("data", [])]
                else:
                    logger.error(f"Errore {response.status_code} nel recupero dei modelli disponibili")
                    return []
        except Exception as e:
            logger.error(f"Eccezione nel recupero dei modelli disponibili: {str(e)}")
            return []

class MockAIClient(AIClient):
    """Client di mock per test senza API reali."""
    
    def __init__(self):
        super().__init__("mock_key", "mock_url", "mock")
        logger.info("Inizializzato client di mock")
    
    async def genera_scaletta_corso(self, parametri: Dict[str, Any]) -> Dict[str, Any]:
        """Genera una scaletta di corso di esempio."""
        logger.info(f"[MOCK] Generazione scaletta per: {parametri['titolo']}")
        
        # Esempio di scaletta per il test
        scaletta = {
            "titolo": parametri['titolo'],
            "descrizione": parametri['descrizione'],
            "durata_stimata": "10 ore",
            "capitoli": [
                {
                    "id": "cap1",
                    "titolo": "Introduzione al corso",
                    "descrizione": "Panoramica generale dei concetti che verranno trattati",
                    "sottoargomenti": [
                        {
                            "titolo": "Obiettivi del corso",
                            "punti_chiave": ["Comprendere i fondamenti", "Applicare le conoscenze", "Sviluppare competenze pratiche"]
                        },
                        {
                            "titolo": "Metodologia didattica",
                            "punti_chiave": ["Approccio teorico-pratico", "Esercitazioni guidate", "Progetti reali"]
                        }
                    ]
                },
                {
                    "id": "cap2",
                    "titolo": "Concetti fondamentali",
                    "descrizione": "I principi base della materia",
                    "sottoargomenti": [
                        {
                            "titolo": "Terminologia essenziale",
                            "punti_chiave": ["Definizioni chiave", "Contesto storico", "Evoluzione dei concetti"]
                        },
                        {
                            "titolo": "Framework teorico",
                            "punti_chiave": ["Principi fondamentali", "Modelli concettuali", "Applicazioni pratiche"]
                        }
                    ]
                },
                {
                    "id": "cap3",
                    "titolo": "Applicazioni pratiche",
                    "descrizione": "Come applicare le conoscenze in contesti reali",
                    "sottoargomenti": [
                        {
                            "titolo": "Casi di studio",
                            "punti_chiave": ["Analisi di esempi reali", "Lezioni apprese", "Best practices"]
                        },
                        {
                            "titolo": "Esercitazioni guidate",
                            "punti_chiave": ["Step-by-step tutorial", "Risoluzione di problemi comuni", "Tecniche avanzate"]
                        }
                    ]
                }
            ]
        }
        
        return {
            "success": True,
            "scaletta": scaletta
        }
    
    async def genera_contenuto_capitolo(self, parametri_corso: Dict[str, Any], 
                                     scaletta: Dict[str, Any], 
                                     capitolo_id: str,
                                     contenuto_precedente: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Genera contenuto di esempio per un capitolo."""
        logger.info(f"[MOCK] Generazione contenuto per capitolo: {capitolo_id}")
        
        # Trova il capitolo
        capitolo = None
        for cap in scaletta['capitoli']:
            if cap['id'] == capitolo_id:
                capitolo = cap
                break
        
        if not capitolo:
            return {
                "success": False,
                "message": f"Capitolo con ID {capitolo_id} non trovato"
            }
        
        # Genera un contenuto di esempio
        contenuto = f"""# {capitolo['titolo']}

{capitolo['descrizione']}

## Introduzione
Questo capitolo esplora i concetti fondamentali di {capitolo['titolo'].lower()}, fornendo una solida base per comprendere 
i temi trattati nel corso. L'obiettivo è quello di fornire sia le conoscenze teoriche che gli strumenti pratici 
per applicare questi concetti in situazioni reali.

"""
        
        # Aggiungi contenuto per ogni sottoargomento
        sotto_items = capitolo.get('sottoargomenti', capitolo.get('sottocapitoli', []))
        for sotto in sotto_items:
            contenuto += f"## {sotto['titolo']}\n\n"
            contenuto += f"In questa sezione affronteremo {sotto['titolo'].lower()}, un aspetto cruciale per la comprensione complessiva della materia.\n\n"
            
            # Aggiungi paragrafi per ogni punto chiave
            if 'punti_chiave' in sotto:
                for punto in sotto['punti_chiave']:
                    contenuto += f"### {punto}\n\n"
                    contenuto += f"L'aspetto di {punto.lower()} è fondamentale perché consente di sviluppare una comprensione più profonda dell'argomento. "
                    contenuto += "Questo concetto si collega a vari aspetti pratici e teorici che esploreremo in dettaglio.\n\n"
                    contenuto += "Esempio pratico: [Qui verrebbe inserito un esempio reale relativo a questo punto chiave].\n\n"
            elif 'descrizione' in sotto:
                contenuto += f"{sotto['descrizione']}\n\n"
                contenuto += "Esempio pratico: [Qui verrebbe inserito un esempio reale relativo a questo sottoargomento].\n\n"
        
        # Aggiungi una conclusione
        contenuto += "## Conclusione\n\n"
        contenuto += f"In questo capitolo abbiamo esplorato {capitolo['titolo'].lower()}, partendo dai concetti base fino ad arrivare alle applicazioni pratiche. "
        contenuto += "Questi concetti costituiranno le fondamenta per i capitoli successivi, dove approfondiremo ulteriormente gli aspetti più avanzati della materia."
        
        return {
            "success": True,
            "contenuto": contenuto
        }

# Istanza globale del client
deepseek_client = None

def create_ai_client():
    """Crea un'istanza del client AI in base alla configurazione."""
    global deepseek_client
    
    # Carica la configurazione
    config = load_config()
    provider = config.get('ai_provider', 'mock')
    
    if provider == 'deepseek':
        api_key = config.get('deepseek_api_key', '')
        base_url = config.get('deepseek_base_url', 'https://api.deepseek.com')
        
        if not api_key:
            logger.warning("API key DeepSeek non configurata. Utilizzo del client di mock.")
            return MockAIClient()
        
        deepseek_client = DeepSeekClient(api_key=api_key, base_url=base_url)
        logger.info(f"Client DeepSeek creato con modello: {deepseek_client.model}")
        return deepseek_client
    
    elif provider == 'openai':
        api_key = config.get('openai_api_key', '')
        base_url = config.get('openai_base_url', 'https://api.openai.com')
        
        if not api_key:
            logger.warning("API key OpenAI non configurata. Utilizzo del client di mock.")
            return MockAIClient()
        
        return OpenAIClient(api_key=api_key, base_url=base_url)
    
    else:
        # Default a mock se il provider non è riconosciuto
        logger.warning(f"Provider AI '{provider}' non riconosciuto. Utilizzo del client di mock.")
        return MockAIClient()

# Inizializza il client al momento dell'importazione
deepseek_client = create_ai_client() 