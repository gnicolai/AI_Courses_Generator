with open('app/api/ai_client.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Correggo l'indentazione alle righe 702 e 703 (indici 701 e 702)
lines[701] = '                        if response.status_code != 200:\n'
lines[702] = '                            error_msg = "Errore sconosciuto"\n'

with open('app/api/ai_client.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Indentazione corretta!") 