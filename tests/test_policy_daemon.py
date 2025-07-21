#!/usr/bin/env python3
"""
Unit tests per PolicyDaemon
"""

import unittest
import tempfile
import yaml
import os
import sys
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

# Aggiungi il path dei moduli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'usr/lib/python3/dist-packages'))

from pypolicyd.policy_daemon import PolicyDaemon


class TestPolicyDaemon(unittest.TestCase):
    """Test per la classe PolicyDaemon"""
    
    def setUp(self):
        """Prepara i test creando file di configurazione temporanei"""
        # File di configurazione principale
        self.config_data = {
            'daemon': {
                'max_connections': 50,
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
        
        # Crea regole di test
        self.create_test_rules()
    
    def tearDown(self):
        """Pulisce i file temporanei"""
        if os.path.exists(self.config_file):
            os.unlink(self.config_file)
        
        # Rimuovi directory delle regole
        import shutil
        if os.path.exists(self.rules_dir):
            shutil.rmtree(self.rules_dir)
        
        # Rimuovi database di test se esiste
        db_path = '/tmp/test_rate_limits.db'
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    def create_test_rules(self):
        """Crea regole di test"""
        # Regole per example.com
        example_rules = {
            'user@example.com': {
                'max_recipients': 25,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h', '500/1d']
            },
            'marketing@example.com': {
                'max_recipients': 1000,
                'max_size': '25M',
                'rate_limits': ['100/1m', '1000/1h', '10000/1d']
            },
            '*@example.com': {
                'max_recipients': 10,
                'max_size': '5M',
                'rate_limits': ['3/1m', '30/1h', '300/1d']
            }
        }
        
        # Regole per company.com
        company_rules = {
            'ceo@company.com': {
                'max_recipients': 500,
                'max_size': '100M',
                'rate_limits': ['50/1m', '500/1h', '5000/1d']
            },
            '*@company.com': {
                'max_recipients': 100,
                'max_size': '50M',
                'rate_limits': ['20/1m', '200/1h', '2000/1d']
            }
        }
        
        # Scrivi i file delle regole
        with open(os.path.join(self.rules_dir, 'example.yml'), 'w') as f:
            yaml.dump(example_rules, f)
        
        with open(os.path.join(self.rules_dir, 'company.yml'), 'w') as f:
            yaml.dump(company_rules, f)
    
    def test_daemon_initialization(self):
        """Test inizializzazione daemon"""
        daemon = PolicyDaemon(self.config_file, debug=False)
        
        # Verifica configurazione
        self.assertEqual(daemon.bind_host, '127.0.0.1')
        self.assertEqual(daemon.bind_port, 10031)
        self.assertEqual(daemon.max_connections, 50)
        
        # Verifica che le regole siano caricate
        self.assertIsInstance(daemon.policy_rules, dict)
        self.assertIn('user@example.com', daemon.policy_rules)
        self.assertIn('*@example.com', daemon.policy_rules)
        self.assertIn('ceo@company.com', daemon.policy_rules)
        self.assertIn('*@company.com', daemon.policy_rules)
    
    def test_parse_size(self):
        """Test parsing dimensioni"""
        daemon = PolicyDaemon(self.config_file, debug=False)
        
        # Test vari formati
        self.assertEqual(daemon._parse_size("1024"), 1024)
        self.assertEqual(daemon._parse_size("1K"), 1024)
        self.assertEqual(daemon._parse_size("1M"), 1024 * 1024)
        self.assertEqual(daemon._parse_size("1G"), 1024 * 1024 * 1024)
        self.assertEqual(daemon._parse_size("10M"), 10 * 1024 * 1024)
        
        # Test formati con B
        self.assertEqual(daemon._parse_size("1KB"), 1024)
        self.assertEqual(daemon._parse_size("1MB"), 1024 * 1024)
        
        # Test formato non valido
        self.assertEqual(daemon._parse_size("invalid"), 0)


class TestPolicyDaemonAsync(unittest.IsolatedAsyncioTestCase):
    """Test asincroni per PolicyDaemon"""
    
    def setUp(self):
        """Prepara i test creando file di configurazione temporanei"""
        # File di configurazione principale
        self.config_data = {
            'daemon': {
                'max_connections': 50,
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
        
        # Crea regole di test
        self.create_test_rules()
    
    def tearDown(self):
        """Pulisce i file temporanei"""
        if os.path.exists(self.config_file):
            os.unlink(self.config_file)
        
        # Rimuovi directory delle regole
        import shutil
        if os.path.exists(self.rules_dir):
            shutil.rmtree(self.rules_dir)
        
        # Rimuovi database di test se esiste
        db_path = '/tmp/test_rate_limits.db'
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    def create_test_rules(self):
        """Crea regole di test"""
        # Regole per example.com
        example_rules = {
            'user@example.com': {
                'max_recipients': 25,
                'max_size': '10M',
                'rate_limits': ['5/1m', '50/1h', '500/1d']
            },
            'marketing@example.com': {
                'max_recipients': 1000,
                'max_size': '25M',
                'rate_limits': ['100/1m', '1000/1h', '10000/1d']
            },
            '*@example.com': {
                'max_recipients': 10,
                'max_size': '5M',
                'rate_limits': ['3/1m', '30/1h', '300/1d']
            }
        }
        
        # Regole per company.com
        company_rules = {
            'ceo@company.com': {
                'max_recipients': 500,
                'max_size': '100M',
                'rate_limits': ['50/1m', '500/1h', '5000/1d']
            },
            '*@company.com': {
                'max_recipients': 100,
                'max_size': '50M',
                'rate_limits': ['20/1m', '200/1h', '2000/1d']
            }
        }
        
        # Scrivi i file delle regole
        with open(os.path.join(self.rules_dir, 'example.yml'), 'w') as f:
            yaml.dump(example_rules, f)
        
        with open(os.path.join(self.rules_dir, 'company.yml'), 'w') as f:
            yaml.dump(company_rules, f)
    
    async def test_process_request_exact_match(self):
        """Test elaborazione richiesta con match esatto della regola"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        # Test richiesta per utente specifico
        request = {
            'sender': 'user@example.com',
            'recipient': 'test@domain.com',
            'queue_id': 'TEST001',
            'size': '1000000',  # 1MB
            'recipient_count': '5',
            'sasl_username': 'user@example.com'
        }
        
        result = await daemon.process_request(request)
        
        # Dovrebbe essere DUNNO (tutti i controlli passano)
        self.assertEqual(result, 'DUNNO')
    
    async def test_process_request_wildcard_match(self):
        """Test elaborazione richiesta con match wildcard"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        # Test richiesta per utente con wildcard
        request = {
            'sender': 'other@example.com',
            'recipient': 'test@domain.com',
            'queue_id': 'TEST002',
            'size': '1000000',  # 1MB
            'recipient_count': '5',
            'sasl_username': 'other'
        }
        
        result = await daemon.process_request(request)
        
        # Dovrebbe essere DUNNO (tutti i controlli passano)
        self.assertEqual(result, 'DUNNO')
    
    async def test_process_request_too_many_recipients(self):
        """Test elaborazione richiesta con troppi destinatari"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        # Test richiesta con troppi destinatari
        request = {
            'sender': 'user@example.com',
            'recipient': 'test@domain.com',
            'queue_id': 'TEST003',
            'size': '1000000',  # 1MB
            'recipient_count': '30',  # Supera il limite di 25
            'sasl_username': 'user@example.com'
        }
        
        result = await daemon.process_request(request)
        
        # Dovrebbe essere REJECT
        self.assertTrue(result.startswith('REJECT Too many recipients'))
        self.assertIn('30/25', result)
    
    async def test_process_request_message_too_large(self):
        """Test elaborazione richiesta con messaggio troppo grande"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        # Test richiesta con messaggio troppo grande
        request = {
            'sender': 'user@example.com',
            'recipient': 'test@domain.com',
            'queue_id': 'TEST004',
            'size': str(15 * 1024 * 1024),  # 15MB (supera il limite di 10M)
            'recipient_count': '5',
            'sasl_username': 'user@example.com'
        }
        
        result = await daemon.process_request(request)
        
        # Dovrebbe essere REJECT
        self.assertTrue(result.startswith('REJECT Message too large'))
    
    async def test_process_request_default_policy(self):
        """Test elaborazione richiesta con policy predefinita"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        # Test richiesta per utente senza regole specifiche
        request = {
            'sender': 'unknown@other.com',
            'recipient': 'test@domain.com',
            'queue_id': 'TEST005',
            'size': '1000000',  # 1MB
            'recipient_count': '5',
            'sasl_username': 'unknown'
        }
        
        result = await daemon.process_request(request)
        
        # Dovrebbe essere DUNNO (policy predefinita)
        self.assertEqual(result, 'DUNNO')
    
    @patch('pypolicyd.policy_daemon.PolicyLoggingService')
    async def test_logging_with_rule_keys(self, mock_logging_service):
        """Test che le chiavi delle regole vengano loggare correttamente"""
        daemon = PolicyDaemon(self.config_file, debug=True)
        
        # Mock del servizio di logging
        mock_logger = Mock()
        daemon.logging_service = mock_logger
        
        # Test richiesta per utente specifico
        request = {
            'sender': 'ceo@company.com',
            'recipient': 'test@domain.com',
            'queue_id': 'TEST006',
            'size': '1000000',  # 1MB
            'recipient_count': '5',
            'sasl_username': 'ceo@company.com'
        }
        
        result = await daemon.process_request(request)
        
        # Verifica che il logging sia stato chiamato
        self.assertTrue(mock_logger.log_policy_decision.called)
        
        # Verifica gli argomenti del log
        call_args = mock_logger.log_policy_decision.call_args
        queue_id, rules, request_data, action = call_args[0]
        
        self.assertEqual(queue_id, 'TEST006')
        self.assertIn('ceo@company.com', rules)  # La chiave della regola dovrebbe essere presente
        self.assertEqual(action, 'DUNNO')


if __name__ == '__main__':
    unittest.main()
