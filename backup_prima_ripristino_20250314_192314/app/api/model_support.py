"""
Modulo per la gestione del supporto per i diversi modelli di AI.
Fornisce informazioni su quali parametri sono supportati da quali modelli.
"""

# Modelli che supportano il formato chat standard (system, user, assistant)
STANDARD_CHAT_MODELS = [
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-1",
    "gpt-4-1106-preview",
    "gpt-4-0125-preview", 
    "gpt-3.5-turbo"
]

# Modelli che richiedono formati specifici
SPECIAL_FORMAT_MODELS = {
    "o1-preview": {
        "supports_system_role": False,      # Non supporta role: system
        "max_tokens_param": "max_completion_tokens",  # Usa max_completion_tokens invece di max_tokens
        "supports_temperature": False,      # Non supporta il parametro temperature
        "supports_top_p": False,            # Non supporta il parametro top_p
        "supports_presence_penalty": False, # Non supporta il parametro presence_penalty
        "supports_frequency_penalty": False, # Non supporta il parametro frequency_penalty
        "max_context_length": 128000,       # Supporta context window molto grande
        "default_max_tokens": 8000,         # Default per i token di output
    },
    "o1": {
        "supports_system_role": False,
        "max_tokens_param": "max_completion_tokens",
        "supports_temperature": False,
        "supports_top_p": False,            # Non supporta il parametro top_p
        "supports_presence_penalty": False, # Non supporta il parametro presence_penalty
        "supports_frequency_penalty": False, # Non supporta il parametro frequency_penalty
        "max_context_length": 128000,
        "default_max_tokens": 8000,
    },
    "o1-mini": {
        "supports_system_role": False,
        "max_tokens_param": "max_completion_tokens",
        "supports_temperature": False,
        "supports_top_p": False,            # Non supporta il parametro top_p
        "supports_presence_penalty": False, # Non supporta il parametro presence_penalty
        "supports_frequency_penalty": False, # Non supporta il parametro frequency_penalty
        "max_context_length": 32000,
        "default_max_tokens": 4000,
    }
}

def get_model_config(model_name: str) -> dict:
    """
    Ottiene la configurazione per un modello specifico.
    
    Args:
        model_name: Nome del modello
        
    Returns:
        Dizionario con le configurazioni del modello
    """
    # Controlla se il modello è nella lista dei modelli special
    for model_prefix, config in SPECIAL_FORMAT_MODELS.items():
        if model_name.startswith(model_prefix):
            return config
            
    # Configurazione default per modelli standard
    return {
        "supports_system_role": True,
        "max_tokens_param": "max_tokens",
        "supports_temperature": True,
        "supports_top_p": True,
        "supports_presence_penalty": True,
        "supports_frequency_penalty": True,
        "max_context_length": 8192,  # Default per modelli standard
        "default_max_tokens": 4000,
    }

def prepare_messages(model_name: str, system_content: str, user_content: str) -> list:
    """
    Prepara i messaggi in base al modello utilizzato.
    
    Args:
        model_name: Nome del modello
        system_content: Contenuto del messaggio system
        user_content: Contenuto del messaggio user
        
    Returns:
        Lista di messaggi formattata correttamente per il modello
    """
    config = get_model_config(model_name)
    
    if config["supports_system_role"]:
        # Formato standard con ruoli separati
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
    else:
        # Incorpora le istruzioni system nel messaggio user
        combined_content = f"{system_content}\n\n{user_content}"
        return [
            {"role": "user", "content": combined_content}
        ]

def prepare_api_parameters(model_name: str, messages: list, temperature: float = 0.7, top_p: float = 0.95, 
                          presence_penalty: float = 0.0, frequency_penalty: float = 0.0) -> dict:
    """
    Prepara i parametri per la chiamata API in base al modello.
    
    Args:
        model_name: Nome del modello
        messages: Lista di messaggi
        temperature: Valore di temperatura (0.0-1.0)
        top_p: Valore di top_p per la diversità delle risposte (0.0-1.0)
        presence_penalty: Valore di presence_penalty (–2.0 a 2.0)
        frequency_penalty: Valore di frequency_penalty (–2.0 a 2.0)
        
    Returns:
        Dizionario con i parametri da inviare all'API
    """
    config = get_model_config(model_name)
    
    params = {
        "model": model_name,
        "messages": messages,
    }
    
    # Aggiungi il parametro corretto per i token massimi
    max_tokens_param = config["max_tokens_param"]
    params[max_tokens_param] = config["default_max_tokens"]
    
    # Aggiungi temperatura solo se supportata
    if config["supports_temperature"]:
        params["temperature"] = temperature
    
    # Aggiungi top_p solo se supportato
    if config.get("supports_top_p", True):  # Default a True per retrocompatibilità
        params["top_p"] = top_p
    
    # Aggiungi presence_penalty solo se supportato
    if config.get("supports_presence_penalty", True):
        params["presence_penalty"] = presence_penalty
    
    # Aggiungi frequency_penalty solo se supportato
    if config.get("supports_frequency_penalty", True):
        params["frequency_penalty"] = frequency_penalty
        
    return params 