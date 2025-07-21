# PyPolicyd Unit Tests

Questa directory contiene i test unitari e di integrazione per PyPolicyd.

## Struttura dei Test

### Test Unitari

- **`test_policy_config.py`** - Test per la classe PolicyConfig
  - Caricamento configurazione da file YAML
  - Valutazione policy con match esatto e wildcard
  - Gestione policy predefinita
  - Caricamento regole da directory

- **`test_rate_limit.py`** - Test per le classi RateLimit e MultiWindowRateTracker
  - Parsing formati rate limit (5/1m, 100/1h, etc.)
  - Controllo rate limits su finestre temporali multiple
  - Gestione utenti multipli
  - Pulizia record scaduti

- **`test_policy_daemon.py`** - Test per la classe PolicyDaemon principale
  - Inizializzazione daemon
  - Elaborazione richieste policy
  - Controlli max_recipients e max_size
  - Logging con chiavi delle regole

- **`test_logging_service.py`** - Test per il servizio di logging
  - Configurazione destinazioni log (stdout, file, syslog)
  - Formati log Postfix
  - Logging condizionale (all/rejected/none)
  - Logging connessioni

### Test di Integrazione

- **`test_integration.py`** - Test completi end-to-end
  - Workflow completo per diversi tipi di utenti
  - Verifica chiavi delle regole nei log
  - Test con configurazioni realistiche
  - Scenari di errore e successo

## Caratteristiche dei Test

### Test delle Chiavi delle Regole

I test verificano che il nuovo sistema di logging mostri correttamente le chiavi delle regole applicate:

```python
# Esempi di chiavi di regole nei log:
- 'ceo@company.com'      # Match esatto utente
- '*@company.com'        # Match wildcard dominio  
- 'admin@internal.com'   # Regola semplice
- 'default'              # Policy predefinita
```

### Test Asincroni

I test utilizzano `unittest.IsolatedAsyncioTestCase` per testare correttamente le funzioni asincrone del daemon.

### Configurazioni Temporanee

Tutti i test creano file di configurazione e database temporanei che vengono puliti automaticamente.

## Esecuzione dei Test

### Eseguire Tutti i Test

```bash
cd /Users/andrea/Projects/Monema/gensite/pypolicyd-debuild
python3 tests/run_tests.py
```

### Eseguire Test Specifici

```bash
# Test policy config
python3 -m unittest tests.test_policy_config

# Test rate limits
python3 -m unittest tests.test_rate_limit

# Test daemon principale
python3 -m unittest tests.test_policy_daemon

# Test logging
python3 -m unittest tests.test_logging_service

# Test di integrazione
python3 -m unittest tests.test_integration
```

### Eseguire Test Singolo

```bash
# Test specifico
python3 -m unittest tests.test_policy_config.TestPolicyConfig.test_evaluate_policy_exact_match
```

## Requisiti

I test richiedono:

- Python 3.7+
- PyYAML (`pip install pyyaml`)
- Moduli standard: unittest, tempfile, asyncio

## Copertura dei Test

I test coprono:

✅ **Valutazione Policy**
- Match esatto utente
- Match wildcard dominio  
- Policy predefinita
- Policy complesse vs semplici

✅ **Rate Limiting**
- Parsing formati temporali
- Finestre temporali multiple
- Persistenza SQLite
- Pulizia automatica

✅ **Logging**
- Chiavi delle regole nei log
- Formati Postfix
- Destinazioni multiple
- Logging condizionale

✅ **Integrazione**
- Workflow end-to-end
- Configurazioni realistiche
- Scenari di errore
- Performance base

## Output dei Test

I test in modalità debug mostrano:

```
=== Test Complete Workflow - CEO ===
[DEBUG] Valutazione policy per richiesta: {'sender': 'ceo@company.com', ...}
[DEBUG] Trovata regola sender esatta: ceo@company.com -> {...}
CEO normal request: DUNNO
CEO too many recipients: REJECT Too many recipients (600/500)
CEO message too large: REJECT Message too large (157286400/104857600 bytes)
```

Questo conferma che le chiavi delle regole vengono identificate e loggare correttamente.

## Note Tecniche

- I test utilizzano database SQLite temporanei in `/tmp/`
- I file di configurazione sono creati con `tempfile.mkstemp()`
- Le regole di test includono esempi realistici da `company.com.yml`
- I test asincroni utilizzano `IsolatedAsyncioTestCase` per isolamento completo
