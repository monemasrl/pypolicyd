#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gestione delle regole policy dal file policy-rules.yml o directory policy-rules.d
"""

import os
import yaml
import glob
import logging
from typing import Dict, Any, Optional

class PolicyRules:
    """Gestisce le regole policy da file singolo o directory modulare"""
    
    def __init__(self, rules_path: str = "/etc/pypolicyd/policy-rules.d"):
        """Inizializza le regole dei criteri
        
        Args:
            rules_path: Può essere un file YAML singolo o una directory 
                       contenente file YAML (policy-rules.d)
        """
        self.rules_path = rules_path
        self.rules: Dict[str, Any] = {}
        self.default_policy: Dict[str, Any] = {}
        self.logger = logging.getLogger('policy-rules')
        self.load_rules()
    
    def load_rules(self):
        """Carica le regole dai file di configurazione"""
        try:
            if os.path.isfile(self.rules_path):
                # Caricamento da file singolo (retrocompatibilità)
                self._load_single_file(self.rules_path)
            elif os.path.isdir(self.rules_path):
                # Caricamento da directory con file multipli
                self._load_directory(self.rules_path)
            else:
                self.logger.warning(f"Percorso delle regole non trovato: {self.rules_path}")
                # Fallback al file singolo tradizionale
                fallback_file = "/etc/pypolicyd/policy-rules.yml"
                if os.path.exists(fallback_file):
                    self.logger.info(f"Usando file fallback: {fallback_file}")
                    self._load_single_file(fallback_file)
        except Exception as e:
            self.logger.error(f"Errore nel caricamento delle regole: {e}")

    def _load_single_file(self, file_path):
        """Carica regole da un singolo file YAML"""
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f) or {}
            self.rules.update(data)
        self.logger.info(f"Caricate {len(data)} regole da {file_path}")

    def _load_directory(self, dir_path):
        """Carica regole da tutti i file YAML in una directory"""
        yaml_files = glob.glob(os.path.join(dir_path, '*.yml')) + \
                    glob.glob(os.path.join(dir_path, '*.yaml'))
        
        # Ordina i file per garantire un caricamento consistente
        yaml_files.sort()
        
        total_rules = 0
        for yaml_file in yaml_files:
            self.logger.debug(f"Caricamento regole da: {yaml_file}")
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f) or {}
                    if data:
                        # Controlla per conflitti nelle regole
                        for rule_key in data:
                            if rule_key in self.rules:
                                self.logger.warning(f"Sovrascrittura regola '{rule_key}' "
                                                  f"da {os.path.basename(yaml_file)}")
                        self.rules.update(data)
                        total_rules += len(data)
            except Exception as e:
                self.logger.error(f"Errore nel caricamento di {yaml_file}: {e}")
        
        self.logger.info(f"Caricate {total_rules} regole totali da {len(yaml_files)} file in {dir_path}")
    
    def set_default_policy(self, default_policy: Dict[str, Any]):
        """Imposta la policy di default"""
        self.default_policy = default_policy
    
    def get_policy_for_user(self, email: str) -> Dict[str, Any]:
        """Ottiene la policy per un utente specifico"""
        if not email:
            return self.default_policy.copy()
        
        # Prima controlla se esiste una regola specifica per l'utente
        if email in self.rules:
            return self.rules[email].copy()
        
        # Poi controlla se esiste una regola per il dominio
        domain = email.split('@')[-1] if '@' in email else ''
        if domain:
            domain_key = f"*@{domain}"
            if domain_key in self.rules:
                return self.rules[domain_key].copy()
        
        # Altrimenti usa la policy di default
        return self.default_policy.copy()
    
    def get_all_users_for_domain(self, domain: str) -> Dict[str, Dict[str, Any]]:
        """Ottiene tutti gli utenti configurati per un dominio"""
        users = {}
        domain_suffix = f"@{domain}"
        
        for key, policy in self.rules.items():
            if key.endswith(domain_suffix) and not key.startswith('*@'):
                users[key] = policy.copy()
        
        return users
    
    def get_domain_policy(self, domain: str) -> Optional[Dict[str, Any]]:
        """Ottiene la policy del dominio se esiste"""
        domain_key = f"*@{domain}"
        if domain_key in self.rules:
            return self.rules[domain_key].copy()
        return None
    
    def validate_user_against_domain(self, user_email: str) -> Dict[str, Any]:
        """Valida che la policy utente non superi quella del dominio"""
        user_policy = self.get_policy_for_user(user_email)
        
        if '@' not in user_email:
            return user_policy
        
        domain = user_email.split('@')[-1]
        domain_policy = self.get_domain_policy(domain)
        
        if not domain_policy:
            return user_policy
        
        # Valida che i limiti utente non superino quelli del dominio
        validated_policy = user_policy.copy()
        
        # Valida max_recipients
        if ('max_recipients' in user_policy and 'max_recipients' in domain_policy and
            user_policy['max_recipients'] > domain_policy['max_recipients']):
            self.logger.warning(f"User {user_email} max_recipients ({user_policy['max_recipients']}) "
                              f"exceeds domain limit ({domain_policy['max_recipients']})")
            validated_policy['max_recipients'] = domain_policy['max_recipients']
        
        # Valida max_size
        if 'max_size' in user_policy and 'max_size' in domain_policy:
            user_size = self._parse_size(user_policy['max_size'])
            domain_size = self._parse_size(domain_policy['max_size'])
            
            if user_size > domain_size:
                self.logger.warning(f"User {user_email} max_size ({user_policy['max_size']}) "
                                  f"exceeds domain limit ({domain_policy['max_size']})")
                validated_policy['max_size'] = domain_policy['max_size']
        
        # Valida rate_limits (confronto complesso, per ora mantieniamo la policy utente)
        # Nota: potresti voler implementare una validazione più sofisticata qui
        
        return validated_policy
    
    def _parse_size(self, size_str: str) -> int:
        """Converte string size (es. '10M', '100K') in bytes"""
        if not size_str:
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
            try:
                return int(size_str)
            except ValueError:
                return 0
    
    def reload(self):
        """Ricarica le regole"""
        self.load_rules()
    
    def list_all_rules(self) -> Dict[str, Any]:
        """Lista tutte le regole caricate"""
        return self.rules.copy()
    
    def add_rule(self, identifier: str, policy: Dict[str, Any]):
        """Aggiunge una regola (per uso programmatico, non salva su file)"""
        self.rules[identifier] = policy.copy()
    
    def remove_rule(self, identifier: str):
        """Rimuove una regola (per uso programmatico, non salva su file)"""
        if identifier in self.rules:
            del self.rules[identifier]
