#!/usr/bin/env python3
"""
Unit tests per PolicyConfig
"""

import unittest
import tempfile
import yaml
import os
from pathlib import Path
import sys

# Aggiungi il path dei moduli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'usr/lib/python3/dist-packages'))

from pypolicyd.policy_config import PolicyConfig


class TestPolicyConfig(unittest.TestCase):
    """Test per la classe PolicyConfig"""
    
    def setUp(self):
        """Prepara i test creando file di configurazione temporanei"""
        # File di configurazione principale
        self.config_data = {
            'daemon': {
                'max_connections': 100,
                'log_level': 'INFO'
            },
            'smtp_policy': {
                'host': '127.0.0.1',
                'port': 10031,
                'database': '/tmp/test_rate_limits.db',
                'default_policy': 'DUNNO',
                'cleanup_interval': 3600,
                'policy_rules_file': '/tmp/test_rules.d',
                'log_destination': 'stdout',
                'log_request': 'all'
            }
        }
        
        # Crea file di configurazione temporaneo
        self.config_fd, self.config_file = tempfile.mkstemp(suffix='.yml')
        with os.fdopen(self.config_fd, 'w') as f:
            yaml.dump(self.config_data, f)
        
        # Crea directory per le regole
        self.rules_dir = tempfile.mkdtemp()
        self.config_data['smtp_policy']['policy_rules_file'] = self.rules_dir
        
        # Ricrea il file di configurazione con il path corretto
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config_data, f)
    
    def tearDown(self):
        """Pulisce i file temporanei"""
        if os.path.exists(self.config_file):
            os.unlink(self.config_file)
        
        # Rimuovi directory delle regole
        import shutil
        if os.path.exists(self.rules_dir):
            shutil.rmtree(self.rules_dir)
    
    def test_load_config(self):
        """Test caricamento configurazione"""
        config = PolicyConfig(self.config_file, debug=False)
        
        # Verifica che la configurazione sia caricata correttamente
        self.assertIsInstance(config.config, dict)
        self.assertEqual(config.config['daemon']['max_connections'], 100)
        self.assertEqual(config.config['smtp_policy']['port'], 10031)
    
    def test_get_daemon_config(self):
        """Test estrazione configurazione daemon"""
        config = PolicyConfig(self.config_file, debug=False)
        daemon_config = config.get_daemon_config()
        
        self.assertIsInstance(daemon_config, dict)
        self.assertEqual(daemon_config['max_connections'], 100)
        self.assertEqual(daemon_config['log_level'], 'INFO')
    
    def test_get_smtp_policy_config(self):
        """Test estrazione configurazione SMTP policy"""
        config = PolicyConfig(self.config_file, debug=False)
        smtp_config = config.get_smtp_policy_config()
        
        self.assertIsInstance(smtp_config, dict)
        self.assertEqual(smtp_config['host'], '127.0.0.1')
        self.assertEqual(smtp_config['port'], 10031)
        self.assertEqual(smtp_config['default_policy'], 'DUNNO')
    
    def test_get_default_policy(self):
        """Test policy predefinita"""
        config = PolicyConfig(self.config_file, debug=False)
        default = config.get_default_policy()
        
        self.assertEqual(default, 'DUNNO')
    
    def test_evaluate_policy_exact_match(self):
        """Test valutazione policy per match esatto"""
        # Crea regole di test
        rules_data = {
            'user@example.com': {
                'max_recipients': 50,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h']
            },
            '*@example.com': {
                'max_recipients': 25,
                'max_size': '5M',
                'rate_limits': ['3/1m', '30/1h']
            }
        }
        
        rules_file = os.path.join(self.rules_dir, 'example.yml')
        with open(rules_file, 'w') as f:
            yaml.dump(rules_data, f)
        
        config = PolicyConfig(self.config_file, debug=False)
        all_rules = config.load_policy_rules_dir(self.rules_dir)
        
        # Test match esatto
        request = {'sender': 'user@example.com', 'recipient': 'test@domain.com', 'sasl_username': 'user@example.com'}
        policy, rule_key = config.evaluate_policy(request, all_rules)
        
        self.assertIsInstance(policy, dict)
        self.assertEqual(rule_key, 'user@example.com')
        self.assertEqual(policy['max_recipients'], 50)
        self.assertEqual(policy['max_size'], '10M')
        self.assertEqual(policy['rate_limits'], ['5/1m', '50/1h'])
    
    def test_evaluate_policy_wildcard_match(self):
        """Test valutazione policy per match wildcard"""
        # Crea regole di test
        rules_data = {
            'user@example.com': {
                'max_recipients': 50,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h']
            },
            '*@example.com': {
                'max_recipients': 25,
                'max_size': '5M',
                'rate_limits': ['3/1m', '30/1h']
            }
        }
        
        rules_file = os.path.join(self.rules_dir, 'example.yml')
        with open(rules_file, 'w') as f:
            yaml.dump(rules_data, f)
        
        config = PolicyConfig(self.config_file, debug=False)
        all_rules = config.load_policy_rules_dir(self.rules_dir)
        
        # Test match wildcard
        request = {'sender': 'other@example.com', 'recipient': 'test@domain.com', 'sasl_username': 'other@example.com'}
        policy, rule_key = config.evaluate_policy(request, all_rules)
        
        self.assertIsInstance(policy, dict)
        self.assertEqual(rule_key, '*@example.com')
        self.assertEqual(policy['max_recipients'], 25)
        self.assertEqual(policy['max_size'], '5M')
        self.assertEqual(policy['rate_limits'], ['3/1m', '30/1h'])
    
    def test_evaluate_policy_default(self):
        """Test valutazione policy predefinita"""
        config = PolicyConfig(self.config_file, debug=False)
        all_rules = {}
        
        # Test nessun match - policy predefinita
        request = {'sender': 'unknown@other.com', 'recipient': 'test@domain.com'}
        policy, rule_key = config.evaluate_policy(request, all_rules)
        
        self.assertEqual(policy, 'DUNNO')
        self.assertEqual(rule_key, 'default')
    
    def test_load_policy_rules_dir(self):
        """Test caricamento regole da directory"""
        # Crea più file di regole
        rules1_data = {
            'user1@example.com': 'ACCEPT',
            '*@example.com': {
                'max_recipients': 25,
                'rate_limits': ['5/1m']
            }
        }
        
        rules2_data = {
            'user2@company.com': {
                'max_recipients': 100,
                'max_size': '50M'
            },
            '*@company.com': 'ACCEPT'
        }
        
        rules1_file = os.path.join(self.rules_dir, 'example.yml')
        rules2_file = os.path.join(self.rules_dir, 'company.yml')
        
        with open(rules1_file, 'w') as f:
            yaml.dump(rules1_data, f)
        
        with open(rules2_file, 'w') as f:
            yaml.dump(rules2_data, f)
        
        config = PolicyConfig(self.config_file, debug=False)
        all_rules = config.load_policy_rules_dir(self.rules_dir)
        
        # Verifica che tutte le regole siano caricate
        self.assertIn('user1@example.com', all_rules)
        self.assertIn('*@example.com', all_rules)
        self.assertIn('user2@company.com', all_rules)
        self.assertIn('*@company.com', all_rules)
        
        self.assertEqual(all_rules['user1@example.com'], 'ACCEPT')
        self.assertEqual(all_rules['*@company.com'], 'ACCEPT')
        self.assertIsInstance(all_rules['*@example.com'], dict)
        self.assertIsInstance(all_rules['user2@company.com'], dict)


if __name__ == '__main__':
    unittest.main()
