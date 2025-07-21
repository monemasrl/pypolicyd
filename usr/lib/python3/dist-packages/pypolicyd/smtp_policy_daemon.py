#!/usr/bin/env python3
"""
SMTP Policy Daemon in Python
Gestisce rate limiting e policy per Postfix tramite configurazione YAML
"""

import asyncio
import signal
import sys
import os
import time
import yaml
import re
from typing import Dict, Any, Optional, Tuple, List
import json
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import logging
import re


class RateLimit:
    """Gestisce rate limit con formato flessibile come '10/1m', '100/5m', etc."""
    
    UNIT_MULTIPLIERS = {
        's': 1,           # secondi
        'm': 60,          # minuti  
        'h': 3600,        # ore
        'd': 86400,       # giorni
        'M': 2592000,     # mesi (30 giorni)
    }
    
    def __init__(self, rate_str: str):
        self.rate_str = rate_str
        self.count, self.window_seconds = self._parse_rate(rate_str)
        
    def _parse_rate(self, rate_str: str) -> Tuple[int, int]:
        """Parse rate string formato 'count/time_unit'"""
        pattern = r'^(\d+)/(\d+)([smhdM])$'
        match = re.match(pattern, rate_str)
        
        if not match:
            raise ValueError(f"Invalid rate format: {rate_str}. Expected format: 'count/time_unit' (e.g., '10/1m', '100/5m')")
            
        count = int(match.group(1))
        time_value = int(match.group(2))
        time_unit = match.group(3)
        
        if time_unit not in self.UNIT_MULTIPLIERS:
            raise ValueError(f"Invalid time unit: {time_unit}. Valid units: {list(self.UNIT_MULTIPLIERS.keys())}")
            
        window_seconds = time_value * self.UNIT_MULTIPLIERS[time_unit]
        return count, window_seconds
    
    def __str__(self):
        return f"RateLimit({self.rate_str}: {self.count} per {self.window_seconds}s)"


