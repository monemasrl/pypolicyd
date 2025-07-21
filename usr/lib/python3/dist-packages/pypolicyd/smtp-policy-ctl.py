#!/usr/bin/env python3
"""
SMTP Policy Daemon Management Script
Utilità per gestire il daemon di policy SMTP
"""

import argparse
import sqlite3
import yaml
import sys
import os
import signal
from datetime import datetime, timedelta
from pathlib import Path

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

def show_stats(db_path):
    """Mostra statistiche rate limiting"""
    if not os.path.exists(db_path):
        print("Database non trovato")
        return
    
    conn = sqlite3.connect(db_path)
    
    print("=== Statistiche Rate Limiting ===")
    
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

def reset_user_limits(db_path, username):
    """Reset limiti per un utente specifico"""
    if not os.path.exists(db_path):
        print("Database non trovato")
        return
    
    conn = sqlite3.connect(db_path)
    
    # Reset limiti orari e giornalieri
    conn.execute('DELETE FROM rate_limits WHERE key IN (?, ?)', 
                (f'hourly:{username}', f'daily:{username}'))
    
    rows_affected = conn.total_changes
    conn.commit()
    conn.close()
    
    print(f"Reset limiti per {username} ({rows_affected} record rimossi)")

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
        policy_rules_file = config.get('smtp_policy', {}).get('policy_rules_file', '/etc/pypolicyd/policy-rules.yml')
        
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
    policy_rules_file = config.get('smtp_policy', {}).get('policy_rules_file', '/etc/pypolicyd/policy-rules.yml')
    
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
        show_stats(args.database)
    elif args.command == 'reset':
        reset_user_limits(args.database, args.username)
    elif args.command == 'cleanup':
        cleanup_expired(args.database)
    elif args.command == 'test-config':
        test_config(args.config)
    elif args.command == 'show-policy':
        show_user_policy(args.config, args.username)

if __name__ == '__main__':
    main()
