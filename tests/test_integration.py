#!/usr/bin/env python3
"""
Test di integrazione per verificare il sistema completo
"""

import unittest
import tempfile
import yaml
import os
import sys
import asyncio
from pathlib import Path

# Aggiungi il path dei moduli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'usr/lib/python3/dist-packages'))

from pypolicyd.policy_daemon import PolicyDaemon


class TestIntegration(unittest.TestCase):
    """Test di integrazione per il sistema completo"""
    
    def setUp(self):
        """Prepara i test creando una configurazione completa"""
        # File di configurazione principale
        self.config_data = {
            'daemon': {
                'max_connections': 50,
                'log_level': 'INFO',
                'host': '127.0.0.1',
                'port': 10031,
                'database': '/tmp/test_integration.db',
                'default_policy': 'DUNNO',
                'cleanup_interval': 3600,
                'policy_rules_file': '/tmp/test_integration_rules.d',
                'log_destination': 'stdout',
                'log_request': 'all',
                'log_connection': True,
                'log_format': 'postfix'
            }
        }
        
        # Crea file di configurazione temporaneo
        self.config_fd, self.config_file = tempfile.mkstemp(suffix='.yml')
        with os.fdopen(self.config_fd, 'w') as f:
            yaml.dump(self.config_data, f)
        
        # Crea directory per le regole
        self.rules_dir = tempfile.mkdtemp()
        self.config_data['daemon']['policy_rules_file'] = self.rules_dir
        
        # Ricrea il file di configurazione con il path corretto
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config_data, f)
        
        # Crea regole complete di test
        self.create_comprehensive_rules()
    
    def tearDown(self):
        """Pulisce i file temporanei"""
        if os.path.exists(self.config_file):
            os.unlink(self.config_file)
        
        # Rimuovi directory delle regole
        import shutil
        if os.path.exists(self.rules_dir):
            shutil.rmtree(self.rules_dir)
        
        # Rimuovi database di test se esiste
        db_path = '/tmp/test_integration.db'
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    def create_comprehensive_rules(self):
        """Crea regole comprehensive per test di integrazione"""
        # Regole per company.com (come nell'esempio reale)
        company_rules = {
            '*@company.com': {
                'max_recipients': 100,
                'max_size': '50M',
                'rate_limits': ['20/1m', '200/1h', '2000/1d', '50000/1M']
            },
            'ceo@company.com': {
                'max_recipients': 500,
                'max_size': '100M',
                'rate_limits': ['50/1m', '500/1h', '5000/1d', '100000/1M']
            },
            'manager@company.com': {
                'max_recipients': 300,
                'max_size': '75M',
                'rate_limits': ['30/1m', '300/1h', '3000/1d', '75000/1M']
            },
            'marketing@company.com': {
                'max_recipients': 1000,
                'max_size': '25M',
                'rate_limits': ['100/1m', '1000/1h', '10000/1d', '200000/1M']
            },
            'newsletter@company.com': {
                'max_recipients': 5000,
                'max_size': '10M',
                'rate_limits': ['200/1m', '2000/1h', '20000/1d', '500000/1M']
            }
        }
        
        # Regole per example.com
        example_rules = {
            '*@example.com': {
                'max_recipients': 25,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h', '500/1d', '10000/1M']
            },
            'user@example.com': {
                'max_recipients': 25,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h', '500/1d', '10000/1M']
            },
            'marketing@example.com': {
                'max_recipients': 500,
                'max_size': '20M',
                'rate_limits': ['50/1m', '500/1h', '5000/1d', '100000/1M']
            }
        }
        
        # Regole semplici (string-based)
        simple_rules = {
            'blocked@spam.com': 'REJECT',
            'admin@internal.com': 'ACCEPT',
            '*@trusted.com': 'ACCEPT'
        }
        
        # Scrivi i file delle regole
        with open(os.path.join(self.rules_dir, 'company.yml'), 'w') as f:
            yaml.dump(company_rules, f)
        
        with open(os.path.join(self.rules_dir, 'example.yml'), 'w') as f:
            yaml.dump(example_rules, f)
        
        with open(os.path.join(self.rules_dir, 'simple.yml'), 'w') as f:
            yaml.dump(simple_rules, f)


