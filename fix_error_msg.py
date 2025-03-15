with open('app/api/ai_client.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Verifica se c'è duplicazione nelle righe 703-704
if 'error_msg = "Errore sconosciuto"' in lines[703] and 'error_msg = "Errore sconosciuto"' in lines[704]:
    lines[703] = '                            error_msg = "Errore sconosciuto"\n'
    del lines[704]
    print("Rimossa riga duplicata.")
else:
    print("Nessuna duplicazione trovata alle righe 703-704.")

with open('app/api/ai_client.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Operazione completata.") 