# Roadmap del Generatore di Corsi AI

## Visione
Creare un generatore di corsi semplice e lineare che permetta all'utente di:
1. Definire i parametri del corso
2. Generare una scaletta di capitoli e sottocapitoli
3. Modificare la scaletta
4. Generare i contenuti di ciascun capitolo con memoria contestuale
5. Modificare i contenuti dei capitoli (anche con AI)
6. Finalizzare il corso in un formato professionale

## Flusso Utente
1. **Inserimento Informazioni Corso**
   - Titolo/argomento
   - Descrizione/obiettivi
   - Pubblico target
   - Livello di complessità
   - Tono del corso
   - Requisiti specifici (opzionali)
   - Stile di scrittura (opzionale)

2. **Generazione Scaletta**
   - L'AI genera una scaletta di capitoli e sottocapitoli
   - Visualizzazione della scaletta in modalità ad albero
   - Possibilità di modificare titoli, aggiungere, rimuovere o riordinare elementi

3. **Generazione Contenuti**
   - Generazione progressiva dei contenuti capitolo per capitolo
   - Memorizzazione dei capitoli precedenti come contesto
   - Indicatore di avanzamento visibile
   - Possibilità di interrompere e riprendere il processo

4. **Modifica Contenuti**
   - Interfaccia per modificare ogni capitolo
   - Opzione per rigenerare un capitolo con AI fornendo direttive specifiche
   - Possibilità di mantenere parte del contenuto esistente

5. **Finalizzazione Corso**
   - Compilazione dei contenuti in un formato finale
   - Applicazione di uno stile coerente e professionale
   - Generazione di indice, introduzione e conclusione
   - Opzioni di esportazione (HTML, PDF, MD)

## Implementazione Tecnica

### Componenti da Sviluppare

1. **Frontend Semplificato**
   - Form di creazione corso unico e lineare
   - Editor di scaletta interattivo
   - Interfaccia di generazione progressiva
   - Editor di contenuti con opzioni AI

2. **Backend Efficiente**
   - API per generazione scaletta
   - API per generazione contenuti (con memoria contestuale)
   - API per rigenerazione mirata
   - Sistema di storage efficiente

3. **Sistema di Memoria Contestuale**
   - Memorizzazione e recupero efficiente dei contenuti generati
   - Creazione del contesto per evitare ripetizioni
   - Tracking dello stato di generazione

4. **Integrazione DeepSeek**
   - Ottimizzazione dei prompt per generare contenuti coerenti
   - Gestione efficiente del token budget
   - Fallback in caso di errori
   - API Deepseek: your-deepseek-api-key