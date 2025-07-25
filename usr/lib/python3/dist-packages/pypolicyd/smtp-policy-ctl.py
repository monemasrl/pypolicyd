#!/usr/bin/env python3
"""
SMTP Policy Daemon Management Script
Utilità per gestire il daemon di policy SMTP - supporta SQLite e Redis
"""

import argparse
import sqlite3
import yaml
import sys
import os
import signal
import json
from datetime import datetime, timedelta
from pathlib import Path

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

def get_daemon_pid():
    """Ottiene il PID del daemon se attivo"""
    try:
        with open('/var/run/pypolicyd/pypolicyd.pid', 'r') as f:
            return int(f.read().strip())
    except:
        return None

def reload_config():
    """Ricarica la configurazione del daemon (SIGHUP)"""
    pid = get_daemon_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGHUP)
            print("Configurazione ricaricata")
            return True
        except:
            print("Errore nel ricaricamento configurazione")
            return False
    else:
        print("Daemon non in esecuzione")
        return False

def show_stats(db_path_or_config):
    """Mostra statistiche rate limiting (SQLite o Redis)"""
    
    # Determina se è un path SQLite o configurazione YAML
    if db_path_or_config.endswith('.db'):
        show_sqlite_stats(db_path_or_config)
    else:
        # Prova a caricare come configurazione YAML
        try:
            with open(db_path_or_config, 'r') as f:
                config = yaml.safe_load(f)
            
            daemon_config = config.get('daemon', {})
            store_type = daemon_config.get('rate_limit_store_type', 'sqlite')
            
            if store_type == 'redis':
                show_redis_stats(daemon_config)
            else:
                sqlite_path = daemon_config.get('database', '/var/lib/pypolicyd/rate_limits.db')
                show_sqlite_stats(sqlite_path)
                
        except Exception as e:
            print(f"Errore caricamento configurazione: {e}")
            # Fallback: tratta come path SQLite
            show_sqlite_stats(db_path_or_config)

def show_sqlite_stats(db_path):
    """Mostra statistiche SQLite"""
    if not os.path.exists(db_path):
        print("Database SQLite non trovato")
        return
    
    conn = sqlite3.connect(db_path)
    
    print("=== Statistiche Rate Limiting (SQLite) ===")
    
    # Top utenti per invii
    print("\nTop 10 utenti per numero invii:")
    cursor = conn.execute('''
        SELECT key, SUM(count) as total_count 
        FROM rate_limits 
        WHERE key LIKE 'hourly:%' 
        GROUP BY REPLACE(key, 'hourly:', '')
        ORDER BY total_count DESC 
        LIMIT 10
    ''')
    
    for row in cursor.fetchall():
        user = row[0].replace('hourly:', '')
        count = row[1]
        print(f"  {user}: {count} email")
    
    # Utenti vicini ai limiti
    print("\nUtenti vicini ai limiti orari:")
    cursor = conn.execute('''
        SELECT key, count, expires 
        FROM rate_limits 
        WHERE key LIKE 'hourly:%' AND count > 80
        ORDER BY count DESC
    ''')
    
    for row in cursor.fetchall():
        user = row[0].replace('hourly:', '')
        count = row[1]
        expires = row[2]
        print(f"  {user}: {count} email (scade: {expires})")
    
    conn.close()

def show_redis_stats(config):
    """Mostra statistiche Redis"""
    if not REDIS_AVAILABLE:
        print("Redis library non disponibile")
        return
    
    try:
        r = redis.Redis(
            host=config.get('redis_host', 'localhost'),
            port=config.get('redis_port', 6379),
            db=config.get('redis_db', 0),
            password=config.get('redis_password', None),
            decode_responses=True
        )
        
        # Test connessione
        r.ping()
        
        print("=== Statistiche Rate Limiting (Redis) ===")
        
        key_prefix = config.get('redis_key_prefix', 'pypolicyd:ratelimit:')
        pattern = f"{key_prefix}*"
        keys = r.keys(pattern)
        
        print(f"\nChiavi attive totali: {len(keys)}")
        
        if keys:
            print("\nTop rate limits attivi:")
            
            # Analizza le chiavi e raggruppa per utente
            user_stats = {}
            
            for key in keys[:50]:  # Limita per performance
                try:
                    data = r.get(key)
                    if data:
                        parsed = json.loads(data)
                        ttl = r.ttl(key)
                        
                        # Estrai nome utente dalla chiave
                        clean_key = key.replace(key_prefix, '')
                        if ':' in clean_key:
                            user_key = clean_key.split(':')[0]
                        else:
                            user_key = clean_key
                        
                        if user_key not in user_stats:
                            user_stats[user_key] = []
                        
                        user_stats[user_key].append({
                            'key': clean_key,
                            'count': parsed.get('count', 0),
                            'ttl': ttl,
                            'first_seen': parsed.get('first_seen', ''),
                            'last_seen': parsed.get('last_seen', '')
                        })
                except Exception as e:
                    continue
            
            # Mostra statistiche per utente
            for user, stats in sorted(user_stats.items())[:10]:
                total_count = sum(stat['count'] for stat in stats)
                print(f"\n  {user}: {total_count} richieste totali")
                for stat in stats[:3]:  # Mostra max 3 rate limits per utente
                    print(f"    {stat['key']}: {stat['count']} (TTL: {stat['ttl']}s)")
        
        # Statistiche Redis generali
        info = r.info()
        print(f"\nInfo Redis:")
        print(f"  Database size: {info.get('db0', {}).get('keys', 0)} chiavi totali")
        print(f"  Memoria usata: {info.get('used_memory_human', 'N/A')}")
        
    except redis.ConnectionError:
        print("❌ Impossibile connettersi a Redis")
    except Exception as e:
        print(f"❌ Errore Redis: {e}")

