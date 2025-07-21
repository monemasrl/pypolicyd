# GitHub Actions Workflows

Questo progetto include diversi workflow GitHub Actions per automazione CI/CD.

## Workflow Disponibili

### 1. `test.yml` - Test Rapidi
**Trigger**: Push e Pull Request su `main`/`develop`

**Cosa fa**:
- ✅ Lint del codice Python con flake8
- ✅ Controllo formatting con black  
- ✅ Validazione file YAML
- ✅ Compilazione moduli Python
- ✅ Test configurazione e policy
- ✅ Test CLI tools

**Durata**: ~2-3 minuti

### 2. `build-deb.yml` - Build Pacchetti Debian
**Trigger**: Push su `main`/`develop`, tag `v*`, Pull Request su `main`

**Cosa fa**:
- 🏗️ Build pacchetti .deb su Ubuntu 20.04, 22.04, 24.04
- 🧪 Test compatibilità Python 3.8-3.12
- 📦 Upload artefatti per ogni versione Ubuntu
- 🏷️ Release automatica per i tag
- ✅ Test installazione pacchetto
- 🔍 Controlli qualità con lintian

**Durata**: ~8-10 minuti

## Artefatti Generati

### Build Artifacts
Ogni build genera artefatti scaricabili:
- `pypolicyd-deb-ubuntu-20.04/` 
- `pypolicyd-deb-ubuntu-22.04/`
- `pypolicyd-deb-ubuntu-24.04/`

Ogni artefatto contiene:
- `pypolicyd_*_all.deb` - Pacchetto Debian
- `pypolicyd_*.buildinfo` - Info di build
- `pypolicyd_*.changes` - Changelog build

### Release Automatiche
Per i tag `v*` (es. `v1.0.0`):
- 🚀 Release GitHub automatica
- 📦 Upload pacchetti .deb per tutte le versioni Ubuntu
- 📝 Note di release generate automaticamente

## Badge Status

Aggiungi questi badge al README principale:

```markdown
[![Tests](https://github.com/YOURUSERNAME/pypolicyd/actions/workflows/test.yml/badge.svg)](https://github.com/YOURUSERNAME/pypolicyd/actions/workflows/test.yml)
[![Build Debian Package](https://github.com/YOURUSERNAME/pypolicyd/actions/workflows/build-deb.yml/badge.svg)](https://github.com/YOURUSERNAME/pypolicyd/actions/workflows/build-deb.yml)
```

## Uso Local Development

### Setup Locale
```bash
# Installa dipendenze di sviluppo
sudo apt-get install build-essential devscripts debhelper dh-python python3-all lintian

# Installa dipendenze Python
pip3 install PyYAML black flake8

# Test rapidi
python3 test_new_config.py

# Build locale
chmod +x build-package.sh
./build-package.sh
```

### Test CLI
```bash
# Test configurazione
python3 src/pypolicyd/smtp-policy-ctl.py --config etc/pypolicyd/main.yml test-config

# Test policy
python3 src/pypolicyd/smtp-policy-ctl.py --config etc/pypolicyd/main.yml show-policy admin@example.com
```

## Deployment

### Installazione da Build Locale
```bash
sudo dpkg -i build/pypolicyd_*.deb
sudo apt-get install -f  # Se necessario
sudo systemctl enable pypolicyd
sudo systemctl start pypolicyd
```

### Installazione da GitHub Release
```bash
# Download dell'ultima release
curl -LO https://github.com/YOURUSERNAME/pypolicyd/releases/latest/download/pypolicyd_*_all.deb

# Installazione
sudo dpkg -i pypolicyd_*_all.deb
sudo apt-get install -f
```

## Troubleshooting Workflow

### Build Fallisce
1. Controlla i log del workflow nella sezione "Actions"
2. Verifica che tutti i file YAML siano validi
3. Controlla sintassi Python con `python3 -m py_compile`
4. Esegui test localmente: `python3 test_new_config.py`

### Test Falliscono
1. Verifica dipendenze Python: `pip3 install PyYAML`
2. Controlla configurazioni in `etc/pypolicyd/`
3. Verifica permessi file
4. Esegui test specifici manualmente

### Release Non Funziona
1. Assicurati che il tag segua il formato `v*` (es. `v1.0.0`)
2. Verifica permessi del token GITHUB_TOKEN
3. Controlla che tutti i workflow precedenti siano passati

## Configurazione Avanzata

### Personalizza Versioni Ubuntu
Modifica `.github/workflows/build-deb.yml`:
```yaml
strategy:
  matrix:
    ubuntu-version: ['20.04', '22.04', '24.04']  # Aggiungi/rimuovi versioni
```

### Personalizza Versioni Python
Modifica il test matrix:
```yaml
strategy:
  matrix:
    python-version: ['3.8', '3.9', '3.10', '3.11', '3.12']
```
