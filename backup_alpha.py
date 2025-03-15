import os
import shutil
import zipfile
import datetime
import logging

# Configurazione logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_alpha_backup():
    """
    Crea un backup completo del progetto con nome "versione_alpha_YYYYMMDD_HHMMSS.zip"
    """
    # Ottiene la data e ora corrente per il nome del file
    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"versione_alpha_{current_time}"
    zip_filename = f"{backup_name}.zip"
    
    logger.info(f"Creazione backup 'versione alpha' in corso: {zip_filename}")
    
    # Elenco delle directory e file da includere nel backup
    include_dirs = ['app']
    include_files = [
        '.env', 'create_env.py', '.env_temp', 'simple_app.py', 'test_app.py', 'run.py',
        'README.md', 'requirements.txt', 'Roadmap.md'
    ]
    
    # Elenco delle directory e file da escludere dal backup
    exclude_patterns = [
        '__pycache__', '*.pyc', '*.pyo', '*.pyd', 
        '.git', '.idea', '.vscode', 'venv', '.cursor',
        '*.zip', '*.log', '.DS_Store'
    ]
    
    def should_exclude(path):
        """Verifica se un file/directory deve essere escluso dal backup"""
        for pattern in exclude_patterns:
            if pattern.startswith('*'):
                # Pattern di estensione file (*.xyz)
                ext = pattern[1:]
                if path.endswith(ext):
                    return True
            elif pattern in path:
                # Pattern di directory o file specifico
                return True
        return False
    
    try:
        # Crea una cartella temporanea per il backup
        temp_dir = f"temp_backup_{current_time}"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            logger.info(f"Creata directory temporanea: {temp_dir}")
        
        # Copia i file principali
        for file in include_files:
            if os.path.exists(file):
                shutil.copy2(file, os.path.join(temp_dir, file))
                logger.info(f"Copiato file: {file}")
            else:
                logger.warning(f"File non trovato, ignorato: {file}")
        
        # Copia le directory principali
        for directory in include_dirs:
            if os.path.exists(directory):
                dest_dir = os.path.join(temp_dir, directory)
                shutil.copytree(
                    directory, 
                    dest_dir,
                    ignore=lambda src, names: [name for name in names if should_exclude(os.path.join(src, name))]
                )
                logger.info(f"Copiata directory: {directory}")
            else:
                logger.warning(f"Directory non trovata, ignorata: {directory}")
        
        # Crea il file ZIP con il contenuto della directory temporanea
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname=arc_name)
        
        logger.info(f"File ZIP creato con successo: {zip_filename}")
        
        # Rimuove la directory temporanea
        shutil.rmtree(temp_dir)
        logger.info(f"Directory temporanea {temp_dir} rimossa")
        
        logger.info(f"Backup 'versione alpha' completato con successo: {zip_filename}")
        return zip_filename
        
    except Exception as e:
        logger.error(f"Errore durante la creazione del backup: {str(e)}")
        # Pulisce la directory temporanea in caso di errore
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Directory temporanea {temp_dir} rimossa dopo errore")
        return None

if __name__ == "__main__":
    backup_file = create_alpha_backup()
    if backup_file:
        print(f"\nBackup 'versione alpha' creato con successo: {backup_file}")
        print(f"Dimensione: {os.path.getsize(backup_file) / (1024*1024):.2f} MB")
    else:
        print("\nErrore durante la creazione del backup. Controlla i log per dettagli.") 