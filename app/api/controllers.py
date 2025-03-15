import json
import logging
from typing import Dict, List, Optional, Any
from fastapi import HTTPException

from app.api.ai_client import create_ai_client, standardizza_markdown
from app.models.database import (
    salva_corso,
    salva_scaletta,
    salva_contenuto_capitolo,
    carica_corso,
    carica_contenuti_corso
)

import sqlite3
from pathlib import Path
import asyncio
import os

# Configurazione del logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

DB_PATH = Path("app/data/corsi.db")

# Inizializza il client AI
ai_client = create_ai_client()

# Dizionario per tenere traccia dello stato dell'espansione per ogni corso
# Chiave: corso_id, Valore: dizionario con lo stato dell'espansione
_espansione_stato = {}

async def crea_corso(parametri_corso: Dict[str, Any]) -> Dict[str, Any]:
    """Crea un nuovo corso e lo salva nel database."""
    try:
        corso_id = salva_corso(parametri_corso)
        return {
            "success": True,
            "corso_id": corso_id,
            "message": "Corso creato con successo."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nella creazione del corso: {str(e)}")

async def genera_scaletta_corso(corso_id: str) -> Dict[str, Any]:
    """Genera la scaletta per un corso esistente."""
    try:
        # Carica il corso dal database
        corso = carica_corso(corso_id)
        if not corso:
            raise HTTPException(status_code=404, detail=f"Corso con ID {corso_id} non trovato.")
        
        print(f"Generazione scaletta per corso: {corso_id}")
        print(f"Parametri corso: {corso['parametri']}")
        
        # Ricrea il client AI per assicurarsi di usare l'ultimo provider configurato
        client = create_ai_client()
        
        # Genera la scaletta usando il client AI
        risultato = await client.genera_scaletta_corso(corso['parametri'])
        
        print(f"Risultato dalla chiamata API: {risultato}")
        
        if not risultato.get('success', False):
            print(f"Errore dalla API: {risultato.get('error', 'Errore sconosciuto')}")
            raise HTTPException(
                status_code=500, 
                detail=f"Errore nella generazione della scaletta: {risultato.get('error', 'Errore sconosciuto')}"
            )
        
        # Estrai la scaletta dal risultato
        scaletta_text = risultato['scaletta']
        
        # Estrai il JSON dalla risposta (potrebbe essere inserito in un blocco di codice)
        try:
            # Se scaletta_text è già un dizionario, usalo direttamente
            if isinstance(scaletta_text, dict):
                scaletta = scaletta_text
            else:
                # Cerca un blocco JSON nella risposta
                json_start = scaletta_text.find('```json')
                if json_start != -1:
                    json_start = scaletta_text.find('{', json_start)
                    json_end = scaletta_text.rfind('}') + 1
                    scaletta_json = scaletta_text[json_start:json_end]
                else:
                    # Cerca direttamente un oggetto JSON
                    json_start = scaletta_text.find('{')
                    json_end = scaletta_text.rfind('}') + 1
                    scaletta_json = scaletta_text[json_start:json_end]
                
                scaletta = json.loads(scaletta_json)
        except Exception as e:
            # In caso di errore nel parsing, restituisci il testo completo
            return {
                "success": True,
                "scaletta_text": scaletta_text,
                "parsing_error": str(e),
                "message": "Scaletta generata ma non è stato possibile analizzarla automaticamente."
            }
        
        # Salva la scaletta nel database
        
        # Trasforma i "sottoargomenti" in "sottocapitoli" per compatibilità con il template
        if 'capitoli' in scaletta:
            for capitolo in scaletta['capitoli']:
                if 'sottoargomenti' in capitolo:
                    capitolo['sottocapitoli'] = capitolo.pop('sottoargomenti')
                    
                    # Assicurati che ogni sottocapitolo abbia un ID
                    for i, sottocap in enumerate(capitolo['sottocapitoli']):
                        if 'id' not in sottocap:
                            sottocap['id'] = f"{capitolo['id']}-sub-{i+1}"
                        if 'ordine' not in sottocap:
                            sottocap['ordine'] = i+1
        
        salva_scaletta(corso_id, scaletta)
        
        # Conta il numero di capitoli e sottocapitoli
        num_capitoli = len(scaletta.get('capitoli', []))
        num_sottocapitoli = 0
        for capitolo in scaletta.get('capitoli', []):
            num_sottocapitoli += len(capitolo.get('sottocapitoli', []))
        
        risposta = {
            "success": True,
            "scaletta": scaletta,
            "message": f"Scaletta generata con successo: {num_capitoli} capitoli e {num_sottocapitoli} sottocapitoli."
        }
        
        print(f"RISPOSTA API GENERA SCALETTA: {risposta}")
        
        return risposta
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nella generazione della scaletta: {str(e)}")

async def genera_contenuto_capitolo(corso_id: str, capitolo_id: str) -> Dict[str, Any]:
    """Genera il contenuto di un capitolo specifico."""
    try:
        # Verifichiamo che il corso esista
        corso = carica_corso(corso_id)
        if not corso:
            return {"success": False, "message": "Corso non trovato"}
        
        # Verifichiamo che il corso abbia una scaletta
        if not corso.get('scaletta'):
            return {"success": False, "message": "Il corso non ha una scaletta"}
        
        # Assicuriamoci che la scaletta utilizzi 'sottocapitoli' invece di 'sottoargomenti'
        if 'capitoli' in corso['scaletta']:
            for capitolo in corso['scaletta']['capitoli']:
                if 'sottoargomenti' in capitolo and 'sottocapitoli' not in capitolo:
                    capitolo['sottocapitoli'] = capitolo.pop('sottoargomenti')
                    
                    # Assicurati che ogni sottocapitolo abbia un ID
                    for i, sottocap in enumerate(capitolo['sottocapitoli']):
                        if 'id' not in sottocap:
                            sottocap['id'] = f"{capitolo['id']}-sub-{i+1}"
                        if 'ordine' not in sottocap:
                            sottocap['ordine'] = i+1
        
        # Ricrea il client AI per assicurarsi di usare l'ultimo provider configurato
        client = create_ai_client()
        
        # Carichiamo eventuali contenuti già generati
        contenuti_esistenti = carica_contenuti_corso(corso_id)
        contenuto_precedente = []
        
        # Se non è il primo capitolo, includiamo il contenuto del capitolo precedente come contesto
        capitoli = corso['scaletta']['capitoli']
        cap_index = -1
        for i, cap in enumerate(capitoli):
            if cap['id'] == capitolo_id:
                cap_index = i
                break
        
        # Se abbiamo trovato il capitolo e non è il primo, proviamo a caricare i precedenti
        if cap_index > 0:
            for i in range(cap_index):
                cap_id = capitoli[i]['id']
                if cap_id in contenuti_esistenti:
                    # Creiamo un riassunto del contenuto
                    contenuto_precedente.append({
                        'id': cap_id,
                        'titolo': capitoli[i]['titolo'],
                        'riassunto': _crea_riassunto(contenuti_esistenti[cap_id])
                    })
        
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
        """
        
        # Generiamo il contenuto
        risultato = await client.genera_contenuto_capitolo(
            corso['parametri'], 
            corso['scaletta'],
            capitolo_id,
            contenuto_precedente if contenuto_precedente else None
        )
        
        if not risultato.get('success', False):
            raise HTTPException(
                status_code=500, 
                detail=f"Errore nella generazione del contenuto: {risultato.get('error', 'Errore sconosciuto')}"
            )
        
        # Salva il contenuto nel database
        contenuto = risultato['contenuto']
        modello_utilizzato = risultato.get('modello_utilizzato', None)
        salva_contenuto_capitolo(corso_id, capitolo_id, contenuto, modello_utilizzato)
        
        # Prepara la risposta con l'informazione sul modello utilizzato
        risposta = {
            "success": True,
            "contenuto": contenuto,
            "message": "Contenuto generato e salvato con successo."
        }
        
        # Aggiungi informazioni sul modello utilizzato se disponibile
        if 'modello_utilizzato' in risultato:
            risposta['modello_utilizzato'] = risultato['modello_utilizzato']
        
        # Aggiungi warning se presente
        if 'warning' in risultato:
            risposta['warning'] = risultato['warning']
            
        return risposta
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nella generazione del contenuto: {str(e)}")

def _crea_riassunto(contenuto: str, lunghezza_max: int = 500) -> str:
    """Crea un breve riassunto del contenuto di un capitolo."""
    # Per ora, prendi solo i primi N caratteri
    if len(contenuto) <= lunghezza_max:
        return contenuto
    
    # Tronca al primo punto dopo lunghezza_max/2 caratteri
    punto_index = contenuto.find('.', lunghezza_max // 2)
    if punto_index != -1 and punto_index < lunghezza_max:
        return contenuto[:punto_index + 1]
    
    return contenuto[:lunghezza_max] + "..."

async def modifica_scaletta(corso_id: str, dati_scaletta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggiorna la scaletta di un corso con i dati forniti.
    
    Args:
        corso_id: ID del corso
        dati_scaletta: I dati aggiornati della scaletta
        
    Returns:
        Un dizionario con i risultati dell'operazione
    """
    try:
        # Carichiamo il corso per verificare che esista
        corso = carica_corso(corso_id)
        if not corso:
            return {"success": False, "message": "Corso non trovato"}
        
        # Verifichiamo che i dati della scaletta siano validi
        if "capitoli" not in dati_scaletta:
            return {"success": False, "message": "Dati della scaletta non validi"}
        
        # Formatta la scaletta nel formato corretto per il salvataggio
        scaletta_formattata = {
            "capitoli": []
        }
        
        for i, capitolo in enumerate(dati_scaletta["capitoli"]):
            # Verifichiamo che il capitolo abbia tutti i campi necessari
            if "id" not in capitolo or "titolo" not in capitolo:
                continue
                
            capitolo_formattato = {
                "id": capitolo["id"],
                "titolo": capitolo["titolo"],
                "ordine": i + 1,
                "sottocapitoli": []
            }
            
            # Aggiungiamo la descrizione se presente
            if "descrizione" in capitolo:
                capitolo_formattato["descrizione"] = capitolo["descrizione"]
            
            # Aggiungiamo i sottocapitoli se presenti
            if "sottocapitoli" in capitolo and isinstance(capitolo["sottocapitoli"], list):
                for j, sottocapitolo in enumerate(capitolo["sottocapitoli"]):
                    if "id" not in sottocapitolo or "titolo" not in sottocapitolo:
                        continue
                        
                    sottocapitolo_formattato = {
                        "id": sottocapitolo["id"],
                        "titolo": sottocapitolo["titolo"],
                        "ordine": j + 1
                    }
                    
                    # Aggiungiamo i punti chiave se presenti
                    if "punti_chiave" in sottocapitolo:
                        sottocapitolo_formattato["punti_chiave"] = sottocapitolo["punti_chiave"]
                    
                    capitolo_formattato["sottocapitoli"].append(sottocapitolo_formattato)
            
            scaletta_formattata["capitoli"].append(capitolo_formattato)
        
        # Salviamo la scaletta aggiornata
        successo = salva_scaletta(corso_id, scaletta_formattata)
        
        if successo:
            return {
                "success": True, 
                "message": "Scaletta aggiornata con successo",
                "scaletta": scaletta_formattata
            }
        else:
            return {"success": False, "message": "Errore durante il salvataggio della scaletta"}
            
    except Exception as e:
        logger.error(f"Errore durante la modifica della scaletta: {str(e)}")
        return {"success": False, "message": f"Errore durante la modifica della scaletta: {str(e)}"}

async def modifica_contenuto_capitolo(corso_id: str, capitolo_id: str, contenuto: str) -> Dict[str, Any]:
    """
    Aggiorna il contenuto di un capitolo specifico.
    
    Args:
        corso_id: ID del corso
        capitolo_id: ID del capitolo
        contenuto: Il nuovo contenuto testuale del capitolo
        
    Returns:
        Un dizionario con i risultati dell'operazione
    """
    try:
        # Verifichiamo che il corso esista
        corso = carica_corso(corso_id)
        if not corso:
            return {"success": False, "message": "Corso non trovato"}
            
        # Verifichiamo che il capitolo esista nella scaletta
        if "scaletta" not in corso or "capitoli" not in corso["scaletta"]:
            return {"success": False, "message": "Scaletta non trovata per questo corso"}
            
        capitolo_trovato = False
        for capitolo in corso["scaletta"]["capitoli"]:
            if capitolo["id"] == capitolo_id:
                capitolo_trovato = True
                break
                
        if not capitolo_trovato:
            return {"success": False, "message": "Capitolo non trovato nella scaletta"}
        
        # Salviamo il nuovo contenuto
        successo = salva_contenuto_capitolo(corso_id, capitolo_id, contenuto)
        
        if successo:
            return {
                "success": True,
                "message": "Contenuto del capitolo aggiornato con successo",
                "contenuto": contenuto
            }
        else:
            return {
                "success": False,
                "message": "Errore durante il salvataggio del contenuto del capitolo"
            }
            
    except Exception as e:
        logger.error(f"Errore durante la modifica del contenuto del capitolo: {str(e)}")
        return {
            "success": False,
            "message": f"Errore durante la modifica del contenuto del capitolo: {str(e)}"
        }

async def esporta_corso(corso_id: str, formato: str) -> Dict[str, Any]:
    """
    Esporta il corso nel formato specificato.
    
    Args:
        corso_id: ID del corso
        formato: Formato di esportazione ('pdf', 'markdown', 'html', 'docx')
        
    Returns:
        Un dizionario con i risultati dell'operazione e l'URL per il download
    """
    try:
        # Verifichiamo che il corso esista
        corso = carica_corso(corso_id)
        if not corso:
            return {"success": False, "message": "Corso non trovato"}
            
        # Verifichiamo che ci sia una scaletta
        if "scaletta" not in corso or not corso["scaletta"]:
            return {"success": False, "message": "Questo corso non ha ancora una scaletta"}
            
        # Carichiamo tutti i contenuti disponibili
        contenuti_corso = carica_contenuti_corso(corso_id)
        
        # Verifichiamo che tutti i capitoli abbiano contenuto
        capitoli_mancanti = []
        for capitolo in corso["scaletta"]["capitoli"]:
            if capitolo["id"] not in contenuti_corso:
                capitoli_mancanti.append(capitolo["titolo"])
                
        if capitoli_mancanti:
            return {
                "success": False, 
                "message": f"Mancano i contenuti per {len(capitoli_mancanti)} capitoli: {', '.join(capitoli_mancanti)}"
            }
        
        # Verifichiamo che il formato sia supportato
        formati_supportati = ["pdf", "markdown", "html", "docx"]
        if formato not in formati_supportati:
            return {"success": False, "message": f"Formato non supportato. Formati disponibili: {', '.join(formati_supportati)}"}
        
        # Prepariamo il contenuto completo del corso
        contenuto_completo = ""
        
        # Aggiungiamo il titolo e le informazioni del corso
        contenuto_completo += f"# {corso['parametri']['titolo']}\n\n"
        contenuto_completo += f"## Descrizione del Corso\n\n{corso['parametri']['descrizione']}\n\n"
        contenuto_completo += f"**Pubblico target:** {corso['parametri']['pubblico_target']}\n\n"
        contenuto_completo += f"**Livello di complessità:** {corso['parametri']['livello_complessita']}\n\n"
        
        # Aggiungiamo i contenuti dei capitoli nell'ordine corretto
        for capitolo in corso["scaletta"]["capitoli"]:
            contenuto_completo += f"# {capitolo['titolo']}\n\n"
            if capitolo["id"] in contenuti_corso:
                contenuto_completo += contenuti_corso[capitolo["id"]] + "\n\n"
        
        # Implementiamo l'esportazione in base al formato
        # Nota: per ora, implementiamo solo l'esportazione in Markdown
        # Gli altri formati richiederebbero l'integrazione con librerie specifiche
        
        # Per il formato Markdown, restituiamo direttamente il contenuto
        if formato == "markdown":
            return {
                "success": True,
                "message": "Corso esportato come Markdown",
                "content": contenuto_completo,
                "filename": f"{corso['parametri']['titolo'].lower().replace(' ', '_')}.md"
            }
        elif formato == "html":
            # Convertiamo il Markdown in HTML
            try:
                import markdown
                
                # Convertiamo il contenuto Markdown in HTML
                html_content = markdown.markdown(contenuto_completo, extensions=['tables', 'fenced_code'])
                
                # Aggiungiamo un template HTML base per renderizzarlo presentabile
                html_output = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{corso['parametri']['titolo']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2, h3 {{ color: #2c3e50; }}
        code {{ background-color: #f8f9fa; padding: 2px 4px; border-radius: 4px; }}
        pre {{ background-color: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        blockquote {{ border-left: 4px solid #ccc; padding-left: 10px; margin-left: 0; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""
                
                return {
                    "success": True,
                    "message": "Corso esportato come HTML",
                    "content": html_output,
                    "filename": f"{corso['parametri']['titolo'].lower().replace(' ', '_')}.html"
                }
            except ImportError as e:
                logger.error(f"Errore di importazione durante la generazione HTML: {str(e)}")
                return {
                    "success": False,
                    "message": f"Impossibile esportare in HTML: libreria mancante. Errore: {str(e)}"
                }
            except Exception as e:
                logger.error(f"Errore durante la conversione in HTML: {str(e)}")
                return {
                    "success": False,
                    "message": f"Errore durante la conversione in HTML: {str(e)}"
                }
        elif formato == "pdf":
            # Generiamo un PDF dal contenuto Markdown usando ReportLab (soluzione nativa)
            try:
                import markdown
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
                from reportlab.platypus.flowables import HRFlowable
                from reportlab.lib.units import cm
                from io import BytesIO
                import base64
                import re
                
                logger.info("Iniziando la conversione in PDF con ReportLab (soluzione nativa)")
                
                # Convertiamo il contenuto Markdown in HTML per il parsing
                html_content = markdown.markdown(contenuto_completo, extensions=['tables', 'fenced_code'])
                
                # Creiamo un buffer per il PDF
                pdf_buffer = BytesIO()
                
                # Creiamo il documento PDF
                doc = SimpleDocTemplate(
                    pdf_buffer, 
                    pagesize=A4,
                    title=corso['parametri']['titolo'],
                    author="Generato con AI Course Builder",
                    leftMargin=2*cm, 
                    rightMargin=2*cm, 
                    topMargin=2*cm, 
                    bottomMargin=2*cm
                )
                
                # Stili per il documento
                styles = getSampleStyleSheet()
                
                # Modifichiamo gli stili esistenti invece di aggiungerne di nuovi
                styles['Heading1'].fontSize = 24
                styles['Heading1'].spaceAfter = 12
                
                styles['Heading2'].fontSize = 18
                styles['Heading2'].spaceAfter = 10
                
                styles['Heading3'].fontSize = 16
                styles['Heading3'].spaceAfter = 8
                
                # Aggiungiamo solo lo stile Code personalizzato che non esiste di default
                styles.add(ParagraphStyle(
                    name='CodeBlock',
                    parent=styles['Code'],
                    fontSize=9,
                    fontName='Courier',
                    backColor=colors.lightgrey,
                    spaceBefore=8,
                    spaceAfter=8
                ))
                
                # Aggiungiamo stili per intestazione e piè di pagina
                styles.add(ParagraphStyle(
                    name='Header',
                    parent=styles['Normal'],
                    fontSize=8,
                    textColor=colors.grey
                ))
                
                styles.add(ParagraphStyle(
                    name='Footer',
                    parent=styles['Normal'],
                    fontSize=8,
                    textColor=colors.grey,
                    alignment=1  # Centrato
                ))
                
                # Funzione per aggiungere intestazione e piè di pagina
                def header_footer(canvas, doc):
                    # Salva lo stato
                    canvas.saveState()
                    
                    # Intestazione
                    header = corso['parametri']['titolo']
                    canvas.setFont('Helvetica', 8)
                    canvas.setFillColor(colors.grey)
                    canvas.drawString(doc.leftMargin, doc.height + doc.topMargin - 10, header)
                    
                    # Piè di pagina con numero di pagina
                    footer = f"Pagina {doc.page} / Generato con AI Course Builder"
                    canvas.drawCentredString(doc.width/2 + doc.leftMargin, doc.bottomMargin - 20, footer)
                    
                    # Ripristina lo stato
                    canvas.restoreState()
                
                # Creiamo il documento PDF con intestazione e piè di pagina
                pdf_buffer = BytesIO()
                doc = SimpleDocTemplate(
                    pdf_buffer, 
                    pagesize=A4,
                    title=corso['parametri']['titolo'],
                    author="Generato con AI Course Builder",
                    leftMargin=2*cm, 
                    rightMargin=2*cm, 
                    topMargin=2*cm, 
                    bottomMargin=2*cm
                )
                
                # Impostiamo il template con intestazione e piè di pagina
                from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
                from reportlab.platypus.frames import Frame
                
                # Creiamo un frame per il contenuto principale
                frame = Frame(
                    doc.leftMargin,
                    doc.bottomMargin,
                    doc.width,
                    doc.height,
                    id='normal'
                )
                
                # Aggiungiamo il template al documento
                template = PageTemplate(
                    id='main_template',
                    frames=[frame],
                    onPage=header_footer
                )
                
                doc.addPageTemplates([template])
                
                # Funzione per convertire semplicemente HTML in elementi Platypus
                def html_to_platypus(html):
                    elements = []
                    
                    # Separiamo l'HTML in blocchi
                    # Nota: questa è una semplificazione, un parser HTML completo sarebbe più robusto
                    # ma molto più complesso da implementare
                    
                    # Titoli
                    for i, section in enumerate(re.split(r'<h1[^>]*>(.*?)</h1>', html)):
                        if i % 2 == 1:  # È un titolo h1
                            text = re.sub(r'<[^>]+>', '', section)
                            elements.append(Paragraph(text, styles['Heading1']))
                            elements.append(Spacer(1, 0.5*cm))
                        else:  # Contenuto tra titoli
                            # h2
                            for j, subsection in enumerate(re.split(r'<h2[^>]*>(.*?)</h2>', section)):
                                if j % 2 == 1:  # È un titolo h2
                                    text = re.sub(r'<[^>]+>', '', subsection)
                                    elements.append(Paragraph(text, styles['Heading2']))
                                    elements.append(Spacer(1, 0.3*cm))
                                else:  # Contenuto tra sottotitoli
                                    # h3
                                    for k, subsubsection in enumerate(re.split(r'<h3[^>]*>(.*?)</h3>', subsection)):
                                        if k % 2 == 1:  # È un titolo h3
                                            text = re.sub(r'<[^>]+>', '', subsubsection)
                                            elements.append(Paragraph(text, styles['Heading3']))
                                            elements.append(Spacer(1, 0.2*cm))
                                        else:  # Paragrafo normale
                                            # Gestiamo i tag <p>
                                            for p in re.split(r'<p[^>]*>(.*?)</p>', subsubsection):
                                                if p.strip():
                                                    # Gestiamo blocchi di codice
                                                    if '<pre><code>' in p:
                                                        code_parts = re.split(r'<pre><code>(.*?)</code></pre>', p, flags=re.DOTALL)
                                                        for l, part in enumerate(code_parts):
                                                            if l % 2 == 1:  # È un blocco di codice
                                                                elements.append(Paragraph(part, styles['CodeBlock']))
                                                            elif part.strip():  # Testo normale
                                                                elements.append(Paragraph(part, styles['Normal']))
                                                    else:
                                                        # Testo normale (sostituzione di alcuni tag HTML comuni)
                                                        p = re.sub(r'<strong>(.*?)</strong>', r'<b>\1</b>', p)
                                                        p = re.sub(r'<em>(.*?)</em>', r'<i>\1</i>', p)
                                                        p = re.sub(r'<code>(.*?)</code>', r'<font face="Courier">\1</font>', p)
                                                        
                                                        if p.strip():
                                                            elements.append(Paragraph(p, styles['Normal']))
                                                            elements.append(Spacer(1, 0.2*cm))
                    
                    return elements
                
                # Convertiamo HTML in elementi Platypus
                story = []
                
                # Aggiungiamo il titolo del corso
                story.append(Paragraph(corso['parametri']['titolo'], styles['Title']))
                story.append(Spacer(1, 0.5*cm))
                
                # Aggiungiamo la descrizione
                story.append(Paragraph("Descrizione del Corso", styles['Heading2']))
                story.append(Paragraph(corso['parametri']['descrizione'], styles['Normal']))
                story.append(Spacer(1, 0.3*cm))
                
                # Aggiungiamo i metadati
                metadata = [
                    ["Pubblico target:", corso['parametri']['pubblico_target']],
                    ["Livello di complessità:", corso['parametri']['livello_complessita']],
                    ["Tono:", corso['parametri']['tono']]
                ]
                
                if corso['parametri'].get('requisiti_specifici'):
                    metadata.append(["Requisiti specifici:", corso['parametri']['requisiti_specifici']])
                
                if corso['parametri'].get('stile_scrittura'):
                    metadata.append(["Stile di scrittura:", corso['parametri']['stile_scrittura']])
                
                # Creiamo una tabella per i metadati
                metadata_table = Table(metadata, colWidths=[4*cm, 12*cm])
                metadata_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                    ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
                    ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                
                story.append(metadata_table)
                story.append(Spacer(1, 1*cm))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
                story.append(Spacer(1, 0.5*cm))
                
                # Aggiungiamo un indice dei contenuti
                story.append(Paragraph("Indice dei contenuti", styles['Heading2']))
                story.append(Spacer(1, 0.3*cm))
                
                for i, capitolo in enumerate(corso["scaletta"]["capitoli"]):
                    story.append(Paragraph(f"{i+1}. {capitolo['titolo']}", styles['Normal']))
                
                story.append(Spacer(1, 1*cm))
                story.append(PageBreak())
                
                # Aggiungiamo i contenuti dei capitoli
                for capitolo in corso["scaletta"]["capitoli"]:
                    if capitolo["id"] in contenuti_corso:
                        # Aggiungiamo il titolo del capitolo
                        story.append(Paragraph(capitolo['titolo'], styles['Heading1']))
                        story.append(Spacer(1, 0.3*cm))
                        
                        # Elaboriamo il contenuto del capitolo
                        capitolo_html = markdown.markdown(contenuti_corso[capitolo["id"]], extensions=['tables', 'fenced_code'])
                        story.extend(html_to_platypus(capitolo_html))
                        
                        # Aggiungiamo un'interruzione di pagina dopo ogni capitolo
                        story.append(PageBreak())
                
                # Costruiamo il documento PDF
                doc.build(story)
                
                # Otteniamo il contenuto del PDF
                pdf_content = pdf_buffer.getvalue()
                logger.info("PDF generato con successo tramite ReportLab")
                
                # Codifichiamo il contenuto del PDF in base64
                pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
                
                return {
                    "success": True,
                    "message": "Corso esportato come PDF",
                    "content": pdf_base64,
                    "is_binary": True,
                    "filename": f"{corso['parametri']['titolo'].lower().replace(' ', '_')}.pdf"
                }
            except Exception as e:
                logger.error(f"Errore durante la conversione in PDF con ReportLab: {str(e)}")
                
                # Fallback: ritorniamo un messaggio informativo e suggeriamo di usare HTML
                return {
                    "success": False,
                    "message": f"Non è stato possibile generare il PDF a causa di un errore: {str(e)}. " +
                              "Ti consigliamo di esportare il corso in formato HTML e poi convertirlo in PDF " +
                              "utilizzando il tuo browser o un convertitore online."
                }
        elif formato == "docx":
            # Convertiamo il Markdown in DOCX
            try:
                import pypandoc
                import tempfile
                import os
                import base64
                
                # Verifica se Pandoc è disponibile e tenta di scaricarlo se mancante
                try:
                    # Verifica se Pandoc è già installato
                    pypandoc.get_pandoc_version()
                except OSError:
                    logger.warning("Pandoc non trovato. Tentativo di download automatico...")
                    try:
                        # Tenta di scaricare Pandoc automaticamente
                        pypandoc.download_pandoc()
                        logger.info("Pandoc scaricato con successo!")
                    except Exception as e:
                        logger.error(f"Impossibile scaricare Pandoc automaticamente: {str(e)}")
                        return {
                            "success": False,
                            "message": "Per esportare in formato DOCX è necessario Pandoc. " +
                                     "Puoi installarlo manualmente da http://pandoc.org/installing.html " +
                                     "oppure esportare il corso in altro formato (HTML o PDF)."
                        }
                
                # Creiamo un file Markdown temporaneo
                with tempfile.NamedTemporaryFile(suffix='.md', delete=False, mode='w', encoding='utf-8') as md_file:
                    md_file.write(contenuto_completo)
                    md_path = md_file.name
                
                # Creiamo un percorso per il file DOCX temporaneo
                docx_path = md_path.replace('.md', '.docx')
                
                # Convertiamo il Markdown in DOCX usando Pandoc
                pypandoc.convert_file(md_path, 'docx', outputfile=docx_path)
                
                # Leggiamo il contenuto binario del file DOCX
                with open(docx_path, 'rb') as docx_file:
                    docx_content = docx_file.read()
                
                # Codifichiamo il contenuto in base64
                docx_base64 = base64.b64encode(docx_content).decode('utf-8')
                
                # Puliamo i file temporanei
                os.remove(md_path)
                os.remove(docx_path)
                
                return {
                    "success": True,
                    "message": "Corso esportato come DOCX",
                    "content": docx_base64,
                    "is_binary": True,
                    "filename": f"{corso['parametri']['titolo'].lower().replace(' ', '_')}.docx"
                }
            except ImportError as e:
                logger.error(f"Errore di importazione durante la generazione DOCX: {str(e)}")
                return {
                    "success": False,
                    "message": "Impossibile esportare in DOCX: la libreria pypandoc non è installata. " + 
                              "Usa il comando 'pip install pypandoc' per installarla, oppure esporta il corso in un altro formato."
                }
            except Exception as e:
                logger.error(f"Errore durante la conversione in DOCX: {str(e)}")
                return {
                    "success": False,
                    "message": f"Errore durante la conversione in DOCX: {str(e)}. " +
                              "Prova ad esportare il corso in un altro formato (HTML o PDF)."
                }
        else:
            # Per altri formati, restituiamo un messaggio di implementazione futura
            return {
                "success": False,
                "message": f"L'esportazione in formato {formato} non è ancora implementata"
            }
            
    except Exception as e:
        logger.error(f"Errore durante l'esportazione del corso: {str(e)}")
        return {"success": False, "message": f"Errore durante l'esportazione del corso: {str(e)}"}

def percento_completamento(corso_id: str) -> int:
    """Calcola la percentuale di completamento del corso."""
    corso = carica_corso(corso_id)
    if not corso or not corso.get('scaletta'):
        return 0
    
    num_capitoli = len(corso['scaletta']['capitoli'])
    if num_capitoli == 0:
        return 0
    
    contenuti = carica_contenuti_corso(corso_id)
    capitoli_generati = 0
    
    for cap in corso['scaletta']['capitoli']:
        if cap['id'] in contenuti:
            capitoli_generati += 1
    
    return round((capitoli_generati / num_capitoli) * 100)

def carica_contenuto_capitolo(corso_id: str, capitolo_id: str) -> Optional[str]:
    """Carica il contenuto di un capitolo dal database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT contenuto FROM contenuti_capitoli WHERE corso_id = ? AND capitolo_id = ? AND generato = 1",
            (corso_id, capitolo_id)
        )
        
        risultato = cursor.fetchone()
        if risultato:
            contenuto = risultato[0]
            # Standardizza il contenuto esistente
            contenuto = standardizza_markdown(contenuto, "generic")
            return contenuto
        return None
    except Exception as e:
        print(f"Errore nel caricamento del contenuto del capitolo: {e}")
        return None
    finally:
        conn.close()

def capitolo_generato(corso_id: str, capitolo_id: str) -> bool:
    """Verifica se un capitolo è stato generato."""
    return carica_contenuto_capitolo(corso_id, capitolo_id) is not None

async def espandi_contenuti_corso(corso_id: str, parametri_espansione: Dict[str, Any]) -> Dict[str, Any]:
    """
    Espande i contenuti di tutti i capitoli di un corso già generati.
    
    Args:
        corso_id: ID del corso da espandere
        parametri_espansione: Parametri per l'espansione (stile, lunghezza, focus, ecc.)
        
    Returns:
        Dizionario con il risultato dell'operazione
    """
    logger.info(f"Richiesta espansione contenuti per corso {corso_id}")
    
    # Verifica che il corso esista
    corso = carica_corso(corso_id)
    if not corso:
        logger.error(f"Corso {corso_id} non trovato")
        return {
            "success": False,
            "message": "Corso non trovato"
        }
    
    # Verifica se c'è già un'espansione in corso per questo corso
    if corso_id in _espansione_stato and _espansione_stato[corso_id]["stato"] in ["in_corso", "in_pausa"]:
        logger.warning(f"Espansione già in corso per il corso {corso_id}")
        return {
            "success": False,
            "message": "Un'espansione è già in corso per questo corso. Attendi il completamento o annulla l'espansione corrente.",
            "stato": _espansione_stato[corso_id]["stato"]
        }
    
    # Verifica che tutti i capitoli siano stati generati
    percentuale = percento_completamento(corso_id)
    if percentuale < 100:
        logger.error(f"Impossibile espandere: non tutti i capitoli sono stati generati ({percentuale}%)")
        return {
            "success": False,
            "message": f"Per espandere i contenuti, tutti i capitoli devono essere generati. Completamento attuale: {percentuale}%"
        }
    
    # Carica i contenuti di tutti i capitoli
    contenuti = carica_contenuti_corso(corso_id)
    if not contenuti:
        logger.error(f"Nessun contenuto trovato per il corso {corso_id}")
        return {
            "success": False,
            "message": "Nessun contenuto trovato per questo corso"
        }
    
    # Inizializza il client AI
    ai_client = create_ai_client()
    
    # Estrai i parametri di espansione
    fattore_espansione = parametri_espansione.get("fattore_espansione", 3)
    stile_espansione = parametri_espansione.get("stile_espansione", "discorsivo")
    focus_espansione = parametri_espansione.get("focus_espansione", [])
    istruzioni_aggiuntive = parametri_espansione.get("istruzioni_aggiuntive", "")
    
    # Controllo del flusso
    continua_dopo_errore = parametri_espansione.get("continua_dopo_errore", False)
    pausa_tra_capitoli = parametri_espansione.get("pausa_tra_capitoli", 0)  # Secondi di pausa
    pausa_tra_sezioni = parametri_espansione.get("pausa_tra_sezioni", 1)   # Secondi di pausa tra sezioni (default 1s)
    
    # Verifica se è richiesta l'espansione di un solo capitolo
    solo_capitolo = parametri_espansione.get("solo_capitolo", None)
    
    # Prepara il risultato e inizializza lo stato dell'espansione
    risultato = {
        "success": True,
        "capitoli_espansi": 0,
        "totale_capitoli": len(corso["scaletta"]["capitoli"]),
        "dettagli_capitoli": [],
        "stato": "in_corso"  # Può essere "completato", "parziale", "annullato", "in_pausa"
    }
    
    # Inizializza i dettagli dei capitoli con lo stato iniziale
    for capitolo in corso["scaletta"]["capitoli"]:
        risultato["dettagli_capitoli"].append({
            "id": capitolo["id"],
            "titolo": capitolo["titolo"],
            "espanso": False,
            "messaggio": "In attesa di elaborazione"
        })
    
    # Se espandiamo un solo capitolo, aggiorna il conteggio totale
    if solo_capitolo:
        risultato["totale_capitoli"] = 1
        logger.info(f"Espansione limitata al solo capitolo {solo_capitolo}")
    
    # Salva lo stato iniziale dell'espansione
    _espansione_stato[corso_id] = risultato
    
    # Controlla se c'è un punto di ripresa specificato nei parametri
    capitolo_ripresa = parametri_espansione.get("capitolo_ripresa", None)
    sezione_ripresa = parametri_espansione.get("sezione_ripresa", None)
    
    # Espandi ogni capitolo
    for i, capitolo in enumerate(corso["scaletta"]["capitoli"]):
        capitolo_id = capitolo["id"]
        
        # Se è richiesto un solo capitolo e non è questo, salta
        if solo_capitolo and capitolo_id != solo_capitolo:
            continue
        
        # Se è specificato un capitolo di ripresa, salta fino a quel capitolo
        if capitolo_ripresa and capitolo_id != capitolo_ripresa:
            # Verifica se questo capitolo è già stato espanso in precedenza
            contenuto_espanso = carica_contenuto_capitolo(corso_id, capitolo_id)
            if contenuto_espanso and len(contenuto_espanso) > len(contenuti.get(capitolo_id, "")):
                # Il capitolo è già stato espanso, aggiorna lo stato
                risultato["dettagli_capitoli"][i]["espanso"] = True
                risultato["dettagli_capitoli"][i]["lunghezza_originale"] = len(contenuti.get(capitolo_id, ""))
                risultato["dettagli_capitoli"][i]["lunghezza_espansa"] = len(contenuto_espanso)
                risultato["dettagli_capitoli"][i]["fattore_reale"] = round(len(contenuto_espanso) / len(contenuti.get(capitolo_id, "")), 1)
                risultato["capitoli_espansi"] += 1
                _espansione_stato[corso_id] = risultato
            continue
        
        # Verifica se l'espansione è stata annullata o messa in pausa
        if _espansione_stato[corso_id]["stato"] == "annullato":
            logger.info(f"Espansione del corso {corso_id} annullata dall'utente")
            risultato["stato"] = "annullato"
            risultato["message"] = "Espansione annullata dall'utente"
            _espansione_stato[corso_id] = risultato
            return risultato
        
        # Se l'espansione è in pausa, attendi finché non viene ripresa o annullata
        while _espansione_stato[corso_id]["stato"] == "in_pausa":
            logger.info(f"Espansione del corso {corso_id} in pausa, attendo...")
            await asyncio.sleep(1)  # Attendi 1 secondo e ricontrolla
            
            # Se l'espansione è stata annullata durante la pausa, esci
            if _espansione_stato[corso_id]["stato"] == "annullato":
                logger.info(f"Espansione del corso {corso_id} annullata durante la pausa")
                risultato["stato"] = "annullato"
                risultato["message"] = "Espansione annullata dall'utente"
                _espansione_stato[corso_id] = risultato
                return risultato
        
        # Se l'espansione è stata annullata, esci dal ciclo
        if _espansione_stato[corso_id]["stato"] == "annullato":
            break
        
        # Verifica che il capitolo sia stato generato
        if capitolo_id not in contenuti:
            logger.warning(f"Capitolo {capitolo_id} non trovato nei contenuti, salto l'espansione")
            risultato["dettagli_capitoli"][i]["espanso"] = False
            risultato["dettagli_capitoli"][i]["messaggio"] = "Contenuto non trovato"
            
            # Aggiorna lo stato dell'espansione
            _espansione_stato[corso_id] = risultato
            continue
        
        # Marca il capitolo come in elaborazione e aggiorna lo stato
        risultato["dettagli_capitoli"][i]["in_elaborazione"] = True
        risultato["dettagli_capitoli"][i]["messaggio"] = "Elaborazione in corso..."
        _espansione_stato[corso_id] = risultato
        
        # Ottieni il contenuto originale
        contenuto_originale = contenuti[capitolo_id]
        
        try:
            logger.info(f"Inizio espansione del capitolo {capitolo_id}: {capitolo['titolo']}")
            
            # Dividi il contenuto in sezioni basate sui titoli di secondo livello (##)
            sezioni = dividi_contenuto_in_sezioni(contenuto_originale)
            
            if not sezioni:
                # Se non ci sono sezioni, tratta l'intero contenuto come una singola sezione
                sezioni = [{"titolo": capitolo['titolo'], "contenuto": contenuto_originale}]
            
            # Aggiorna lo stato con il numero di sezioni
            risultato["dettagli_capitoli"][i]["totale_sezioni"] = len(sezioni)
            _espansione_stato[corso_id] = risultato
            
            # Espandi ogni sezione separatamente
            sezioni_espanse = []
            errore_in_sezione = False
            
            # Inizializza un file temporaneo per salvare le sezioni già espanse
            temp_file_path = os.path.join("app/data/contenuti", f"{corso_id}_{capitolo_id}_temp.md")
            if not sezione_ripresa:
                # Se non c'è una sezione di ripresa, cancella il file temporaneo se esiste
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            
            # Recupera eventuali sezioni già espanse dal file temporaneo
            sezioni_gia_espanse = []
            if os.path.exists(temp_file_path):
                try:
                    with open(temp_file_path, 'r', encoding='utf-8') as f:
                        temp_content = f.read()
                        temp_sections = json.loads(temp_content)
                        sezioni_gia_espanse = temp_sections
                        
                        # Aggiungi le sezioni già espanse alla lista
                        sezioni_espanse = sezioni_gia_espanse.copy()
                        logger.info(f"Recuperate {len(sezioni_gia_espanse)} sezioni già espanse per il capitolo {capitolo_id}")
                except Exception as e:
                    logger.error(f"Errore nel recupero delle sezioni già espanse: {str(e)}")
            
            # Calcola l'indice di partenza in base alle sezioni già espanse
            indice_iniziale = 0
            if sezione_ripresa and len(sezioni_gia_espanse) > 0:
                indice_iniziale = len(sezioni_gia_espanse)
                logger.info(f"Ripresa espansione dalla sezione {indice_iniziale+1}/{len(sezioni)}")
            
            for j, sezione in enumerate(sezioni):
                # Salta le sezioni già espanse
                if j < indice_iniziale:
                    continue
                
                # Verifica se l'espansione è stata annullata o messa in pausa
                if _espansione_stato[corso_id]["stato"] == "annullato":
                    logger.info(f"Espansione del corso {corso_id} annullata durante l'elaborazione della sezione {j+1}/{len(sezioni)}")
                    risultato["stato"] = "annullato"
                    risultato["message"] = "Espansione annullata dall'utente"
                    _espansione_stato[corso_id] = risultato
                    return risultato
                
                # Se l'espansione è in pausa, attendi finché non viene ripresa o annullata
                while _espansione_stato[corso_id]["stato"] == "in_pausa":
                    logger.info(f"Espansione del corso {corso_id} in pausa durante l'elaborazione della sezione {j+1}/{len(sezioni)}, attendo...")
                    await asyncio.sleep(1)  # Attendi 1 secondo e ricontrolla
                    
                    # Se l'espansione è stata annullata durante la pausa, esci
                    if _espansione_stato[corso_id]["stato"] == "annullato":
                        logger.info(f"Espansione del corso {corso_id} annullata durante la pausa")
                        risultato["stato"] = "annullato"
                        risultato["message"] = "Espansione annullata dall'utente"
                        _espansione_stato[corso_id] = risultato
                        return risultato
                
                # Se l'espansione è stata annullata, esci dal ciclo
                if _espansione_stato[corso_id]["stato"] == "annullato":
                    break
                
                logger.info(f"Espansione sezione {j+1}/{len(sezioni)} del capitolo {capitolo_id}")
                
                # Aggiorna lo stato con la sezione corrente
                risultato["dettagli_capitoli"][i]["sezione_corrente"] = j + 1
                _espansione_stato[corso_id] = risultato
                
                # Prepara il prompt per l'espansione della sezione
                prompt_espansione = f"""
Sei un assistente specializzato nell'espansione di contenuti didattici. Il tuo compito è espandere il contenuto fornito seguendo queste istruzioni.

### Contenuto originale da espandere:

{sezione['contenuto']}

### Istruzioni per l'espansione:

- Espandi il contenuto originale di circa {fattore_espansione} volte la sua lunghezza attuale
- Mantieni la struttura generale e i concetti chiave del contenuto originale
- Utilizza uno stile {stile_espansione}, con un linguaggio naturale e scorrevole
- Evita elenchi puntati eccessivi e frasi troppo brevi o schematiche
- Rendi il testo più discorsivo, come se stessi spiegando i concetti a voce
- Aggiungi esempi pratici, analogie e spiegazioni più dettagliate
"""
                
                # Aggiungi focus specifici se presenti
                if focus_espansione:
                    prompt_espansione += "\n\n### Focus specifici per l'espansione:\n"
                    for focus in focus_espansione:
                        prompt_espansione += f"- {focus}\n"
                
                # Aggiungi istruzioni aggiuntive se presenti
                if istruzioni_aggiuntive:
                    prompt_espansione += f"\n\n### Istruzioni aggiuntive:\n{istruzioni_aggiuntive}\n"
                
                prompt_espansione += """
### Formato di output:
Fornisci il contenuto espanso in formato Markdown, mantenendo i titoli e la struttura generale del contenuto originale.
"""
                
                # Chiamata all'AI per espandere la sezione
                risposta_ai = await ai_client.genera_contenuto_espanso(
                    corso_id=corso_id,
                    capitolo_id=f"{capitolo_id}_sezione_{j+1}",
                    contenuto_originale=sezione['contenuto'],
                    prompt_espansione=prompt_espansione
                )
                
                if risposta_ai["success"]:
                    # Aggiungi la sezione espansa
                    sezione_espansa = {
                        "titolo": sezione['titolo'],
                        "contenuto": risposta_ai["contenuto"]
                    }
                    sezioni_espanse.append(sezione_espansa)
                    
                    # Salva immediatamente la sezione espansa nel file temporaneo
                    try:
                        with open(temp_file_path, 'w', encoding='utf-8') as f:
                            json.dump(sezioni_espanse, f, ensure_ascii=False, indent=2)
                        logger.info(f"Sezione {j+1}/{len(sezioni)} del capitolo {capitolo_id} salvata temporaneamente")
                    except Exception as e:
                        logger.error(f"Errore nel salvataggio temporaneo della sezione {j+1}: {str(e)}")
                else:
                    logger.error(f"Errore nell'espansione della sezione {j+1} del capitolo {capitolo_id}: {risposta_ai.get('message', 'Errore sconosciuto')}")
                    errore_in_sezione = True
                    
                    # Aggiorna lo stato con l'errore
                    risultato["dettagli_capitoli"][i]["messaggio"] = f"Errore nella sezione {j+1}: {risposta_ai.get('message', 'Errore sconosciuto')}"
                    _espansione_stato[corso_id] = risultato
                    
                    # Se non dobbiamo continuare dopo un errore, interrompi l'espansione di questo capitolo
                    if not continua_dopo_errore:
                        break
                
                # Pausa tra le sezioni per evitare sovraccarichi
                if j < len(sezioni) - 1 and pausa_tra_sezioni > 0:
                    logger.info(f"Pausa di {pausa_tra_sezioni} secondi prima della prossima sezione")
                    await asyncio.sleep(pausa_tra_sezioni)
            
            # Se l'espansione è stata annullata, esci dal ciclo principale
            if _espansione_stato[corso_id]["stato"] == "annullato":
                risultato["stato"] = "annullato"
                risultato["message"] = "Espansione annullata dall'utente"
                _espansione_stato[corso_id] = risultato
                return risultato
            
            # Se c'è stato un errore in una sezione e non continuiamo dopo gli errori, segna il capitolo come non espanso
            if errore_in_sezione and not continua_dopo_errore:
                risultato["dettagli_capitoli"][i]["espanso"] = False
                risultato["dettagli_capitoli"][i]["in_elaborazione"] = False
                risultato["dettagli_capitoli"][i]["errore"] = True
                
                # Aggiorna lo stato dell'espansione
                _espansione_stato[corso_id] = risultato
                
                # Salva le informazioni di ripresa nel risultato
                risultato["punto_ripresa"] = {
                    "corso_id": corso_id,
                    "capitolo_id": capitolo_id,
                    "sezione": risultato["dettagli_capitoli"][i]["sezione_corrente"]
                }
                
                # Se non dobbiamo continuare dopo un errore, interrompi l'espansione di tutti i capitoli
                if not continua_dopo_errore:
                    risultato["stato"] = "parziale"
                    risultato["message"] = f"Espansione interrotta al capitolo {i+1}/{risultato['totale_capitoli']} a causa di un errore."
                    break
                
                continue
            
            # Ricomponi il capitolo completo dalle sezioni espanse
            contenuto_espanso = ricomponi_sezioni(sezioni_espanse)
            
            # Aggiorna il contenuto nel database
            success = salva_contenuto_capitolo(
                corso_id=corso_id,
                capitolo_id=capitolo_id,
                contenuto=contenuto_espanso,
                modello_utilizzato=risposta_ai.get("modello_utilizzato", "AI")
            )
            
            if success:
                logger.info(f"Capitolo {capitolo_id} espanso con successo")
                risultato["capitoli_espansi"] += 1
                risultato["dettagli_capitoli"][i]["espanso"] = True
                risultato["dettagli_capitoli"][i]["in_elaborazione"] = False
                risultato["dettagli_capitoli"][i]["lunghezza_originale"] = len(contenuto_originale)
                risultato["dettagli_capitoli"][i]["lunghezza_espansa"] = len(contenuto_espanso)
                risultato["dettagli_capitoli"][i]["fattore_reale"] = round(len(contenuto_espanso) / len(contenuto_originale), 1) if len(contenuto_originale) > 0 else 0
                risultato["dettagli_capitoli"][i]["num_sezioni"] = len(sezioni)
                
                # Elimina il file temporaneo dopo il salvataggio completo
                if os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                        logger.info(f"File temporaneo per il capitolo {capitolo_id} eliminato dopo il salvataggio completo")
                    except Exception as e:
                        logger.error(f"Errore nell'eliminazione del file temporaneo: {str(e)}")
                
                # Aggiorna lo stato dell'espansione
                _espansione_stato[corso_id] = risultato
            else:
                logger.error(f"Errore nel salvataggio del capitolo espanso {capitolo_id}")
                risultato["dettagli_capitoli"][i]["espanso"] = False
                risultato["dettagli_capitoli"][i]["in_elaborazione"] = False
                risultato["dettagli_capitoli"][i]["errore"] = True
                risultato["dettagli_capitoli"][i]["messaggio"] = "Errore nel salvataggio del contenuto espanso"
                
                # Salva le informazioni di ripresa nel risultato
                risultato["punto_ripresa"] = {
                    "corso_id": corso_id,
                    "capitolo_id": capitolo_id,
                    "sezione": len(sezioni_espanse)
                }
                
                # Aggiorna lo stato dell'espansione
                _espansione_stato[corso_id] = risultato
                
                # Se non dobbiamo continuare dopo un errore, interrompi l'espansione
                if not continua_dopo_errore:
                    risultato["stato"] = "parziale"
                    risultato["message"] = f"Espansione interrotta al capitolo {i+1}/{risultato['totale_capitoli']} a causa di un errore di salvataggio."
                    break
        except Exception as e:
            logger.exception(f"Eccezione durante l'espansione del capitolo {capitolo_id}: {str(e)}")
            risultato["dettagli_capitoli"][i]["espanso"] = False
            risultato["dettagli_capitoli"][i]["in_elaborazione"] = False
            risultato["dettagli_capitoli"][i]["errore"] = True
            risultato["dettagli_capitoli"][i]["messaggio"] = f"Errore: {str(e)}"
            
            # Salva le informazioni di ripresa nel risultato
            risultato["punto_ripresa"] = {
                "corso_id": corso_id,
                "capitolo_id": capitolo_id,
                "sezione": risultato["dettagli_capitoli"][i].get("sezione_corrente", 0)
            }
            
            # Aggiorna lo stato dell'espansione
            _espansione_stato[corso_id] = risultato
    
    # Aggiorna il messaggio finale
    if not risultato.get("message"):
        if risultato["capitoli_espansi"] == risultato["totale_capitoli"]:
            risultato["message"] = f"Tutti i {risultato['totale_capitoli']} capitoli sono stati espansi con successo!"
            risultato["stato"] = "completato"
        elif risultato["capitoli_espansi"] > 0:
            risultato["message"] = f"Espansi {risultato['capitoli_espansi']} capitoli su {risultato['totale_capitoli']}."
            risultato["stato"] = "parziale"
        else:
            risultato["success"] = False
            risultato["message"] = "Nessun capitolo è stato espanso. Verifica i dettagli per maggiori informazioni."
            risultato["stato"] = "fallito"
    
    # Aggiorna lo stato finale dell'espansione
    _espansione_stato[corso_id] = risultato
    
    return risultato

def dividi_contenuto_in_sezioni(contenuto: str) -> List[Dict[str, str]]:
    """
    Divide il contenuto in sezioni basate sui titoli di secondo livello (##).
    Se le sezioni sono troppo grandi, le suddivide ulteriormente.
    
    Args:
        contenuto: Il contenuto markdown da dividere
        
    Returns:
        Lista di dizionari con titolo e contenuto di ogni sezione
    """
    import re
    
    # Trova tutti i titoli di secondo livello (##)
    pattern = r'^##\s+(.+)$'
    linee = contenuto.split('\n')
    sezioni = []
    sezione_corrente = None
    contenuto_corrente = []
    
    # Aggiungi il titolo principale se presente
    titolo_principale = None
    for linea in linee:
        if linea.startswith('# '):
            titolo_principale = linea[2:].strip()
            break
    
    for linea in linee:
        match = re.match(pattern, linea, re.MULTILINE)
        if match:
            # Se c'è già una sezione in corso, salvala
            if sezione_corrente is not None:
                sezioni.append({
                    "titolo": sezione_corrente,
                    "contenuto": '\n'.join(contenuto_corrente)
                })
            
            # Inizia una nuova sezione
            sezione_corrente = match.group(1)
            contenuto_corrente = [linea]
        elif sezione_corrente is not None:
            # Aggiungi la linea alla sezione corrente
            contenuto_corrente.append(linea)
    
    # Aggiungi l'ultima sezione se presente
    if sezione_corrente is not None and contenuto_corrente:
        sezioni.append({
            "titolo": sezione_corrente,
            "contenuto": '\n'.join(contenuto_corrente)
        })
    
    # Se non ci sono sezioni ma c'è un titolo principale, crea una sezione con tutto il contenuto
    if not sezioni and titolo_principale:
        sezioni.append({
            "titolo": titolo_principale,
            "contenuto": contenuto
        })
    
    # Se non ci sono sezioni, dividi il contenuto in paragrafi
    if not sezioni:
        paragrafi = re.split(r'\n\s*\n', contenuto)
        if len(paragrafi) > 1:
            # Crea sezioni di massimo 5 paragrafi ciascuna
            for i in range(0, len(paragrafi), 5):
                gruppo_paragrafi = paragrafi[i:i+5]
                sezioni.append({
                    "titolo": f"Parte {i//5 + 1}",
                    "contenuto": '\n\n'.join(gruppo_paragrafi)
                })
        else:
            # Se c'è un solo paragrafo, usalo come sezione
            sezioni.append({
                "titolo": "Contenuto",
                "contenuto": contenuto
            })
    
    # Verifica se le sezioni sono troppo grandi e dividile ulteriormente se necessario
    sezioni_finali = []
    for sezione in sezioni:
        contenuto_sezione = sezione["contenuto"]
        # Se la sezione è più lunga di 2000 caratteri, dividila
        if len(contenuto_sezione) > 2000:
            # Dividi in paragrafi
            paragrafi = re.split(r'\n\s*\n', contenuto_sezione)
            # Se ci sono più paragrafi, crea sottosezioni
            if len(paragrafi) > 1:
                # Crea sottosezioni di massimo 5 paragrafi ciascuna
                for i in range(0, len(paragrafi), 5):
                    gruppo_paragrafi = paragrafi[i:i+5]
                    sezioni_finali.append({
                        "titolo": f"{sezione['titolo']} - Parte {i//5 + 1}",
                        "contenuto": '\n\n'.join(gruppo_paragrafi)
                    })
            else:
                # Se c'è un solo paragrafo lungo, dividilo in frasi
                frasi = re.split(r'(?<=[.!?])\s+', contenuto_sezione)
                # Crea sottosezioni di massimo 10 frasi ciascuna
                for i in range(0, len(frasi), 10):
                    gruppo_frasi = frasi[i:i+10]
                    sezioni_finali.append({
                        "titolo": f"{sezione['titolo']} - Parte {i//10 + 1}",
                        "contenuto": ' '.join(gruppo_frasi)
                    })
        else:
            # Se la sezione non è troppo grande, aggiungila direttamente
            sezioni_finali.append(sezione)
    
    # Assicurati che ci sia almeno una sezione
    if not sezioni_finali:
        sezioni_finali.append({
            "titolo": "Contenuto",
            "contenuto": contenuto
        })
    
    return sezioni_finali

def ricomponi_sezioni(sezioni: List[Dict[str, str]]) -> str:
    """
    Ricompone le sezioni in un unico contenuto.
    
    Args:
        sezioni: Lista di dizionari con titolo e contenuto di ogni sezione
        
    Returns:
        Contenuto ricomposto
    """
    return '\n\n'.join([sezione["contenuto"] for sezione in sezioni])

def get_stato_espansione(corso_id: str) -> Dict[str, Any]:
    """
    Restituisce lo stato corrente dell'espansione per un corso.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        Stato dell'espansione
    """
    if corso_id not in _espansione_stato:
        # Se non c'è uno stato attivo, restituisci uno stato predefinito
        corso = carica_corso(corso_id)
        if not corso:
            return {
                "success": False,
                "message": "Corso non trovato",
                "stato": "non_iniziato"
            }
        
        return {
            "success": True,
            "capitoli_espansi": 0,
            "totale_capitoli": len(corso["scaletta"]["capitoli"]),
            "dettagli_capitoli": [],
            "stato": "non_iniziato"
        }
    
    return _espansione_stato[corso_id]

def pausa_espansione(corso_id: str) -> bool:
    """
    Mette in pausa l'espansione di un corso.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        True se l'operazione è riuscita, False altrimenti
    """
    if corso_id not in _espansione_stato:
        logger.warning(f"Impossibile mettere in pausa: nessuna espansione attiva per il corso {corso_id}")
        return False
    
    if _espansione_stato[corso_id]["stato"] != "in_corso":
        logger.warning(f"Impossibile mettere in pausa: l'espansione non è in corso (stato: {_espansione_stato[corso_id]['stato']})")
        return False
    
    _espansione_stato[corso_id]["stato"] = "in_pausa"
    logger.info(f"Espansione del corso {corso_id} messa in pausa")
    return True

def riprendi_espansione(corso_id: str) -> bool:
    """
    Riprende l'espansione di un corso precedentemente messa in pausa.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        True se l'operazione è riuscita, False altrimenti
    """
    if corso_id not in _espansione_stato:
        logger.warning(f"Impossibile riprendere: nessuna espansione attiva per il corso {corso_id}")
        return False
    
    if _espansione_stato[corso_id]["stato"] != "in_pausa":
        logger.warning(f"Impossibile riprendere: l'espansione non è in pausa (stato: {_espansione_stato[corso_id]['stato']})")
        return False
    
    _espansione_stato[corso_id]["stato"] = "in_corso"
    logger.info(f"Espansione del corso {corso_id} ripresa")
    return True

def annulla_espansione(corso_id: str) -> bool:
    """
    Annulla l'espansione di un corso in corso.
    
    Args:
        corso_id: ID del corso
        
    Returns:
        True se l'operazione è riuscita, False altrimenti
    """
    if corso_id not in _espansione_stato:
        logger.warning(f"Impossibile annullare: nessuna espansione attiva per il corso {corso_id}")
        return False
    
    if _espansione_stato[corso_id]["stato"] not in ["in_corso", "in_pausa"]:
        logger.warning(f"Impossibile annullare: l'espansione non è in corso o in pausa (stato: {_espansione_stato[corso_id]['stato']})")
        return False
    
    _espansione_stato[corso_id]["stato"] = "annullato"
    _espansione_stato[corso_id]["message"] = "Espansione annullata dall'utente"
    logger.info(f"Espansione del corso {corso_id} annullata")
    return True 