class MultiWindowRateTracker:
    """Traccia rate limiting su multiple finestre temporali"""
    
    def __init__(self, rate_limits: List[RateLimit]):
        self.rate_limits = rate_limits
        self.counters: Dict[Tuple[str, float], List[float]] = {}  # key: (user, window_seconds) -> list of timestamps
        
    def check_rate_limits(self, user: str, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Controlla se l'utente ha superato qualche rate limit
        Returns: (is_allowed, reason)
        """
        if current_time is None:
            current_time = datetime.now()
            
        current_timestamp = current_time.timestamp()
        
        for rate_limit in self.rate_limits:
            key = (user, rate_limit.window_seconds)
            
            # Inizializza counter se non esiste
            if key not in self.counters:
                self.counters[key] = []
                
            # Rimuovi timestamp vecchi fuori dalla finestra
            cutoff_time = current_timestamp - rate_limit.window_seconds
            self.counters[key] = [ts for ts in self.counters[key] if ts > cutoff_time]
            
            # Controlla se abbiamo superato il limite
            current_count = len(self.counters[key])
            if current_count >= rate_limit.count:
                return False, f"Rate limit exceeded: {current_count}/{rate_limit.count} in {rate_limit.rate_str}"
                
        return True, "OK"
    
    def record_request(self, user: str, current_time: Optional[datetime] = None):
        """Registra una richiesta per l'utente"""
        if current_time is None:
            current_time = datetime.now()
            
        current_timestamp = current_time.timestamp()
        
        for rate_limit in self.rate_limits:
            key = (user, rate_limit.window_seconds)
            if key not in self.counters:
                self.counters[key] = []
            self.counters[key].append(current_timestamp)
    
    def cleanup_old_counters(self, current_time: Optional[datetime] = None):
        """Pulisce i counter vecchi per risparmiare memoria"""
        if current_time is None:
            current_time = datetime.now()
            
        current_timestamp = current_time.timestamp()
        
        for key in list(self.counters.keys()):
            user, window_seconds = key
            cutoff_time = current_timestamp - window_seconds
            self.counters[key] = [ts for ts in self.counters[key] if ts > cutoff_time]
            
            # Rimuovi chiavi vuote
            if not self.counters[key]:
                del self.counters[key]


class PolicyConfig:
    """Gestione configurazione YAML"""
    
    def __init__(self, config_file: str, debug: bool = False):
        self.config_file = config_file
        self.debug = debug
        self.config: Dict[str, Any] = {}
        self.policy_rules: Dict[str, Any] = {}
        self.load_config()
    
    def load_config(self):
        """Carica la configurazione dal file YAML"""
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            logging.info(f"Configurazione caricata da {self.config_file}")
            
            # Debug della configurazione solo se abilitato
            if self.debug:
                self._debug_config()
            
            # Carica le policy rules dal file o directory separato
            self._load_policy_rules()
            
        except Exception as e:
            logging.error(f"Errore caricamento configurazione: {e}")
            self.config = {}
            self.policy_rules = {}
    
    def _debug_config(self):
        """Debug della configurazione caricata"""
        if self.config:
            logging.info("=== DEBUG CONFIGURAZIONE ===")
            logging.info(f"Sezioni disponibili: {list(self.config.keys())}")
            
            # Debug sezione smtp_policy
            smtp_config = self.config.get('smtp_policy', {})
            if smtp_config:
                logging.info(f"smtp_policy keys: {list(smtp_config.keys())}")
                logging.info(f"log_request: {smtp_config.get('log_request', 'N/A')}")
                logging.info(f"enable_advanced_rates: {smtp_config.get('enable_advanced_rates', 'N/A')}")
                logging.info(f"policy_rules_file: {smtp_config.get('policy_rules_file', 'N/A')}")
            else:
                logging.warning("Sezione 'smtp_policy' non trovata!")
            
            # Debug sezione daemon
            daemon_config = self.config.get('daemon', {})
            if daemon_config:
                logging.info(f"daemon keys: {list(daemon_config.keys())}")
                logging.info(f"pid_file: {daemon_config.get('pid_file', 'N/A')}")
            else:
                logging.warning("Sezione 'daemon' non trovata!")
            
            # Debug default_policy
            default_policy = self.config.get('default_policy', {})
            if default_policy:
                logging.info(f"default_policy keys: {list(default_policy.keys())}")
            else:
                logging.warning("Sezione 'default_policy' non trovata!")
            
            logging.info("=== FINE DEBUG CONFIGURAZIONE ===")
        else:
            logging.error("Configurazione vuota!")
    
    def _load_policy_rules(self):
        """Carica le policy rules da file o directory"""
        from pathlib import Path
        
        policy_rules_file = self.config.get('smtp_policy', {}).get('policy_rules_file', '/etc/pypolicyd/policy-rules.yml')
        self.policy_rules = {}
        
        try:
            if policy_rules_file.endswith('.d') or Path(policy_rules_file).is_dir():
                # Carica da directory
                rules_dir = Path(policy_rules_file)
                if rules_dir.exists():
                    for yaml_file in sorted(rules_dir.glob('*.yml')):
                        with open(yaml_file, 'r') as f:
                            file_rules = yaml.safe_load(f) or {}
                            self.policy_rules.update(file_rules)
                            logging.info(f"Policy rules caricate da {yaml_file}")
            else:
                # Carica da file singolo
                if Path(policy_rules_file).exists():
                    with open(policy_rules_file, 'r') as f:
                        self.policy_rules = yaml.safe_load(f) or {}
                        logging.info(f"Policy rules caricate da {policy_rules_file}")
        except Exception as e:
            logging.error(f"Errore caricamento policy rules: {e}")
            self.policy_rules = {}
        
        # Debug policy rules caricate solo se abilitato
        if self.debug:
            policy_rules_file = self.config.get('smtp_policy', {}).get('policy_rules_file', '/etc/pypolicyd/policy-rules.yml')
            logging.info(f"Policy rules file/directory: {policy_rules_file}")
            logging.info(f"Policy rules path exists: {Path(policy_rules_file).exists()}")
            
            if self.policy_rules:
                logging.info(f"Policy rules caricate: {len(self.policy_rules)} regole")
                for key in self.policy_rules.keys():
                    logging.info(f"  - {key}")
            else:
                logging.warning("Nessuna policy rule caricata!")
    
    def get_policy_for_user(self, sasl_username: str) -> Dict[str, Any]:
        """Ottiene la policy per un utente specifico con validazione gerarchica"""
        if not sasl_username:
            return self.config.get('default_policy', {})
        
        # Estrai dominio dall'email
        domain = sasl_username.split('@')[-1] if '@' in sasl_username else ''
        
        # 1. Cerca policy utente specifica
        if sasl_username in self.policy_rules:
            user_policy = self.policy_rules[sasl_username]
            # Valida contro policy dominio
            domain_pattern = f"*@{domain}"
            if domain_pattern in self.policy_rules:
                domain_policy = self.policy_rules[domain_pattern]
                return self._validate_user_policy_against_domain(user_policy, domain_policy, sasl_username)
            return user_policy
        
        # 2. Cerca policy dominio
        domain_pattern = f"*@{domain}"
        if domain_pattern in self.policy_rules:
            return self.policy_rules[domain_pattern]
        
        # 3. Fallback a policy default
        return self.config.get('default_policy', {})
    
    def _validate_user_policy_against_domain(self, user_policy: Dict[str, Any], 
                                           domain_policy: Dict[str, Any], 
                                           username: str) -> Dict[str, Any]:
        """Valida che la policy utente non superi quella del dominio"""
        validated_policy = {}
        
        # Validazione rate_limits avanzati
        if 'rate_limits' in user_policy and 'rate_limits' in domain_policy:
            validated_policy['rate_limits'] = self._validate_rate_limits(
                user_policy['rate_limits'], domain_policy['rate_limits'], username
            )
        elif 'rate_limits' in user_policy:
            # Se il dominio ha solo legacy limits, converti per confronto
            domain_rate_limits = []
            if 'rate_limit' in domain_policy and domain_policy['rate_limit'] > 0:
                domain_rate_limits.append(f"{domain_policy['rate_limit']}/1h")
            if 'daily_limit' in domain_policy and domain_policy['daily_limit'] > 0:
                domain_rate_limits.append(f"{domain_policy['daily_limit']}/1d")
            
            if domain_rate_limits:
                validated_policy['rate_limits'] = self._validate_rate_limits(
                    user_policy['rate_limits'], domain_rate_limits, username
                )
            else:
                validated_policy['rate_limits'] = user_policy['rate_limits']
        
        # Validazione legacy rate limits
        if 'rate_limit' in user_policy:
            domain_rate_limit = domain_policy.get('rate_limit', float('inf'))
            if user_policy['rate_limit'] > domain_rate_limit:
                logging.warning(f"POLICY_CONFLICT: User {username} rate_limit ({user_policy['rate_limit']}) "
                              f"exceeds domain limit ({domain_rate_limit}). Using domain limit.")
                validated_policy['rate_limit'] = domain_rate_limit
            else:
                validated_policy['rate_limit'] = user_policy['rate_limit']
        
        if 'daily_limit' in user_policy:
            domain_daily_limit = domain_policy.get('daily_limit', float('inf'))
            if user_policy['daily_limit'] > domain_daily_limit:
                logging.warning(f"POLICY_CONFLICT: User {username} daily_limit ({user_policy['daily_limit']}) "
                              f"exceeds domain limit ({domain_daily_limit}). Using domain limit.")
                validated_policy['daily_limit'] = domain_daily_limit
            else:
                validated_policy['daily_limit'] = user_policy['daily_limit']
        
        # Validazione max_recipients
        if 'max_recipients' in user_policy:
            domain_max_recipients = domain_policy.get('max_recipients', float('inf'))
            if user_policy['max_recipients'] > domain_max_recipients:
                logging.warning(f"POLICY_CONFLICT: User {username} max_recipients ({user_policy['max_recipients']}) "
                              f"exceeds domain limit ({domain_max_recipients}). Using domain limit.")
                validated_policy['max_recipients'] = domain_max_recipients
            else:
                validated_policy['max_recipients'] = user_policy['max_recipients']
        
        # Validazione max_size
        if 'max_size' in user_policy:
            user_size = self._parse_size(user_policy['max_size'])
            domain_size = self._parse_size(domain_policy.get('max_size', '0'))
            
            if domain_size > 0 and user_size > domain_size:
                logging.warning(f"POLICY_CONFLICT: User {username} max_size ({user_policy['max_size']}) "
                              f"exceeds domain limit ({domain_policy.get('max_size', '0')}). Using domain limit.")
                validated_policy['max_size'] = domain_policy.get('max_size', '0')
            else:
                validated_policy['max_size'] = user_policy['max_size']
        
        return validated_policy
    
    def _validate_rate_limits(self, user_rate_limits: List[str], 
                            domain_rate_limits: List[str], 
                            username: str) -> List[str]:
        """Valida che i rate limits utente non superino quelli del dominio"""
        validated_limits = []
        
        # Crea mappatura dei limiti del dominio per finestra temporale
        domain_limits_map = {}
        for rate_str in domain_rate_limits:
            try:
                rate = RateLimit(rate_str)
                # Usa window_seconds come chiave per il confronto
                domain_limits_map[rate.window_seconds] = rate
            except ValueError:
                continue
        
        # Valida ogni limite utente
        for rate_str in user_rate_limits:
            try:
                user_rate = RateLimit(rate_str)
                
                if user_rate.window_seconds in domain_limits_map:
                    domain_rate = domain_limits_map[user_rate.window_seconds]
                    if user_rate.count > domain_rate.count:
                        logging.warning(f"POLICY_CONFLICT: User {username} rate_limit ({rate_str}) "
                                      f"exceeds domain limit ({domain_rate.rate_str}). Using domain limit.")
                        validated_limits.append(domain_rate.rate_str)
                    else:
                        validated_limits.append(rate_str)
                else:
                    # Nessun limite di dominio per questa finestra temporale
                    validated_limits.append(rate_str)
                    
            except ValueError as e:
                logging.warning(f"Invalid rate limit format '{rate_str}' for user {username}: {e}")
        
        return validated_limits
    
    def _parse_size(self, size_str: str) -> int:
        """Converte string size (es. '10M', '100K') in bytes"""
        if not size_str or size_str == '0':
            return 0
            
        size_str = size_str.upper().strip()
        
        # Rimuovi 'B' finale se presente
        if size_str.endswith('B'):
            size_str = size_str[:-1]
        
        # Trova l'unità
        if size_str.endswith('K'):
            return int(size_str[:-1]) * 1024
        elif size_str.endswith('M'):
            return int(size_str[:-1]) * 1024 * 1024
        elif size_str.endswith('G'):
            return int(size_str[:-1]) * 1024 * 1024 * 1024
        else:
            # Assume bytes
            return int(size_str)

class RateLimitStore:
    """Gestione SQLite per rate limiting"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inizializza il database SQLite"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                key TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                expires TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_expires ON rate_limits(expires)
        ''')
        
        conn.commit()
        conn.close()
    
    def cleanup_expired(self):
        """Rimuove entry scadute"""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now()
        conn.execute('DELETE FROM rate_limits WHERE expires < ?', (now,))
        conn.commit()
        conn.close()
    
    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Controlla rate limit per una chiave
        Returns: (is_allowed, current_count)
        """
        conn = sqlite3.connect(self.db_path)
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        
        # Cleanup entry scadute per questa chiave
        conn.execute('DELETE FROM rate_limits WHERE key = ? AND expires < ?', (key, now))
        
        # Conta richieste nella finestra temporale
        cursor = conn.execute(
            'SELECT count, first_seen FROM rate_limits WHERE key = ? AND first_seen >= ?',
            (key, window_start)
        )
        result = cursor.fetchone()
        
        if result:
            current_count, first_seen = result
            # Incrementa contatore
            new_count = current_count + 1
            expires = datetime.fromisoformat(first_seen) + timedelta(seconds=window_seconds)
            
            conn.execute(
                'UPDATE rate_limits SET count = ?, last_seen = ?, expires = ? WHERE key = ?',
                (new_count, now, expires, key)
            )
        else:
            # Prima richiesta nella finestra
            new_count = 1
            expires = now + timedelta(seconds=window_seconds)
            
            conn.execute(
                'INSERT OR REPLACE INTO rate_limits (key, count, first_seen, last_seen, expires) VALUES (?, ?, ?, ?, ?)',
                (key, new_count, now, now, expires)
            )
        
        conn.commit()
        conn.close()
        
        is_allowed = new_count <= limit
        return is_allowed, new_count

class PolicyDaemon:
    """Daemon principale per policy SMTP"""
    
    def __init__(self, config_file: str, db_path: str, host: str = '127.0.0.1', port: int = 10040, debug: bool = False):
        self.config_file = config_file
        self.host = host
        self.port = port
        self.server = None
        self.pid_file = None
        self.debug = debug
        
        # Inizializza componenti
        self.policy_config = PolicyConfig(config_file, debug=debug)
        self.rate_store = RateLimitStore(db_path)
        
        # Advanced rate limiting - tracker globale
        self.rate_tracker: Optional[MultiWindowRateTracker] = None
        self.enable_advanced_rates = True
        self.cleanup_interval = 300
        
        # Setup logging basato sulla configurazione
        self.setup_logging()
        self.logger = logging.getLogger('policy-daemon')
        
        # Configurazione logging richieste
        smtp_config = self.policy_config.config.get('smtp_policy', {})
        self.log_request = smtp_config.get('log_request', 'rejected').lower()
        self.enable_advanced_rates = smtp_config.get('enable_advanced_rates', True)
        self.cleanup_interval = smtp_config.get('cleanup_interval', 300)
        
        # Setup signal handlers
        signal.signal(signal.SIGHUP, self.reload_config)
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)
        
        # Setup PID file path
        daemon_config = self.policy_config.config.get('daemon', {})
        self.pid_file = daemon_config.get('pid_file', '/var/run/pypolicyd/pypolicyd.pid')
    
    def create_pid_file(self):
        """Crea il file PID"""
        try:
            from pathlib import Path
            pid_dir = Path(self.pid_file).parent
            pid_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            
            self.logger.info(f"File PID creato: {self.pid_file}")
        except Exception as e:
            self.logger.error(f"Errore nella creazione del file PID: {e}")
    
    def remove_pid_file(self):
        """Rimuove il file PID"""
        try:
            if self.pid_file and os.path.exists(self.pid_file):
                os.unlink(self.pid_file)
                self.logger.info(f"File PID rimosso: {self.pid_file}")
        except Exception as e:
            self.logger.error(f"Errore nella rimozione del file PID: {e}")
    
    def check_already_running(self):
        """Controlla se il daemon è già in esecuzione"""
        if self.pid_file and os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)  # Controlla se il processo esiste
                self.logger.error(f"Il demone è già in esecuzione (PID: {pid})")
                return True
            except (OSError, ValueError):
                # Il processo non esiste, rimuovi il file PID orfano
                os.unlink(self.pid_file)
        return False
    
    def setup_logging(self):
        """Configura il logging basato sulla configurazione"""
        smtp_config = self.policy_config.config.get('smtp_policy', {})
        
        log_level = getattr(logging, smtp_config.get('log_level', 'INFO').upper())
        log_file = smtp_config.get('log_file', '')
        log_to_syslog = smtp_config.get('log_to_syslog', False)
        syslog_facility = smtp_config.get('syslog_facility', 'mail')
        
        # Clear any existing handlers
        logging.getLogger().handlers.clear()
        
        # Setup logging format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        if log_to_syslog:
            # Log to syslog
            try:
                from logging.handlers import SysLogHandler
                
                # Map facility name to syslog constant
                facility_map = {
                    'mail': SysLogHandler.LOG_MAIL,
                    'daemon': SysLogHandler.LOG_DAEMON,
                    'local0': SysLogHandler.LOG_LOCAL0,
                    'local1': SysLogHandler.LOG_LOCAL1,
                    'local2': SysLogHandler.LOG_LOCAL2,
                    'local3': SysLogHandler.LOG_LOCAL3,
                    'local4': SysLogHandler.LOG_LOCAL4,
                    'local5': SysLogHandler.LOG_LOCAL5,
                    'local6': SysLogHandler.LOG_LOCAL6,
                    'local7': SysLogHandler.LOG_LOCAL7,
                }
                
                facility = facility_map.get(syslog_facility, SysLogHandler.LOG_MAIL)
                syslog_handler = SysLogHandler(address='/dev/log', facility=facility)
                
                # Syslog format (no timestamp, syslog provides it)
                syslog_formatter = logging.Formatter(
                    'pypolicyd[%(process)d]: %(message)s'
                )
                syslog_handler.setFormatter(syslog_formatter)
                syslog_handler.setLevel(log_level)
                
                logging.getLogger().addHandler(syslog_handler)
                logging.getLogger().setLevel(log_level)
                
            except Exception as e:
                # Fallback to stdout if syslog fails
                print(f"Warning: Could not setup syslog, falling back to stdout: {e}")
                self.setup_stdout_logging(log_level, formatter)
                
        elif log_file:
            # Log to file
            try:
                from logging.handlers import RotatingFileHandler
                
                # Create log directory if needed
                import os
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(log_level)
                
                logging.getLogger().addHandler(file_handler)
                logging.getLogger().setLevel(log_level)
                
            except Exception as e:
                # Fallback to stdout if file logging fails
                print(f"Warning: Could not setup file logging, falling back to stdout: {e}")
                self.setup_stdout_logging(log_level, formatter)
        else:
            # Default: log to stdout (systemd journal)
            self.setup_stdout_logging(log_level, formatter)
    
    def setup_stdout_logging(self, log_level, formatter):
        """Setup logging to stdout (for systemd)"""
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        
        logging.getLogger().addHandler(console_handler)
        logging.getLogger().setLevel(log_level)
    
    def reload_config(self, signum, frame):
        """Ricarica configurazione su SIGHUP"""
        self.logger.info("Ricaricamento configurazione...")
        self.policy_config.load_config()
        
        # Ricarica configurazione logging richieste e advanced rates
        smtp_config = self.policy_config.config.get('smtp_policy', {})
        self.log_request = smtp_config.get('log_request', 'rejected').lower()
        self.enable_advanced_rates = smtp_config.get('enable_advanced_rates', True)
        self.cleanup_interval = smtp_config.get('cleanup_interval', 300)
        
        # Reset rate tracker se la configurazione è cambiata
        self.rate_tracker = None
        
        self.logger.info(f"Log request level: {self.log_request}, Advanced rates: {self.enable_advanced_rates}")
    
    def _debug_daemon_config(self):
        """Debug della configurazione del daemon all'avvio"""
        self.logger.info("=== DEBUG DAEMON CONFIGURAZIONE ===")
        self.logger.info(f"Config file: {self.config_file}")
        self.logger.info(f"Host: {self.host}")
        self.logger.info(f"Port: {self.port}")
        self.logger.info(f"PID file: {self.pid_file}")
        self.logger.info(f"Log request: {self.log_request}")
        self.logger.info(f"Enable advanced rates: {self.enable_advanced_rates}")
        self.logger.info(f"Cleanup interval: {self.cleanup_interval}")
        
        # Debug policy default
        default_policy = self.policy_config.get_policy_for_user('')
        self.logger.info(f"Default policy: {default_policy}")
        
        # Test alcune policy utenti di esempio
        test_users = ['admin@example.com', 'user@test.com', 'test@company.com']
        for user in test_users:
            policy = self.policy_config.get_policy_for_user(user)
            if policy != default_policy:
                self.logger.info(f"Policy specifica per {user}: {policy}")
        
        self.logger.info("=== FINE DEBUG DAEMON ===")
    
    def _print_startup_info(self):
        """Stampa informazioni di avvio sullo standard output"""
        print(f"\n{'='*60}")
        print(f"  PyPolicyd - SMTP Policy Daemon")
        print(f"{'='*60}")
        print(f"📝 Config file: {self.config_file}")
        print(f"🌐 Listening on: {self.host}:{self.port}")
        print(f"📁 PID file: {self.pid_file}")
        print(f"🔧 Log requests: {self.log_request}")
        print(f"⚡ Advanced rates: {self.enable_advanced_rates}")
        print(f"🧹 Cleanup interval: {self.cleanup_interval}s")
        
        # Mostra policy default
        default_policy = self.policy_config.get_policy_for_user('')
        if default_policy:
            print(f"📋 Default policy:")
            if 'max_recipients' in default_policy:
                print(f"   • Max recipients: {default_policy['max_recipients']}")
            if 'max_size' in default_policy:
                print(f"   • Max size: {default_policy['max_size']}")
            if 'rate_limits' in default_policy:
                print(f"   • Rate limits: {', '.join(default_policy['rate_limits'])}")
        
        # Mostra policy rules caricate
        if self.policy_config.policy_rules:
            print(f"📚 Policy rules loaded: {len(self.policy_config.policy_rules)} rules")
            domains = set()
            users = set()
            for key in self.policy_config.policy_rules.keys():
                if key.startswith('*@'):
                    domains.add(key[2:])  # Rimuovi '*@'
                elif '@' in key:
                    users.add(key)
            
            if domains:
                print(f"   • Domains: {', '.join(sorted(domains))}")
            if users:
                print(f"   • Specific users: {len(users)} configured")
        else:
            print("⚠️  No policy rules loaded")
        
        print(f"{'='*60}")
    
    def _print_debug_startup_info(self):
        """Stampa informazioni di debug dettagliate sullo standard output"""
        print(f"\n{'='*60}")
        print(f"  DEBUG: Detailed Configuration Info")
        print(f"{'='*60}")
        
        # Sezioni configurazione
        if self.policy_config.config:
            print(f"📋 Configuration sections: {list(self.policy_config.config.keys())}")
            
            # Dettagli smtp_policy
            smtp_config = self.policy_config.config.get('smtp_policy', {})
            if smtp_config:
                print(f"🔧 SMTP Policy config:")
                for key, value in smtp_config.items():
                    print(f"   • {key}: {value}")
            
            # Dettagli daemon
            daemon_config = self.policy_config.config.get('daemon', {})
            if daemon_config:
                print(f"⚙️  Daemon config:")
                for key, value in daemon_config.items():
                    print(f"   • {key}: {value}")
        
        # Policy rules dettagliate
        if self.policy_config.policy_rules:
            print(f"📚 All policy rules:")
            for key, policy in self.policy_config.policy_rules.items():
                print(f"   • {key}:")
                if 'max_recipients' in policy:
                    print(f"     - Max recipients: {policy['max_recipients']}")
                if 'max_size' in policy:
                    print(f"     - Max size: {policy['max_size']}")
                if 'rate_limits' in policy:
                    print(f"     - Rate limits: {policy['rate_limits']}")
        
        print(f"{'='*60}")
    
    def _get_rate_tracker_for_user(self, user: str) -> Optional['MultiWindowRateTracker']:
        """Ottiene o crea il rate tracker per un utente"""
        # Trova la policy per l'utente
        policy = self.policy_config.get_policy_for_user(user)
        
        if self.enable_advanced_rates and 'rate_limits' in policy:
            # Crea tracker se non esiste ancora
            if self.rate_tracker is None:
                rate_limits = []
                for rate_str in policy['rate_limits']:
                    try:
                        rate_limits.append(RateLimit(rate_str))
                    except ValueError as e:
                        self.logger.warning(f"Invalid rate limit format '{rate_str}' for user {user}: {e}")
                        
                if rate_limits:
                    self.rate_tracker = MultiWindowRateTracker(rate_limits)
                    
            return self.rate_tracker
                    
        return None
    
    def _check_legacy_rate_limits(self, user: str, policy: Dict[str, Any]) -> Tuple[bool, str]:
        """Controlla rate limits con formato legacy usando RateLimitStore"""
        # Controllo rate limiting orario
        rate_limit = policy.get('rate_limit', 0)
        if rate_limit > 0:
            allowed, count = self.rate_store.check_rate_limit(
                f"hourly:{user}", rate_limit, 3600
            )
            if not allowed:
                return False, f"REJECT Rate limit exceeded ({count}/{rate_limit}) for {user}"
        
        # Controllo rate limiting giornaliero
        daily_limit = policy.get('daily_limit', 0)
        if daily_limit > 0:
            allowed, count = self.rate_store.check_rate_limit(
                f"daily:{user}", daily_limit, 86400
            )
            if not allowed:
                return False, f"REJECT Daily limit exceeded ({count}/{daily_limit}) for {user}"
                
        return True, "OK"
    
    def _check_domain_rate_limits(self, user: str) -> Tuple[bool, str]:
        """Controlla i rate limits a livello di dominio"""
        # Estrai dominio dall'email
        domain = user.split('@')[-1] if '@' in user else ''
        
        # Cerca policy del dominio
        domain_pattern = f"*@{domain}"
        domain_policy = self.policy_config.policy_rules.get(domain_pattern)
        
        if not domain_policy:
            return True, "OK"
        
        # Controlla rate limits avanzati del dominio
        if self.enable_advanced_rates and 'rate_limits' in domain_policy:
            # Usa il nuovo sistema multi-window
            try:
                rate_limits = []
                for rate_str in domain_policy['rate_limits']:
                    rate_limits.append(RateLimit(rate_str))
                
                domain_tracker = MultiWindowRateTracker(rate_limits)
                allowed, msg = domain_tracker.check_rate_limits(f"domain:{domain}")
                
                if not allowed:
                    return False, f"REJECT Domain {msg} for domain {domain}"
                    
            except ValueError as e:
                self.logger.warning(f"Invalid domain rate limit format for {domain}: {e}")
        
        # Fallback a rate limits legacy se definiti
        else:
            # Supporto legacy rate_limit e daily_limit
            rate_limit = domain_policy.get('rate_limit', 0)
            if rate_limit > 0:
                allowed, count = self.rate_store.check_rate_limit(
                    f"domain_hourly:{domain}", rate_limit, 3600
                )
                if not allowed:
                    return False, f"REJECT Domain rate limit exceeded ({count}/{rate_limit}) for domain {domain}"
            
            daily_limit = domain_policy.get('daily_limit', 0)
            if daily_limit > 0:
                allowed, count = self.rate_store.check_rate_limit(
                    f"domain_daily:{domain}", daily_limit, 86400
                )
                if not allowed:
                    return False, f"REJECT Domain daily limit exceeded ({count}/{daily_limit}) for domain {domain}"
        
        return True, "OK"
    
    def _record_domain_request(self, user: str):
        """Registra una richiesta per i contatori del dominio"""
        domain = user.split('@')[-1] if '@' in user else ''
        
        # Cerca policy del dominio
        domain_pattern = f"*@{domain}"
        domain_policy = self.policy_config.policy_rules.get(domain_pattern)
        
        if not domain_policy:
            return
        
        # Registra nei contatori del dominio con nuovo sistema
        if self.enable_advanced_rates and 'rate_limits' in domain_policy:
            try:
                rate_limits = []
                for rate_str in domain_policy['rate_limits']:
                    rate_limits.append(RateLimit(rate_str))
                
                domain_tracker = MultiWindowRateTracker(rate_limits)
                domain_tracker.check_rate_limits(f"domain:{domain}")
                
            except ValueError as e:
                self.logger.warning(f"Invalid domain rate limit format for {domain}: {e}")
        
        # Supporto legacy
        if domain_policy.get('rate_limit', 0) > 0:
            self.rate_store.check_rate_limit(f"domain_hourly:{domain}", 1, 3600)
        
        if domain_policy.get('daily_limit', 0) > 0:
            self.rate_store.check_rate_limit(f"domain_daily:{domain}", 1, 86400)
    
    def _check_hierarchical_rate_limits(self, user: str, policy: Dict[str, Any]) -> Tuple[bool, str]:
        """Controlla rate limits con validazione gerarchica (dominio + utente)"""
        # Prima controlla i limiti del dominio
        domain_allowed, domain_msg = self._check_domain_rate_limits(user)
        if not domain_allowed:
            return False, domain_msg
        
        # Poi controlla i limiti dell'utente
        user_allowed, user_msg = self._check_legacy_rate_limits(user, policy)
        if not user_allowed:
            return False, user_msg
        
        # Se entrambi OK, registra per entrambi i livelli
        self._record_domain_request(user)
        
        return True, "OK"
    
    async def start_server(self):
        """Avvia il server policy"""
        # Controlla se è già in esecuzione
        if self.check_already_running():
            return
            
        # Crea PID file
        self.create_pid_file()
        
        try:
            # Stampa informazioni di avvio sullo standard output
            self._print_startup_info()
            
            # Stampa debug dettagliato se abilitato
            if self.debug:
                self._print_debug_startup_info()
            
            self.logger.info(f"Avvio server policy su {self.host}:{self.port}")
            
            # Debug configurazione se abilitato (per log file)
            if self.debug:
                self._debug_daemon_config()
            
            self.server = await asyncio.start_server(
                self.handle_policy_request,
                self.host,
                self.port
            )
            
            # Avvia task di pulizia periodica
            cleanup_task = asyncio.create_task(self.periodic_cleanup())
            
            print(f"✅ Server started successfully on {self.host}:{self.port}")
            print("   Press Ctrl+C to stop the daemon")
            
            self.logger.info(f"Server policy avviato su {self.host}:{self.port}")
            
            async with self.server:
                await self.server.serve_forever()
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            self.logger.error(f"Errore nel server policy: {e}")
            raise
        finally:
            # Rimuovi PID file alla chiusura
            self.remove_pid_file()
    
    def _get_rule_name_for_user(self, user: str) -> str:
        """Ottiene il nome della regola applicata per un utente"""
        if not user:
            return "default"
        
        # Cerca policy utente specifica
        if user in self.policy_config.policy_rules:
            return user
        
        # Cerca policy dominio
        domain = user.split('@')[-1] if '@' in user else ''
        domain_pattern = f"*@{domain}"
        if domain_pattern in self.policy_config.policy_rules:
            return domain_pattern
        
        return "default"
    
    def _log_policy_decision(self, request: Dict[str, str], action: str, rule_name: str, reason: str = ""):
        """Log della decisione policy nel nuovo formato Postfix-style"""
        sasl_username = request.get('sasl_username', '')
        sender = request.get('sender', '')
        recipient = request.get('recipient', '')
        size = int(request.get('size', 0))
        recipient_count = int(request.get('recipient_count', 1))
        queue_id = request.get('queue_id', '')  # ID del messaggio da Postfix
        
        # Formato: ID: [RULES] rule=<nome-rule>, user=<user>, sender=<sender>, recipient=<recipient>, size=N, nrcpt=M, action=ACTION
        if queue_id:
            log_msg = f"{queue_id}: [RULES] rule={rule_name}, user={sasl_username}, sender={sender}, recipient={recipient}, size={size}, nrcpt={recipient_count}, action={action}"
        else:
            log_msg = f"[RULES] rule={rule_name}, user={sasl_username}, sender={sender}, recipient={recipient}, size={size}, nrcpt={recipient_count}, action={action}"
        
        if reason:
            log_msg += f", reason={reason}"
        
        if action.startswith('REJECT'):
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)
    
    async def periodic_cleanup(self):
        """Task di pulizia periodica per i rate tracker"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                if self.rate_tracker:
                    self.rate_tracker.cleanup_old_counters()
                    self.logger.debug("Cleanup rate tracker completed")
                    
                # Pulizia del database SQLite
                self.rate_store.cleanup_expired()
                
            except Exception as e:
                self.logger.error(f"Errore durante cleanup periodico: {e}")
                await asyncio.sleep(60)  # Attendi un minuto prima di riprovare
    
    def shutdown(self, signum, frame):
        """Shutdown graceful"""
        print(f"\n{'='*60}")
        print(f"  Shutting down PyPolicyd...")
        print(f"{'='*60}")
        self.logger.info("Shutdown del daemon...")
        if self.server:
            self.server.close()
            print("✅ Server stopped")
        self.remove_pid_file()
        print("✅ PID file removed")
        print("👋 Goodbye!")
        sys.exit(0)
    
    async def handle_policy_request(self, reader, writer):
        """Gestisce una richiesta policy da Postfix"""
        client_address = writer.get_extra_info('peername')
        if client_address:
            hostname = client_address[0] if isinstance(client_address, tuple) else str(client_address)
            # Log connessione nel formato Postfix
            self.logger.info(f"connect from localhost[{hostname}]")
        
        try:
            # Leggi richiesta
            request_data = {}
            while True:
                line = await reader.readline()
                if not line:
                    break
                
                line = line.decode('utf-8').strip()
                if not line:
                    break
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    request_data[key] = value
            
            # Processa policy
            response = await self.process_policy(request_data)
            
            # Invia risposta
            writer.write(f"action={response}\n\n".encode('utf-8'))
            await writer.drain()
            
        except Exception as e:
            self.logger.error(f"Errore gestione richiesta: {e}")
            writer.write(b"action=DUNNO\n\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def process_policy(self, request: Dict[str, str]) -> str:
        """Processa una richiesta policy e ritorna azione"""
        
        # Estrai informazioni richiesta
        sasl_username = request.get('sasl_username', '')
        client_address = request.get('client_address', '')
        sender = request.get('sender', '')
        recipient = request.get('recipient', '')
        size = int(request.get('size', 0))
        recipient_count = int(request.get('recipient_count', 1))
        
        # Se non è autenticato, permetti (gestito da altre regole Postfix)  
        if not sasl_username:
            return 'DUNNO'
        
        # Ottieni policy per utente
        policy = self.policy_config.get_policy_for_user(sasl_username)
        rule_name = self._get_rule_name_for_user(sasl_username)
        
        if not policy:
            if self.log_request == 'all':
                self._log_policy_decision(request, "DUNNO", "default", "no policy found")
            return 'DUNNO'
        
        # Controllo dimensione messaggio
        max_size = self._parse_size(policy.get('max_size', '0'))
        if max_size > 0 and size > max_size:
            action = f"REJECT Message size {size} bytes exceeds limit {max_size} bytes"
            if self.log_request in ['all', 'rejected']:
                self._log_policy_decision(request, action, rule_name, "message size exceeded")
            return action
        
        # Controllo numero destinatari
        max_recipients = policy.get('max_recipients', 0)
        if max_recipients > 0 and recipient_count > max_recipients:
            action = f"REJECT Too many recipients ({recipient_count}), limit is {max_recipients}"
            if self.log_request in ['all', 'rejected']:
                self._log_policy_decision(request, action, rule_name, "too many recipients")
            return action
        
        # Controllo rate limiting
        if self.enable_advanced_rates:
            # Nuovo sistema multi-finestra
            tracker = self._get_rate_tracker_for_user(sasl_username)
            if tracker:
                # Prima controlla i limiti del dominio, poi quelli dell'utente
                domain_allowed, domain_msg = self._check_domain_rate_limits(sasl_username)
                if not domain_allowed:
                    if self.log_request in ['all', 'rejected']:
                        self._log_policy_decision(request, domain_msg, rule_name, "domain rate limit")
                    return domain_msg
                
                # Controlla rate limits dell'utente
                allowed, message = tracker.check_rate_limits(sasl_username)
                if not allowed:
                    action = f"REJECT {message}"
                    if self.log_request in ['all', 'rejected']:
                        self._log_policy_decision(request, action, rule_name, "rate limit exceeded")
                    return action
                else:
                    # Registra la richiesta sia per dominio che per utente
                    self._record_domain_request(sasl_username)
                    tracker.record_request(sasl_username)
                    if self.log_request == 'all':
                        self._log_policy_decision(request, "DUNNO", rule_name)
            else:
                # Fallback al sistema legacy con controllo gerarchico
                allowed, message = self._check_hierarchical_rate_limits(sasl_username, policy)
                if not allowed:
                    if self.log_request in ['all', 'rejected']:
                        self._log_policy_decision(request, message, rule_name, "rate limit exceeded")
                    return message
        else:
            # Sistema legacy con controllo gerarchico
            allowed, message = self._check_hierarchical_rate_limits(sasl_username, policy)
            if not allowed:
                if self.log_request in ['all', 'rejected']:
                    self._log_policy_decision(request, message, rule_name, "rate limit exceeded")
                return message
        
        # Log richiesta accettata se richiesto
        if self.log_request == 'all':
            self._log_policy_decision(request, "DUNNO", rule_name)
        
        return 'DUNNO'
    
    def _parse_size(self, size_str: str) -> int:
        """Converte stringa dimensione in bytes"""
        if not size_str:
            return 0
        
        size_str = size_str.upper()
        if size_str.endswith('K'):
            return int(size_str[:-1]) * 1024
        elif size_str.endswith('M'):
            return int(size_str[:-1]) * 1024 * 1024
        elif size_str.endswith('G'):
            return int(size_str[:-1]) * 1024 * 1024 * 1024
        else:
            return int(size_str)
    
    async def start(self):
        """Avvia il daemon"""
        self.logger.info(f"Avvio daemon su {self.host}:{self.port}")
        
        # Cleanup periodico ogni 5 minuti
        async def cleanup_task():
            while True:
                await asyncio.sleep(300)  # 5 minuti
                self.rate_store.cleanup_expired()
        
        # Avvia task cleanup
        asyncio.create_task(cleanup_task())
        
        # Avvia server
        self.server = await asyncio.start_server(
            self.handle_policy_request, self.host, self.port
        )
        
        self.logger.info(f"Daemon in ascolto su {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()

def main():
    """Entry point principale"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SMTP Policy Daemon')
    parser.add_argument('--config', '-c', default='/etc/pypolicyd/main.yml',
                       help='File configurazione YAML')
    parser.add_argument('--database', '-d', default='/var/lib/pypolicyd/policy.db',
                       help='Database SQLite')
    parser.add_argument('--host', default='127.0.0.1',
                       help='Indirizzo di bind')
    parser.add_argument('--port', '-p', type=int, default=10040,
                       help='Porta di ascolto')
    parser.add_argument('--daemon', action='store_true',
                       help='Esegui come daemon')
    parser.add_argument('--debug', action='store_true',
                       help='Abilita debug dettagliato della configurazione')
    
    args = parser.parse_args()
    
    # Carica configurazione per ottenere host e port se non specificati come argomenti
    config_data = {}
    try:
        with open(args.config, 'r') as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Could not load config file {args.config}: {e}")
    
    # Determina host e port: argomenti CLI hanno precedenza, poi config file, poi default
    smtp_config = config_data.get('smtp_policy', {})
    
    # Per il database, usa argomento CLI se specificato, altrimenti config file
    database_path = args.database
    if args.database == '/var/lib/pypolicyd/policy.db':  # valore default
        database_path = smtp_config.get('database', args.database)
    
    # Per host, usa argomento CLI se specificato, altrimenti config file  
    host = args.host
    if args.host == '127.0.0.1':  # valore default
        host = smtp_config.get('host', args.host)
    
    # Per port, usa argomento CLI se specificato, altrimenti config file
    port = args.port
    if args.port == 10040:  # valore default
        port = smtp_config.get('port', args.port)
    
    # Crea directory database se non esiste
    db_dir = Path(database_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    
    # Debug della configurazione usata
    if args.debug:
        print(f"Configuration resolution:")
        print(f"  Config file: {args.config}")
        print(f"  Database: {database_path} {'(from config)' if database_path != args.database else '(from CLI/default)'}")
        print(f"  Host: {host} {'(from config)' if host != args.host else '(from CLI/default)'}")
        print(f"  Port: {port} {'(from config)' if port != args.port else '(from CLI/default)'}")
        print()
    
    if args.daemon:
        # Fork per diventare daemon
        if os.fork() > 0:
            sys.exit(0)
        
        os.setsid()
        
        if os.fork() > 0:
            sys.exit(0)
        
        # Redirect stdin/stdout/stderr
        with open('/dev/null', 'r') as f:
            os.dup2(f.fileno(), sys.stdin.fileno())
        with open('/dev/null', 'w') as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
            os.dup2(f.fileno(), sys.stderr.fileno())
    
    # Avvia daemon
    daemon = PolicyDaemon(args.config, database_path, host, port, debug=args.debug)
    
    try:
        asyncio.run(daemon.start_server())
    except KeyboardInterrupt:
        print("\n🛑 Daemon stopped by user (Ctrl+C)")
        logging.info("Daemon fermato dall'utente")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logging.error(f"Errore daemon: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