def reset_user_limits(db_path_or_config, username):
    """Reset limiti per un utente specifico (SQLite o Redis)"""
    
    # Determina se è SQLite o configurazione Redis
    if db_path_or_config.endswith('.db'):
        reset_sqlite_user_limits(db_path_or_config, username)
    else:
        try:
            with open(db_path_or_config, 'r') as f:
                config = yaml.safe_load(f)
            
            daemon_config = config.get('daemon', {})
            store_type = daemon_config.get('rate_limit_store_type', 'sqlite')
            
            if store_type == 'redis':
                reset_redis_user_limits(daemon_config, username)
            else:
                sqlite_path = daemon_config.get('database', '/var/lib/pypolicyd/rate_limits.db')
                reset_sqlite_user_limits(sqlite_path, username)
                
        except Exception as e:
            print(f"Errore: {e}")

def reset_sqlite_user_limits(db_path, username):
    """Reset limiti SQLite per un utente"""
    if not os.path.exists(db_path):
        print("Database non trovato")
        return
    
    conn = sqlite3.connect(db_path)
    
    # Reset tutti i limiti dell'utente
    cursor = conn.execute('DELETE FROM rate_limits WHERE key LIKE ?', (f'%{username}%',))
    deleted = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"Reset {deleted} rate limits per {username}")

def reset_redis_user_limits(config, username):
    """Reset limiti Redis per un utente"""
    if not REDIS_AVAILABLE:
        print("Redis library non disponibile")
        return
    
    try:
        r = redis.Redis(
            host=config.get('redis_host', 'localhost'),
            port=config.get('redis_port', 6379),
            db=config.get('redis_db', 0),
            password=config.get('redis_password', None),
            decode_responses=True
        )
        
        key_prefix = config.get('redis_key_prefix', 'pypolicyd:ratelimit:')
        pattern = f"{key_prefix}*{username}*"
        keys = r.keys(pattern)
        
        if keys:
            deleted = r.delete(*keys)
            print(f"Reset {deleted} rate limits per {username} da Redis")
        else:
            print(f"Nessun rate limit trovato per {username} in Redis")
            
    except redis.ConnectionError:
        print("❌ Impossibile connettersi a Redis")
    except Exception as e:
        print(f"❌ Errore Redis: {e}")

def cleanup_expired(db_path):
    """Rimuove record scaduti dal database"""
    if not os.path.exists(db_path):
        print("Database non trovato")
        return
    
    conn = sqlite3.connect(db_path)
    now = datetime.now()
    
    cursor = conn.execute('SELECT COUNT(*) FROM rate_limits WHERE expires < ?', (now,))
    expired_count = cursor.fetchone()[0]
    
    conn.execute('DELETE FROM rate_limits WHERE expires < ?', (now,))
    conn.commit()
    conn.close()
    
    print(f"Rimossi {expired_count} record scaduti")

def test_config(config_file):
    """Testa la validità del file di configurazione"""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validazioni base
        errors = []
        
        if 'default_policy' not in config:
            errors.append("Manca 'default_policy'")
        
        # Controlla se esiste il file delle policy rules
        policy_rules_file = config.get('daemon', {}).get('policy_rules_file', '/etc/pypolicyd/policy-rules.yml')
        
        # Se stiamo testando localmente, adatta i path
        if config_file.startswith('etc/'):
            # Path relativo per testing locale
            if policy_rules_file.startswith('/etc/pypolicyd/'):
                policy_rules_file = policy_rules_file.replace('/etc/pypolicyd/', 'etc/pypolicyd/')
        
        # Se è una directory, controlla che esista
        if policy_rules_file.endswith('.d') or os.path.isdir(policy_rules_file):
            if not os.path.exists(policy_rules_file):
                errors.append(f"Directory policy rules non trovata: {policy_rules_file}")
        else:
            # Se è un file, controlla che esista
            if not os.path.exists(policy_rules_file):
                errors.append(f"File policy rules non trovato: {policy_rules_file}")
        
        if errors:
            print("Errori nella configurazione:")
            for error in errors:
                print(f"  - {error}")
            return False
        else:
            print("Configurazione valida")
            return True
            
    except Exception as e:
        print(f"Errore lettura configurazione: {e}")
        return False

