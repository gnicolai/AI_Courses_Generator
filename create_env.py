#!/usr/bin/env python
# Script per creare il file .env corretto

env_content = """# Configurazione delle API

# OpenAI
OPENAI_API_KEY=<inserisci-qui-la-tua-chiave-openai>
OPENAI_BASE_URL=https://api.openai.com

# Deepseek
DEEPSEEK_API_KEY=<inserisci-qui-la-tua-chiave-deepseek>
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Configurazione dell'applicazione
DEFAULT_AI_PROVIDER=openai
"""

try:
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)
    print("File .env creato con successo!")
except Exception as e:
    print(f"Errore nella creazione del file .env: {e}") 