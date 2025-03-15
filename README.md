# AI Courses Generator

Un generatore di corsi basato su intelligenza artificiale che utilizza OpenAI GPT e DeepSeek per espandere e arricchire contenuti didattici.

## Caratteristiche Principali

- 🤖 Supporto per multiple AI providers (OpenAI e DeepSeek)
- 📚 Espansione automatica dei contenuti dei capitoli
- 🔄 Sistema di ripresa automatica in caso di errori
- ⚙️ Configurazione flessibile dei parametri di espansione
- 🎨 Formattazione Markdown consistente
- 🔒 Gestione sicura delle API keys

## Requisiti di Sistema

- Python 3.8+
- Flask
- SQLite3
- Account API per OpenAI e/o DeepSeek

## Installazione

1. Clona il repository:
```bash
git clone https://github.com/gnicolai/AI_Courses_Generator.git
cd AI_Courses_Generator
```

2. Installa le dipendenze:
```bash
pip install -r requirements.txt
```

3. Configura le variabili d'ambiente:
   - Copia il file `.env.example` in `.env`
   - Inserisci le tue API keys e altre configurazioni nel file `.env`

## Configurazione

Il file `.env` deve contenere le seguenti variabili:

```
OPENAI_API_KEY=your-openai-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key
DEFAULT_AI_PROVIDER=openai
FLASK_ENV=development
SECRET_KEY=your-secret-key
DB_PATH=app/data/database.db
```

## Utilizzo

1. Avvia l'applicazione:
```bash
python run.py
```

2. Accedi all'interfaccia web all'indirizzo `http://localhost:5000`

3. Dalla pagina delle impostazioni puoi:
   - Selezionare il provider AI (OpenAI o DeepSeek)
   - Configurare i parametri di espansione
   - Gestire le pause tra le espansioni

4. Per espandere un capitolo:
   - Seleziona il corso e il capitolo desiderato
   - Clicca su "Espandi Contenuto"
   - In caso di interruzioni, usa il bottone "Riprendi" per continuare l'espansione

## Gestione degli Errori

- Il sistema include un meccanismo di retry automatico con backoff esponenziale
- In caso di errori di connessione, il sistema tenterà fino a 3 volte di riconnettersi
- I contenuti già espansi vengono salvati e possono essere recuperati
- È possibile configurare pause tra le espansioni per evitare sovraccarichi

## Struttura del Progetto

```
AI_Courses_Generator/
├── app/
│   ├── api/
│   │   ├── ai_client.py      # Gestione delle API AI
│   │   ├── controllers.py    # Controller principali
│   │   └── routes.py         # Route Flask
│   ├── models/
│   │   └── database.py       # Modelli del database
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   └── templates/            # Template HTML
├── .env.example             # Esempio configurazione
├── requirements.txt         # Dipendenze Python
└── run.py                  # Entry point
```

## Contribuire

Sentiti libero di aprire issues o pull requests per migliorare il progetto!

## Licenza

MIT License - vedi il file LICENSE per i dettagli. 