"""
Policy configuration management for PyPolicyd
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Union, List, Union, Optional
from .logging_service import PolicyLoggingService


class PolicyConfig:
    """Gestione configurazione policy"""
    
    def __init__(self, config_file: str, debug: bool = False):
        self.config_file = config_file
        self.debug = debug
        self.config = {}

        self.load_config()
        self.logging_service = PolicyLoggingService(self.config, debug=self.debug)
        self.logging_service.log_startup(f"Loaded configuration from {self.config_file}")
            
    def load_config(self):
        """Carica configurazione da file YAML"""
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            
            if self.debug:
                print(f"[DEBUG] Configurazione caricata: {self.config}")
                
        except FileNotFoundError:
            raise FileNotFoundError(f"File di configurazione non trovato: {self.config_file}")
        except yaml.YAMLError as e:
            raise ValueError(f"Errore parsing YAML: {e}")
    
    def get_smtp_policy_config(self) -> Dict[str, Any]:
        """Restituisce configurazione smtp_policy"""
        return self.config.get('daemon', {})
    
    def get_daemon_config(self) -> Dict[str, Any]:
        """Restituisce configurazione daemon"""
        return self.config.get('daemon', {})
    
    def get_default_policy(self) -> str:
        """Restituisce policy predefinita"""
        # Cerca prima un valore stringa diretto
        if isinstance(self.config.get('default_policy'), str):
            return self.config.get('default_policy', 'DUNNO')
        
        # Se non c'è, usa DUNNO come default per Postfix
        return 'DUNNO'
    
    def load_policy_rules_dir(self, rules_dir: str) -> Dict[str, Any]:
        """Carica regole da directory policy-rules.d con nuovo formato gerarchico"""
        rules_dir_path = Path(rules_dir)
        
        if not rules_dir_path.exists() or not rules_dir_path.is_dir():
            if self.debug:
                print(f"[DEBUG] Directory regole non trovata: {rules_dir}")
            return {}
        
        all_rules = {}
        
        for rules_file in rules_dir_path.glob("*.yml"):
            if self.debug:
                print(f"[DEBUG] Caricamento regole da: {rules_file}")
            
            try:
                with open(rules_file, 'r') as f:
                    rules = yaml.safe_load(f)
                
                if rules and 'domains' in rules:
                    # Nuovo formato gerarchico con domains
                    for domain_config in rules['domains']:
                        domain_name = domain_config.get('name')
                        if not domain_name:
                            continue
                        
                        # Processa domain_limits come regola wildcard
                        if 'domain_limits' in domain_config:
                            domain_key = f"*@{domain_name}"
                            all_rules[domain_key] = domain_config['domain_limits'].copy()
                            
                            if self.debug:
                                print(f"[DEBUG] Domain limits per {domain_name}: {all_rules[domain_key]}")
                        
                        # Processa utenti specifici
                        if 'users' in domain_config:
                            for user_email, user_policy in domain_config['users'].items():
                                all_rules[user_email] = user_policy.copy()
                                
                                if self.debug:
                                    print(f"[DEBUG] User policy per {user_email}: {all_rules[user_email]}")
                
                elif rules:
                    # Formato legacy: merge diretto delle regole
                    if self.debug:
                        print(f"[DEBUG] Formato legacy rilevato in {rules_file}")
                    
                    for rule_key, rule_value in rules.items():
                        all_rules[rule_key] = rule_value
                
                if self.debug:
                    print(f"[DEBUG] Regole caricate da {rules_file}: {len(rules.get('domains', rules))} entry")
                    
            except yaml.YAMLError as e:
                logging.error(f"Errore parsing regole da {rules_file}: {e}")
                continue
        
        if self.debug:
            print(f"[DEBUG] Tutte le regole caricate: {all_rules}")
            
        return all_rules
    
    def evaluate_policy(self, request: Dict[str, str], rules: Dict[str, Any]) -> tuple[Union[str, Dict[str, Any]], str]:
        """Valuta policy basata su regole - restituisce tupla (policy, rule_key)"""
        if self.debug:
            print(f"[DEBUG] Valutazione policy per richiesta: {request}")
            print(f"[DEBUG] Regole disponibili: {list(rules.keys())}")
        
        # Ottieni sasl_username per controllo gerarchico (campo principale per le policy)
        sasl_user = request.get('sasl_username', '')
        sender = request.get('sender', '')
        
        # Se c'è sasl_username, usa quello per le policy
        if sasl_user:
            if self.debug:
                print(f"[DEBUG] Utente autenticato: {sasl_user}")
            
            # Se sasl_user non contiene @, ricostruisci l'email completa dal sender
            if '@' not in sasl_user and sender and '@' in sender:
                domain = sender.split('@')[1]
                full_user_email = f"{sasl_user}@{domain}"
                if self.debug:
                    print(f"[DEBUG] Ricostruisco email completa: {sasl_user} + {domain} = {full_user_email}")
            else:
                full_user_email = sasl_user
            
            # Cerca regola specifica per utente (utente esatto)
            if full_user_email in rules:
                policy = rules[full_user_email]
                if self.debug:
                    print(f"[DEBUG] Trovata regola utente esatta: {full_user_email} -> {policy}")
                return policy, full_user_email
            
            # Cerca anche la versione originale di sasl_user (per backward compatibility)
            if sasl_user != full_user_email and sasl_user in rules:
                policy = rules[sasl_user]
                if self.debug:
                    print(f"[DEBUG] Trovata regola utente esatta (legacy): {sasl_user} -> {policy}")
                return policy, sasl_user
            
            # Cerca regola per dominio utente (wildcard *@dominio)
            if '@' in full_user_email:
                domain = full_user_email.split('@')[1]
                domain_pattern = f"*@{domain}"
                
                if domain_pattern in rules:
                    policy = rules[domain_pattern]
                    if self.debug:
                        print(f"[DEBUG] Trovata regola dominio utente: {domain_pattern} -> {policy}")
                    return policy, domain_pattern
            
            # Se non troviamo regole per l'utente autenticato, REJECT
            if self.debug:
                print(f"[DEBUG] Nessuna regola trovata per utente autenticato {sasl_user} - REJECT")
            return f"REJECT Unauthorized user: {sasl_user}", "unauthorized"
        
        # Se non c'è sasl_username, comportamento legacy con sender (per backward compatibility)
        elif sender:
            if self.debug:
                print(f"[DEBUG] Nessun sasl_username, uso sender legacy: {sender}")
            
            # Cerca regola specifica per sender (utente esatto)
            if sender in rules:
                policy = rules[sender]
                if self.debug:
                    print(f"[DEBUG] Trovata regola sender esatta: {sender} -> {policy}")
                return policy, sender
            
            # Cerca regola per dominio sender (wildcard *@dominio)
            if '@' in sender:
                domain = sender.split('@')[1]
                domain_pattern = f"*@{domain}"
                
                if domain_pattern in rules:
                    policy = rules[domain_pattern]
                    if self.debug:
                        print(f"[DEBUG] Trovata regola dominio sender: {domain_pattern} -> {policy}")
                    return policy, domain_pattern
        
        # Controlla regole legacy (sender/recipient separati)
        
        # Controlla regole legacy (sender/recipient separati)
        # Controlla regole per sender
        if sender and 'sender' in rules:
            sender_rules = rules['sender']
            if self.debug:
                print(f"[DEBUG] Controllo regole sender legacy per: {sender}")
                print(f"[DEBUG] Regole sender disponibili: {list(sender_rules.keys())}")
            
            # Controlla sender esatto
            if sender in sender_rules:
                policy = sender_rules[sender]
                if self.debug:
                    print(f"[DEBUG] Trovata regola sender esatta: {sender} -> {policy}")
                return policy, f"sender.{sender}"
            
            # Controlla domini sender
            if '@' in sender:
                domain = sender.split('@')[1]
                if domain in sender_rules:
                    policy = sender_rules[domain]
                    if self.debug:
                        print(f"[DEBUG] Trovata regola dominio sender: {domain} -> {policy}")
                    return policy, f"sender.{domain}"
        
        # Controlla regole per recipient
        recipient = request.get('recipient', '')
        if recipient and 'recipient' in rules:
            recipient_rules = rules['recipient']
            if self.debug:
                print(f"[DEBUG] Controllo regole recipient per: {recipient}")
                print(f"[DEBUG] Regole recipient disponibili: {list(recipient_rules.keys())}")
            
            # Controlla recipient esatto
            if recipient in recipient_rules:
                policy = recipient_rules[recipient]
                if self.debug:
                    print(f"[DEBUG] Trovata regola recipient esatta: {recipient} -> {policy}")
                return policy, f"recipient.{recipient}"
            
            # Controlla domini recipient
            if '@' in recipient:
                domain = recipient.split('@')[1]
                if domain in recipient_rules:
                    policy = recipient_rules[domain]
                    if self.debug:
                        print(f"[DEBUG] Trovata regola dominio recipient: {domain} -> {policy}")
                    return policy, f"recipient.{domain}"
        
        # Policy predefinita
        default = self.get_default_policy()
        if self.debug:
            print(f"[DEBUG] Nessuna regola trovata, uso policy predefinita: {default}")
        return default, "default"

    def evaluate_all_applicable_policies(self, request: Dict[str, str], rules: Dict[str, Any]) -> List[tuple[Union[str, Dict[str, Any]], str]]:
        """Trova TUTTE le regole applicabili per la richiesta (controllo gerarchico)"""
        if self.debug:
            print(f"[DEBUG] Valutazione TUTTE le policy per richiesta: {request}")
            print(f"[DEBUG] Regole disponibili: {list(rules.keys())}")
        
        applicable_policies = []
        
        # Ottieni sasl_username per controllo gerarchico (campo principale per le policy)
        sasl_user = request.get('sasl_username', '')
        sender = request.get('sender', '')
        
        # Se c'è sasl_username, usa quello per le policy (autenticazione richiesta)
        if sasl_user:
            if self.debug:
                print(f"[DEBUG] Utente autenticato: {sasl_user}")
            
            # Se sasl_user non contiene @, ricostruisci l'email completa dal sender
            if '@' not in sasl_user and sender and '@' in sender:
                domain = sender.split('@')[1]
                full_user_email = f"{sasl_user}@{domain}"
                if self.debug:
                    print(f"[DEBUG] Ricostruisco email completa: {sasl_user} + {domain} = {full_user_email}")
            else:
                full_user_email = sasl_user
            
            # 1. Cerca regola specifica per utente (più prioritaria)
            if full_user_email in rules:
                policy = rules[full_user_email]
                applicable_policies.append((policy, full_user_email))
                if self.debug:
                    print(f"[DEBUG] Aggiunta regola utente esatta: {full_user_email} -> {policy}")
            
            # Cerca anche la versione originale di sasl_user (per backward compatibility)
            if sasl_user != full_user_email and sasl_user in rules:
                policy = rules[sasl_user]
                applicable_policies.append((policy, sasl_user))
                if self.debug:
                    print(f"[DEBUG] Aggiunta regola utente esatta (legacy): {sasl_user} -> {policy}")
            
            # 2. Cerca regola per dominio utente (wildcard *@dominio)
            if '@' in full_user_email:
                domain = full_user_email.split('@')[1]
                domain_pattern = f"*@{domain}"
                
                if domain_pattern in rules:
                    policy = rules[domain_pattern]
                    applicable_policies.append((policy, domain_pattern))
                    if self.debug:
                        print(f"[DEBUG] Aggiunta regola dominio utente: {domain_pattern} -> {policy}")
            
            # Se non abbiamo trovato regole applicabili per l'utente autenticato, REJECT
            if not applicable_policies:
                if self.debug:
                    print(f"[DEBUG] Nessuna regola trovata per utente autenticato {sasl_user} - REJECT")
                # Restituiamo una policy REJECT esplicita
                return [("REJECT Unauthorized user", "unauthorized")]
        
        # Se non c'è sasl_username, comportamento legacy con sender (per backward compatibility)
        elif sender:
            if self.debug:
                print(f"[DEBUG] Nessun sasl_username, uso sender legacy: {sender}")
            
            # 1. Cerca regola specifica per sender (più prioritaria)
            if sender in rules:
                policy = rules[sender]
                applicable_policies.append((policy, sender))
                if self.debug:
                    print(f"[DEBUG] Aggiunta regola sender esatta: {sender} -> {policy}")
            
            # 2. Cerca regola per dominio sender (wildcard *@dominio)
            if '@' in sender:
                domain = sender.split('@')[1]
                domain_pattern = f"*@{domain}"
                
                if domain_pattern in rules:
                    policy = rules[domain_pattern]
                    applicable_policies.append((policy, domain_pattern))
                    if self.debug:
                        print(f"[DEBUG] Aggiunta regola dominio sender: {domain_pattern} -> {policy}")
            
            # Se non abbiamo trovato regole applicabili, usa default
            if not applicable_policies:
                default = self.get_default_policy()
                applicable_policies.append((default, "default"))
                if self.debug:
                    print(f"[DEBUG] Nessuna regola trovata per sender, uso policy predefinita: {default}")
        
        # Se non c'è né sasl_username né sender, REJECT
        else:
            if self.debug:
                print(f"[DEBUG] Nessun sasl_username né sender fornito - REJECT per sicurezza")
            return [("REJECT No authentication", "unauthorized")]
        
        return applicable_policies
