import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Directory di configurazione
CONFIG_DIR = Path("app/config")
CONFIG_FILE = CONFIG_DIR / "settings.json"

# Crea la directory di configurazione se non esiste
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Configurazione predefinita con priorità alle variabili d'ambiente
DEFAULT_CONFIG = {
    "ai_provider": os.getenv("DEFAULT_AI_PROVIDER", "openai"),  # Opzioni: "mock", "deepseek", "openai"
    "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "deepseek_base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "deepseek_model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),  # Default a deepseek-chat (V3)
    "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com"),
    "openai_model": os.getenv("OPENAI_MODEL", "o1-preview")  # Modello predefinito: o1-preview (più probabile nome corretto)
}

def load_config() -> Dict[str, Any]:
    """Carica la configurazione dal file JSON e sovrascrive con variabili d'ambiente se presenti."""
    if not CONFIG_FILE.exists():
        # Se il file non esiste, crea uno con la configurazione predefinita
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
            # Assicurati che tutte le chiavi predefinite esistano
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            
            # Sovrascrivi con variabili d'ambiente se presenti, MA NON sovrascrivere ai_provider
            # perché vogliamo rispettare la scelta dell'utente
            # La variabile DEFAULT_AI_PROVIDER serve solo per l'inizializzazione iniziale
            # if os.getenv("DEFAULT_AI_PROVIDER"):
            #     config["ai_provider"] = os.getenv("DEFAULT_AI_PROVIDER")
            
            # Aggiorna solo le chiavi API e URL se presenti come variabili d'ambiente
            if os.getenv("DEEPSEEK_API_KEY"):
                config["deepseek_api_key"] = os.getenv("DEEPSEEK_API_KEY")
            if os.getenv("DEEPSEEK_BASE_URL"):
                config["deepseek_base_url"] = os.getenv("DEEPSEEK_BASE_URL")
            if os.getenv("OPENAI_API_KEY"):
                config["openai_api_key"] = os.getenv("OPENAI_API_KEY")
            if os.getenv("OPENAI_BASE_URL"):
                config["openai_base_url"] = os.getenv("OPENAI_BASE_URL")
            if os.getenv("OPENAI_MODEL"):
                config["openai_model"] = os.getenv("OPENAI_MODEL")
            
            return config
    except Exception as e:
        print(f"Errore nel caricamento della configurazione: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]) -> bool:
    """Salva la configurazione nel file JSON."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Errore nel salvataggio della configurazione: {e}")
        return False

def get_config_value(key: str, default: Any = None) -> Any:
    """Ottiene un valore specifico dalla configurazione."""
    config = load_config()
    return config.get(key, default)

def set_config_value(key: str, value: Any) -> bool:
    """Imposta un valore specifico nella configurazione."""
    config = load_config()
    config[key] = value
    return save_config(config)

def get_current_api_key() -> str:
    """Ottiene l'API key del provider attualmente in uso."""
    config = load_config()
    provider = config.get("ai_provider", "deepseek")
    
    if provider == "openai":
        return config.get("openai_api_key", "")
    else:
        return config.get("deepseek_api_key", DEFAULT_CONFIG["deepseek_api_key"]) 