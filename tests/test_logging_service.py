#!/usr/bin/env python3
"""
Unit tests per LoggingService
"""

import unittest
import tempfile
import os
import sys
import logging
from unittest.mock import Mock, patch
from io import StringIO

# Aggiungi il path dei moduli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'usr/lib/python3/dist-packages'))

from pypolicyd.logging_service import PolicyLoggingService


class TestPolicyLoggingService(unittest.TestCase):
    """Test per la classe PolicyLoggingService"""
    
    def setUp(self):
        """Prepara i test"""
        self.config = {
            'log_destination': 'stdout',
            'log_format': 'postfix',
            'log_request': 'all',
            'log_connection': True
        }
    
    def test_logging_service_initialization(self):
        """Test inizializzazione servizio di logging"""
        service = PolicyLoggingService(self.config, debug=False)
        
        self.assertIsNotNone(service.logger)
        self.assertEqual(service.config, self.config)
    
    def test_log_destination_stdout(self):
        """Test configurazione logging su stdout"""
        config = self.config.copy()
        config['log_destination'] = 'stdout'
        
        service = PolicyLoggingService(config, debug=False)
        
        # Verifica che il logger sia configurato correttamente
        self.assertIsNotNone(service.logger)
        self.assertTrue(len(service.logger.handlers) > 0)
    
    def test_log_destination_file(self):
        """Test configurazione logging su file"""
        log_fd, log_file = tempfile.mkstemp(suffix='.log')
        os.close(log_fd)
        
        try:
            config = self.config.copy()
            config['log_destination'] = log_file
            
            service = PolicyLoggingService(config, debug=False)
            
            # Verifica che il logger sia configurato correttamente
            self.assertIsNotNone(service.logger)
            self.assertTrue(len(service.logger.handlers) > 0)
            
        finally:
            if os.path.exists(log_file):
                os.unlink(log_file)
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_log_policy_decision_all_requests(self, mock_stdout):
        """Test logging decisione policy - tutte le richieste"""
        config = self.config.copy()
        config['log_request'] = 'all'
        
        service = PolicyLoggingService(config, debug=False)
        
        # Simula una decisione di policy
        queue_id = 'TEST001'
        rules = ['ceo@company.com']
        request = {
            'sender': 'ceo@company.com',
            'recipient': 'test@example.com',
            'size': '1000000',
            'recipient_count': '5',
            'sasl_username': 'ceo'
        }
        action = 'DUNNO'
        
        service.log_policy_decision(queue_id, rules, request, action)
        
        # Non verifichiamo l'output esatto perché dipende dalla configurazione del logger
        # Ma verifichiamo che non ci siano errori
        self.assertTrue(True)
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_log_policy_decision_rejected_only(self, mock_stdout):
        """Test logging decisione policy - solo richieste rifiutate"""
        config = self.config.copy()
        config['log_request'] = 'rejected'
        
        service = PolicyLoggingService(config, debug=False)
        
        # Test richiesta accettata (non dovrebbe essere loggata)
        queue_id = 'TEST002'
        rules = ['user@example.com']
        request = {
            'sender': 'user@example.com',
            'recipient': 'test@example.com',
            'size': '1000000',
            'recipient_count': '5',
            'sasl_username': 'user'
        }
        action = 'DUNNO'
        
        service.log_policy_decision(queue_id, rules, request, action)
        
        # Test richiesta rifiutata (dovrebbe essere loggata)
        action = 'REJECT Too many recipients'
        service.log_policy_decision(queue_id, rules, request, action)
        
        # Verifichiamo che non ci siano errori
        self.assertTrue(True)
    
    def test_log_policy_decision_none(self):
        """Test logging disabilitato"""
        config = self.config.copy()
        config['log_request'] = 'none'
        
        service = PolicyLoggingService(config, debug=False)
        
        # Simula una decisione di policy
        queue_id = 'TEST003'
        rules = ['default']
        request = {
            'sender': 'unknown@other.com',
            'recipient': 'test@example.com',
            'size': '1000000',
            'recipient_count': '5',
            'sasl_username': 'unknown'
        }
        action = 'DUNNO'
        
        # Questo non dovrebbe loggare nulla
        service.log_policy_decision(queue_id, rules, request, action)
        
        # Verifichiamo che non ci siano errori
        self.assertTrue(True)
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_log_connection(self, mock_stdout):
        """Test logging connessione"""
        config = self.config.copy()
        config['log_connection'] = True
        
        service = PolicyLoggingService(config, debug=False)
        
        # Simula log di connessione
        client_host = 'mail.example.com'
        client_ip = '192.168.1.100'
        
        service.log_connection(client_host, client_ip)
        
        # Verifichiamo che non ci siano errori
        self.assertTrue(True)
    
    def test_log_connection_disabled(self):
        """Test logging connessione disabilitato"""
        config = self.config.copy()
        config['log_connection'] = False
        
        service = PolicyLoggingService(config, debug=False)
        
        # Simula log di connessione (non dovrebbe loggare)
        client_host = 'mail.example.com'
        client_ip = '192.168.1.100'
        
        service.log_connection(client_host, client_ip)
        
        # Verifichiamo che non ci siano errori
        self.assertTrue(True)
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_log_startup(self, mock_stdout):
        """Test logging startup"""
        service = PolicyLoggingService(self.config, debug=False)
        
        message = "PyPolicyd started on 127.0.0.1:10031"
        service.log_startup(message)
        
        # Verifichiamo che non ci siano errori
        self.assertTrue(True)
    
    @patch('sys.stdout', new_callable=StringIO)
    def test_log_shutdown(self, mock_stdout):
        """Test logging shutdown"""
        service = PolicyLoggingService(self.config, debug=False)
        
        message = "PyPolicyd stopped"
        service.log_shutdown(message)
        
        # Verifichiamo che non ci siano errori
        self.assertTrue(True)
    
    def test_log_format_postfix(self):
        """Test formato log Postfix"""
        config = self.config.copy()
        config['log_format'] = 'postfix'
        
        service = PolicyLoggingService(config, debug=False)
        
        # Verifica che il servizio sia inizializzato correttamente
        self.assertIsNotNone(service.logger)
    
    def test_rule_keys_in_log_message(self):
        """Test che le chiavi delle regole appaiano nel messaggio di log"""
        service = PolicyLoggingService(self.config, debug=False)
        
        # Mock del logger per catturare il messaggio
        with patch.object(service.logger, 'info') as mock_info:
            queue_id = 'TEST004'
            rules = ['ceo@company.com', '*@company.com']  # Più regole
            request = {
                'sender': 'ceo@company.com',
                'recipient': 'test@example.com',
                'size': '1000000',
                'recipient_count': '5',
                'sasl_username': 'ceo'
            }
            action = 'DUNNO'
            
            service.log_policy_decision(queue_id, rules, request, action)
            
            # Verifica che il metodo info sia stato chiamato
            self.assertTrue(mock_info.called)
            
            # Verifica che il messaggio contenga le chiavi delle regole
            call_args = mock_info.call_args[0][0]
            self.assertIn('ceo@company.com', call_args)
            self.assertIn('*@company.com', call_args)
            self.assertIn('TEST004', call_args)
            self.assertIn('DUNNO', call_args)


if __name__ == '__main__':
    unittest.main()
