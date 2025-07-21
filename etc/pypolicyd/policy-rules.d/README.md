# README: Policy Rules Modulari

## Panoramica
La directory `policy-rules.d/` consente di organizzare le regole policy in file separati per dominio o categoria, migliorando la gestione e la manutenzione delle configurazioni.

## Struttura
```
etc/pypolicyd/
├── main.yml                    # Configurazione principale del daemon
└── policy-rules.d/             # Directory modulare per le regole
    ├── example.com.yml         # Regole per example.com
    ├── test.com.yml           # Regole per test.com  
    ├── company.com.yml        # Regole per company.com
    └── special-users.yml      # Regole per utenti speciali (opzionale)
```

## Vantaggi
1. **Organizzazione**: Ogni dominio ha il proprio file di configurazione
2. **Manutenzione**: Più facile modificare regole specifiche per dominio
3. **Collaborazione**: Team diversi possono gestire file diversi
4. **Scalabilità**: Aggiunta di nuovi domini senza modificare file esistenti
5. **Retrocompatibilità**: Supporta ancora file singolo policy-rules.yml

## Formato File
Ogni file YAML in `policy-rules.d/` segue questo formato:

```yaml
# Regola generale per il dominio
"*@dominio.com":
  max_recipients: 50
  max_size: "10M"
  rate_limits:
    - "10/1m"     # 10 email al minuto
    - "100/1h"    # 100 email all'ora
    - "1000/1d"   # 1000 email al giorno

# Utenti specifici del dominio
"admin@dominio.com":
  max_recipients: 200
  max_size: "50M"
  rate_limits:
    - "20/1m"
    - "200/1h"
    - "2000/1d"
```

## Caricamento
Il sistema carica automaticamente tutti i file `.yml` e `.yaml` dalla directory, ordinandoli alfabeticamente. Se esistono regole duplicate, l'ultima regola caricata sovrascrive le precedenti.

## Configurazione
In `main.yml`, specifica la directory:

```yaml
smtp_policy:
  policy_rules_file: "/etc/pypolicyd/policy-rules.d"
```

## Test
Usa `test_modular_rules.py` per verificare il caricamento corretto:

```bash
python3 test_modular_rules.py
```

## Best Practices
- Un file per dominio principale
- Nomi file descrittivi (esempio: `company.com.yml`)
- Commenti per spiegare regole speciali
- Regole generali del dominio prima di quelle specifiche per utente
- Backup dei file prima delle modifiche
