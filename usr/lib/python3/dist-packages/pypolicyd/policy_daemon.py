"""
Main policy daemon for PyPolicyd
"""

import asyncio
import logging
import socket
import sys
import os
from pathlib import Path
from typing import Dict, Any

from .policy_config import PolicyConfig
from .rate_limit import RateLimit, MultiWindowRateTracker
from .rate_limit_store import RateLimitStore
from .logging_service import PolicyLoggingService


class PolicyDaemon:
    """Demone principale per SMTP Policy"""
    
    def __init__(self, config_file: str, debug: bool = False):
        self.config_file = config_file
        self.debug = debug
        self.config = PolicyConfig(config_file, debug)
        
        # Configurazione daemon
        daemon_config = self.config.get_daemon_config()
        
        # Host e porta dal config SMTP policy (non daemon)
        self.bind_host = daemon_config.get('host', '127.0.0.1')
        self.bind_port = daemon_config.get('port', 10031)
        self.max_connections = daemon_config.get('max_connections', 100)
        
        # Configurazione SMTP policy
        self.db_path = daemon_config.get('database', '/var/lib/pypolicyd/rate_limits.db')
        self.cleanup_interval = daemon_config.get('cleanup_interval', 3600)
        
        # Directory regole policy - solo directory supportata
        self.rules_dir = daemon_config.get('policy_rules_file', '/etc/pypolicyd/policy-rules.d')
        
        # Store SQLite
        self.rate_limit_store = RateLimitStore(self.db_path)
        
        # Configura servizio di logging
        self.logging_service = PolicyLoggingService(daemon_config, debug=self.debug)
        
        # Server
        self.server = None
        
        # Carica regole
        self.policy_rules = {}
        self.load_policy_rules()
        
        if self.debug:
            self._print_startup_info()
    
    def _print_startup_info(self):
        """Mostra informazioni di avvio"""
        print(f"=== PyPolicyd Startup Info ===")
        print(f"Config file: {self.config_file}")
        print(f"Bind: {self.bind_host}:{self.bind_port}")
        print(f"Max connections: {self.max_connections}")
        print(f"Rate limit DB: {self.db_path}")
        print(f"Policy rules dir: {self.rules_dir}")
        print(f"Policy rules loaded: {len(self.policy_rules)} rules")
        print(f"Default policy: {self.config.get_default_policy()}")
        print(f"Debug mode: {self.debug}")
        print("=" * 30)
    
    def load_policy_rules(self):
        """Carica regole policy da directory"""
        self.policy_rules = {}
        
        # Carica da directory
        dir_rules = self.config.load_policy_rules_dir(self.rules_dir)
        
        # Le regole sono già nel formato chiave->valore corretto
        self.policy_rules = dir_rules.copy()
        
        if self.debug:
            print(f"[DEBUG] Regole policy caricate: {self.policy_rules}")
    
    async def handle_policy_request(self, reader, writer):
        """Gestisce richiesta policy Postfix"""
        try:
            request = {}
            
            # Ottieni informazioni del client per il log di connessione
            peer_info = writer.get_extra_info('peername')
            if peer_info:
                client_ip = peer_info[0]
                
                # Tenta di risolvere l'hostname (con timeout breve per non bloccare)
                try:
                    client_host = socket.gethostbyaddr(client_ip)[0]
                except (socket.herror, socket.timeout, OSError):
                    # Se la risoluzione fallisce, usa l'IP
                    client_host = client_ip
                
                self.logging_service.log_connection(client_host, client_ip)
            
            # Leggi richiesta Postfix
            while True:
                line = await reader.readline()
                if not line:
                    break
                
                line = line.decode('utf-8').strip()
                if not line:
                    break
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    request[key] = value
            
            if self.debug:
                print(f"[DEBUG] Richiesta ricevuta: {request}")
            
            # Elabora richiesta
            response = await self.process_request(request)
            
            # Invia risposta
            writer.write(f"action={response}\n\n".encode('utf-8'))
            await writer.drain()
            
        except Exception as e:
            logging.error(f"Errore gestione richiesta: {e}")
            writer.write(b"action=DUNNO\n\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def process_request(self, request: Dict[str, str]) -> str:
        """Elabora richiesta policy"""
        sender = request.get('sender', '')
        recipient = request.get('recipient', '')
        client_address = request.get('client_address', '')
        queue_id = request.get('queue_id', 'UNKNOWN')
        size = request.get('size', '0')
        nrcpt = request.get('recipient_count', '1')
        sasl_username = request.get('sasl_username', '')
        
        # Lista regole applicate per il log
        applied_rules = []
        
        # Ottieni l'identificatore utente per il rate limiting (stesso logic di policy_config)
        sasl_user = request.get('sasl_username', '')
        user_for_rate_limit = sasl_user if sasl_user else sender
        
        # Valuta TUTTE le policy applicabili (verifica gerarchica)
        applicable_policies = self.config.evaluate_all_applicable_policies(request, self.policy_rules)
        
        if self.debug:
            print(f"[DEBUG] Policy applicabili trovate: {len(applicable_policies)}")
            for policy, rule_key in applicable_policies:
                print(f"[DEBUG]   - {rule_key}: {policy}")
        
        # Se non ci sono policy applicabili, significa che l'utente non è autorizzato
        if not applicable_policies:
            action = "REJECT Unauthorized - user not found in policy rules"
            self._log_policy_decision(queue_id, ["unauthorized"], request, action)
            return action
        
        action = "DUNNO"  # Default action
        
        # Controlla rate limits per TUTTE le policy applicabili (controllo gerarchico)
        for policy, rule_key in applicable_policies:
            applied_rules.append(rule_key)
            
            # Se è una stringa, è una policy semplice (ACCEPT/REJECT/DUNNO)
            if isinstance(policy, str):
                if policy in ["REJECT", "ACCEPT"]:
                    # Policy esplicita ha precedenza
                    action = policy
                    self._log_policy_decision(queue_id, [rule_key], request, action)
                    return action
                # Se è DUNNO, continua con altre verifiche
                continue
            
            # Se è un oggetto, è una policy complessa con rate_limits specifici
            elif isinstance(policy, dict):
                # Controlla rate_limits specifici dell'utente/dominio
                if 'rate_limits' in policy:
                    rate_limit_result = self._check_user_rate_limits(user_for_rate_limit, policy['rate_limits'], rule_key)
                    if not rate_limit_result[0]:
                        # Rate limit superato - restituisci immediatamente REJECT
                        action = rate_limit_result[1]
                        self._log_policy_decision(queue_id, applied_rules, request, action)
                        return action
                
                # Controlla max_recipients
                recipient_count = int(nrcpt)
                if 'max_recipients' in policy:
                    max_recipients = policy['max_recipients']
                    if recipient_count > max_recipients:
                        action = f"REJECT Too many recipients ({recipient_count}/{max_recipients}) for rule {rule_key}"
                        self._log_policy_decision(queue_id, applied_rules, request, action)
                        return action
                
                # Controlla max_size
                if 'max_size' in policy:
                    message_size = int(size)
                    max_size_bytes = self._parse_size(policy['max_size'])
                    if message_size > max_size_bytes:
                        action = f"REJECT Message too large ({message_size}/{max_size_bytes} bytes) for rule {rule_key}"
                        self._log_policy_decision(queue_id, applied_rules, request, action)
                        return action
        
        # Se tutti i controlli passano
        action = "DUNNO"
        self._log_policy_decision(queue_id, applied_rules, request, action)
        return action
    
    def _log_policy_decision(self, queue_id: str, rules: list, request: Dict[str, str], action: str):
        """Log decisione policy in formato Postfix"""
        self.logging_service.log_policy_decision(queue_id, rules, request, action)
    
    def _check_user_rate_limits(self, user: str, rate_limits: list, rule_key: str = None) -> tuple[bool, str]:
        """Controlla rate limits specifici utente/dominio usando il database"""
        from .rate_limit import RateLimit
        
        try:
            if self.debug:
                print(f"[DEBUG] Controllo rate limits per {user} (regola: {rule_key}): {rate_limits}")
            
            # Converte le stringhe rate_limits in oggetti RateLimit
            rate_limit_objects = []
            for rate_str in rate_limits:
                try:
                    rate_limit_objects.append(RateLimit(rate_str))
                except ValueError as e:
                    logging.warning(f"Invalid rate limit format '{rate_str}' for user {user}: {e}")
                    continue
            
            if not rate_limit_objects:
                return True, "OK"
            
            # Controlla ogni rate limit usando il database
            for rate_limit in rate_limit_objects:
                # CORREZIONE: Usa rule_key (nome regola) invece di user (campo from)
                # Crea una chiave unica basata sulla regola che ha fatto match
                if rule_key:
                    rate_key = f"{rule_key}:{rate_limit.rate_str}"
                else:
                    # Fallback al comportamento precedente se rule_key non è disponibile
                    rate_key = f"{user}:{rate_limit.rate_str}"
                
                # Usa il database per controllare il rate limit
                allowed, current_count = self.rate_limit_store.check_rate_limit(
                    rate_key, 
                    rate_limit.count, 
                    rate_limit.window_seconds
                )
                
                if self.debug:
                    print(f"[DEBUG] Rate limit {rate_limit.rate_str} per regola {rule_key or user}: {current_count}/{rate_limit.count} (allowed: {allowed})")
                
                if not allowed:
                    reject_msg = f"REJECT Rate limit exceeded: {current_count}/{rate_limit.count} in {rate_limit.rate_str}"
                    if rule_key:
                        reject_msg += f" for rule {rule_key}"
                    return False, reject_msg
            
            return True, "OK"
            
        except Exception as e:
            logging.error(f"Error checking user rate limits for {user}: {e}")
            if self.debug:
                print(f"[DEBUG] Errore rate limiting per {user}: {e}")
            return True, "OK"  # In caso di errore, consenti l'accesso
    
    def _parse_size(self, size_str: str) -> int:
        """Converte string size (es. '10M', '100K') in bytes"""
        import re
        
        size_str = size_str.strip().upper()
        
        # Match formato: numero + unità opzionale
        match = re.match(r'^(\d+)([KMGT]?)B?$', size_str)
        
        if not match:
            # Se non c'è unità, assume bytes
            try:
                return int(size_str)
            except ValueError:
                return 0
        
        number = int(match.group(1))
        unit = match.group(2)
        
        multipliers = {
            '': 1,
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }
        
        return number * multipliers.get(unit, 1)
    
    async def cleanup_task(self):
        """Task periodico di pulizia"""
        while True:
            try:
                # Pulizia rate limits scaduti
                self.rate_limit_store.cleanup_expired()
                
                if self.debug:
                    print(f"[DEBUG] Cleanup completato")
            except Exception as e:
                logging.error(f"Errore durante cleanup: {e}")
            
            await asyncio.sleep(self.cleanup_interval)
    
    async def start_server(self):
        """Avvia server policy"""
        # Crea directory per database se non esiste
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Avvia server
        self.server = await asyncio.start_server(
            self.handle_policy_request,
            self.bind_host,
            self.bind_port,
            limit=self.max_connections
        )
        
        print(f"PyPolicyd listening on {self.bind_host}:{self.bind_port}")
        self.logging_service.log_startup(f"PyPolicyd started on {self.bind_host}:{self.bind_port}")
        
        # Avvia task di cleanup
        cleanup_task = asyncio.create_task(self.cleanup_task())
        
        try:
            async with self.server:
                await self.server.serve_forever()
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
    
    def stop_server(self):
        """Ferma server"""
        if self.server:
            self.server.close()
            print("PyPolicyd stopped")
            self.logging_service.log_shutdown("PyPolicyd stopped")