def show_user_policy(config_file, username):
    """Mostra la policy applicata a un utente"""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Errore lettura configurazione: {e}")
        return
    
    # Carica le policy rules dal file o directory separato
    policy_rules_file = config.get('daemon', {}).get('policy_rules_file', '/etc/pypolicyd/policy-rules.yml')
    
    # Se stiamo testando localmente, adatta i path
    if config_file.startswith('etc/'):
        # Path relativo per testing locale
        if policy_rules_file.startswith('/etc/pypolicyd/'):
            policy_rules_file = policy_rules_file.replace('/etc/pypolicyd/', 'etc/pypolicyd/')
    
    policy_rules = {}
    
    try:
        if policy_rules_file.endswith('.d') or os.path.isdir(policy_rules_file):
            # Carica da directory
            from pathlib import Path
            rules_dir = Path(policy_rules_file)
            if rules_dir.exists():
                for yaml_file in rules_dir.glob('*.yml'):
                    with open(yaml_file, 'r') as f:
                        file_rules = yaml.safe_load(f) or {}
                        policy_rules.update(file_rules)
        else:
            # Carica da file singolo
            if os.path.exists(policy_rules_file):
                with open(policy_rules_file, 'r') as f:
                    policy_rules = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Errore lettura policy rules: {e}")
    
    # Cerca policy per l'utente
    policy = None
    policy_source = "default"
    
    # 1. Cerca policy utente specifica
    if username in policy_rules:
        policy = policy_rules[username]
        policy_source = "user"
    else:
        # 2. Cerca policy dominio
        domain = username.split('@')[-1] if '@' in username else ''
        domain_pattern = f"*@{domain}"
        if domain_pattern in policy_rules:
            policy = policy_rules[domain_pattern]
            policy_source = "domain"
    
    # 3. Fallback a policy default
    if not policy:
        policy = config.get('default_policy', {})
    
    print(f"Policy per {username} (fonte: {policy_source}):")
    print(f"  Rate limits: {policy.get('rate_limits', 'N/A')}")
    print(f"  Max recipients: {policy.get('max_recipients', 'N/A')}")
    print(f"  Max size: {policy.get('max_size', 'N/A')}")
    
    if policy_source != "default":
        print(f"  Definita in: {policy_rules_file}")

def main():
    parser = argparse.ArgumentParser(description='SMTP Policy Daemon Management')
    parser.add_argument('--config', '-c', default='/etc/pypolicyd/main.yml',
                       help='File configurazione')
    parser.add_argument('--database', '-d', default='/var/lib/pypolicyd/policy.db',
                       help='Database SQLite')
    
    subparsers = parser.add_subparsers(dest='command', help='Comandi disponibili')
    
    # Comando reload
    subparsers.add_parser('reload', help='Ricarica configurazione daemon')
    
    # Comando stats
    subparsers.add_parser('stats', help='Mostra statistiche')
    
    # Comando reset
    reset_parser = subparsers.add_parser('reset', help='Reset limiti utente')
    reset_parser.add_argument('username', help='Username da resettare')
    
    # Comando cleanup
    subparsers.add_parser('cleanup', help='Rimuovi record scaduti')
    
    # Comando test-config
    subparsers.add_parser('test-config', help='Testa configurazione')
    
    # Comando show-policy
    policy_parser = subparsers.add_parser('show-policy', help='Mostra policy utente')
    policy_parser.add_argument('username', help='Username da controllare')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'reload':
        reload_config()
    elif args.command == 'stats':
        show_stats(args.config)  # Usa config invece di database
    elif args.command == 'reset':
        reset_user_limits(args.config, args.username)  # Usa config invece di database
    elif args.command == 'cleanup':
        # Per cleanup, determina il tipo di store dalla configurazione
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
            daemon_config = config.get('daemon', {})
            store_type = daemon_config.get('rate_limit_store_type', 'sqlite')
            
            if store_type == 'redis':
                print("Cleanup non necessario per Redis (TTL automatico)")
            else:
                db_path = daemon_config.get('database', args.database)
                cleanup_expired(db_path)
        except Exception as e:
            print(f"Errore durante cleanup: {e}")
    elif args.command == 'test-config':
        test_config(args.config)
    elif args.command == 'show-policy':
        show_user_policy(args.config, args.username)

if __name__ == '__main__':
    main()