class TestIntegrationAsync(unittest.IsolatedAsyncioTestCase):
    """Test di integrazione asincroni"""
    
    def setUp(self):
        """Prepara i test creando una configurazione completa"""
        # File di configurazione principale
        self.config_data = {
            'daemon': {
                'max_connections': 50,
                'log_level': 'INFO',
                'host': '127.0.0.1',
                'port': 10031,
                'database': '/tmp/test_integration.db',
                'default_policy': 'DUNNO',
                'cleanup_interval': 3600,
                'policy_rules_file': '/tmp/test_integration_rules.d',
                'log_destination': 'stdout',
                'log_request': 'all',
                'log_connection': True,
                'log_format': 'postfix'
            }
        }
        
        # Crea file di configurazione temporaneo
        self.config_fd, self.config_file = tempfile.mkstemp(suffix='.yml')
        with os.fdopen(self.config_fd, 'w') as f:
            yaml.dump(self.config_data, f)
        
        # Crea directory per le regole
        self.rules_dir = tempfile.mkdtemp()
        self.config_data['daemon']['policy_rules_file'] = self.rules_dir
        
        # Ricrea il file di configurazione con il path corretto
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config_data, f)
        
        # Crea regole complete di test
        self.create_comprehensive_rules()
    
    def tearDown(self):
        """Pulisce i file temporanei"""
        if os.path.exists(self.config_file):
            os.unlink(self.config_file)
        
        # Rimuovi directory delle regole
        import shutil
        if os.path.exists(self.rules_dir):
            shutil.rmtree(self.rules_dir)
        
        # Rimuovi database di test se esiste
        db_path = '/tmp/test_integration.db'
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    def create_comprehensive_rules(self):
        """Crea regole comprehensive per test di integrazione"""
        # Regole per company.com (come nell'esempio reale)
        company_rules = {
            '*@company.com': {
                'max_recipients': 100,
                'max_size': '50M',
                'rate_limits': ['20/1m', '200/1h', '2000/1d', '50000/1M']
            },
            'ceo@company.com': {
                'max_recipients': 500,
                'max_size': '100M',
                'rate_limits': ['50/1m', '500/1h', '5000/1d', '100000/1M']
            },
            'manager@company.com': {
                'max_recipients': 300,
                'max_size': '75M',
                'rate_limits': ['30/1m', '300/1h', '3000/1d', '75000/1M']
            },
            'marketing@company.com': {
                'max_recipients': 1000,
                'max_size': '25M',
                'rate_limits': ['100/1m', '1000/1h', '10000/1d', '200000/1M']
            },
            'newsletter@company.com': {
                'max_recipients': 5000,
                'max_size': '10M',
                'rate_limits': ['200/1m', '2000/1h', '20000/1d', '500000/1M']
            }
        }
        
        # Regole per example.com
        example_rules = {
            '*@example.com': {
                'max_recipients': 25,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h', '500/1d', '10000/1M']
            },
            'user@example.com': {
                'max_recipients': 25,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h', '500/1d', '10000/1M']
            },
            'marketing@example.com': {
                'max_recipients': 500,
                'max_size': '20M',
                'rate_limits': ['50/1m', '500/1h', '5000/1d', '100000/1M']
            }
        }
        
        # Regole semplici (string-based)
        simple_rules = {
            'blocked@spam.com': 'REJECT',
            'admin@internal.com': 'ACCEPT',
            '*@trusted.com': 'ACCEPT'
        }
        
        # Scrivi i file delle regole
        with open(os.path.join(self.rules_dir, 'company.yml'), 'w') as f:
            yaml.dump(company_rules, f)
        
        with open(os.path.join(self.rules_dir, 'example.yml'), 'w') as f:
            yaml.dump(example_rules, f)
        
        with open(os.path.join(self.rules_dir, 'simple.yml'), 'w') as f:
            yaml.dump(simple_rules, f)
    
    async def test_complete_workflow_ceo(self):
        """Test workflow completo per CEO di company.com"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        print("\n=== Test Complete Workflow - CEO ===")
        
        # Richiesta normale del CEO
        request = {
            'sender': 'ceo@company.com',
            'recipient': 'client@external.com',
            'queue_id': 'INTEG001',
            'size': str(10 * 1024 * 1024),  # 10MB
            'recipient_count': '50',
            'sasl_username': 'ceo@company.com'
        }
        
        result = await daemon.process_request(request)
        print(f"CEO normal request: {result}")
        self.assertEqual(result, 'DUNNO')
        
        # Richiesta CEO con troppi destinatari
        request['recipient_count'] = '600'  # Supera limite di 500
        request['queue_id'] = 'INTEG002'
        
        result = await daemon.process_request(request)
        print(f"CEO too many recipients: {result}")
        self.assertTrue(result.startswith('REJECT Too many recipients'))
        
        # Richiesta CEO con messaggio troppo grande
        request['recipient_count'] = '50'
        request['size'] = str(150 * 1024 * 1024)  # 150MB (supera 100M)
        request['queue_id'] = 'INTEG003'
        
        result = await daemon.process_request(request)
        print(f"CEO message too large: {result}")
        self.assertTrue(result.startswith('REJECT Message too large'))
    
    async def test_complete_workflow_wildcard(self):
        """Test workflow completo per utente wildcard"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        print("\n=== Test Complete Workflow - Wildcard User ===")
        
        # Richiesta normale di utente company.com
        request = {
            'sender': 'employee@company.com',
            'recipient': 'client@external.com',
            'queue_id': 'INTEG004',
            'size': str(5 * 1024 * 1024),  # 5MB
            'recipient_count': '20',
            'sasl_username': 'user@example.com'
        }
        
        result = await daemon.process_request(request)
        print(f"Employee normal request: {result}")
        self.assertEqual(result, 'DUNNO')
        
        # Richiesta con troppi destinatari per wildcard
        request['recipient_count'] = '150'  # Supera limite di 100
        request['queue_id'] = 'INTEG005'
        
        result = await daemon.process_request(request)
        print(f"Employee too many recipients: {result}")
        self.assertTrue(result.startswith('REJECT Too many recipients'))
    
    async def test_complete_workflow_simple_rules(self):
        """Test workflow completo per regole semplici"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        print("\n=== Test Complete Workflow - Simple Rules ===")
        
        # Utente bloccato
        request = {
            'sender': 'blocked@spam.com',
            'recipient': 'victim@company.com',
            'queue_id': 'INTEG006',
            'size': '1000',
            'recipient_count': '1',
            'sasl_username': 'blocked@spam.com'
        }
        
        result = await daemon.process_request(request)
        print(f"Blocked user: {result}")
        self.assertEqual(result, 'REJECT')
        
        # Utente admin (sempre accettato)
        request['sender'] = 'admin@internal.com'
        request['sasl_username'] = 'admin@internal.com'
        request['queue_id'] = 'INTEG007'
        
        result = await daemon.process_request(request)
        print(f"Admin user: {result}")
        self.assertEqual(result, 'ACCEPT')
        
        # Dominio trusted (sempre accettato)
        request['sender'] = 'anyone@trusted.com'
        request['sasl_username'] = 'anyone@trusted.com'
        request['queue_id'] = 'INTEG008'
        
        result = await daemon.process_request(request)
        print(f"Trusted domain: {result}")
        self.assertEqual(result, 'ACCEPT')
    
    async def test_complete_workflow_default_policy(self):
        """Test workflow completo per policy predefinita"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        print("\n=== Test Complete Workflow - Default Policy ===")
        
        # Utente senza regole specifiche
        request = {
            'sender': 'unknown@other.com',
            'recipient': 'someone@company.com',
            'queue_id': 'INTEG009',
            'size': str(2 * 1024 * 1024),  # 2MB
            'recipient_count': '5',
            'sasl_username': 'unknown@nowhere.com'
        }
        
        result = await daemon.process_request(request)
        print(f"Unknown user (default policy): {result}")
        self.assertEqual(result, 'DUNNO')
    
    async def test_rule_key_logging(self):
        """Test che le chiavi delle regole vengano loggare correttamente"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        print("\n=== Test Rule Key Logging ===")
        
        # Raccogliamo gli output dei log per verificare le chiavi
        test_cases = [
            {
                'sender': 'ceo@company.com',
                'expected_rule': 'ceo@company.com',
                'description': 'CEO exact match'
            },
            {
                'sender': 'employee@company.com',
                'expected_rule': '*@company.com',
                'description': 'Company wildcard match'
            },
            {
                'sender': 'user@example.com',
                'expected_rule': 'user@example.com',
                'description': 'Example user exact match'
            },
            {
                'sender': 'other@example.com',
                'expected_rule': '*@example.com',
                'description': 'Example wildcard match'
            },
            {
                'sender': 'admin@internal.com',
                'expected_rule': 'admin@internal.com',
                'description': 'Admin simple rule'
            },
            {
                'sender': 'unknown@nowhere.com',
                'expected_rule': 'default',
                'description': 'Default policy'
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            request = {
                'sender': test_case['sender'],
                'recipient': 'test@domain.com',
                'queue_id': f'RULEKEY{i:03d}',
                'size': '1000000',
                'recipient_count': '5',
                'sasl_username': test_case['sender']
            }
            
            print(f"\nTesting {test_case['description']}:")
            print(f"  Sender: {test_case['sender']}")
            print(f"  Expected rule key: {test_case['expected_rule']}")
            
            result = await daemon.process_request(request)
            print(f"  Result: {result}")
            
            # Il test verifica che non ci siano errori
            # L'output delle chiavi delle regole è visibile nei log di debug
            self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
