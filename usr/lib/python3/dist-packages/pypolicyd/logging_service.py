"""
Logging service for PyPolicyd
Gestisce il logging configurabile per policy decisions
"""

import logging
import logging.handlers
import sys
import os
from pathlib import Path
from typing import Dict, Any


class PolicyLoggingService:
    """Servizio di logging per policy decisions"""
    
    def __init__(self, config: Dict[str, Any], debug: bool = False):
        self.config = config
        self.debug = debug
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """Configura logger per policy decisions"""
        logger = logging.getLogger('pypolicyd.policy')
        logger.setLevel(logging.INFO)
        
        # Rimuovi handler esistenti per evitare duplicati
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Formato personalizzato senza timestamp per output Postfix-style
        formatter = logging.Formatter('%(message)s')
        
        # Configurazione output
        log_to_syslog = self.config.get('log_to_syslog', False)
        log_file = self.config.get('log_file', None)
        
        if log_to_syslog:
            self._setup_syslog_handler(logger, formatter)
        elif log_file:
            self._setup_file_handler(logger, formatter, log_file)
        else:
            self._setup_console_handler(logger, formatter)
        
        # Non propagare al logger root per evitare duplicati
        logger.propagate = False
        
        return logger
    
    def _setup_syslog_handler(self, logger: logging.Logger, formatter: logging.Formatter):
        """Configura handler per syslog"""
        syslog_facility = self.config.get('syslog_facility', 'mail')
        facility_map = {
            'mail': logging.handlers.SysLogHandler.LOG_MAIL,
            'daemon': logging.handlers.SysLogHandler.LOG_DAEMON,
            'user': logging.handlers.SysLogHandler.LOG_USER,
            'local0': logging.handlers.SysLogHandler.LOG_LOCAL0,
            'local1': logging.handlers.SysLogHandler.LOG_LOCAL1,
            'local2': logging.handlers.SysLogHandler.LOG_LOCAL2,
            'local3': logging.handlers.SysLogHandler.LOG_LOCAL3,
            'local4': logging.handlers.SysLogHandler.LOG_LOCAL4,
            'local5': logging.handlers.SysLogHandler.LOG_LOCAL5,
            'local6': logging.handlers.SysLogHandler.LOG_LOCAL6,
            'local7': logging.handlers.SysLogHandler.LOG_LOCAL7,
        }
        
        try:
            facility = facility_map.get(syslog_facility, logging.handlers.SysLogHandler.LOG_MAIL)
            syslog_handler = logging.handlers.SysLogHandler(
                address='/dev/log',
                facility=facility
            )
            syslog_handler.setFormatter(formatter)
            logger.addHandler(syslog_handler)
            
            if self.debug:
                print(f"[DEBUG] Policy logger configurato per syslog (facility: {syslog_facility})")
                
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] Errore configurazione syslog: {e}, fallback a stdout")
            # Fallback a stdout
            self._setup_console_handler(logger, formatter)
    
    def _setup_file_handler(self, logger: logging.Logger, formatter: logging.Formatter, log_file: str):
        """Configura handler per file"""
        try:
            # Crea directory se non esiste
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            if self.debug:
                print(f"[DEBUG] Policy logger configurato per file: {log_file}")
                
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] Errore configurazione log file: {e}, fallback a stdout")
            # Fallback a stdout
            self._setup_console_handler(logger, formatter)
    
    def _setup_console_handler(self, logger: logging.Logger, formatter: logging.Formatter):
        """Configura handler per console (stdout)"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        if self.debug:
            print(f"[DEBUG] Policy logger configurato per stdout")
    
    def log_policy_decision(self, queue_id: str, rules: list, request: Dict[str, str], action: str):
        """Log decisione policy in formato Postfix"""
        # Controlla se il logging delle richieste è abilitato
        log_request = self.config.get('log_request', 'all').lower()
        
        if log_request == 'none':
            return
        elif log_request == 'rejected':
            # Log solo per azioni di rifiuto
            if not (action.startswith('REJECT') or action.startswith('DISCARD') or action.startswith('DEFER')):
                return
        # Se log_request == 'all', procedi sempre
        
        pid = os.getpid()
        sender = request.get('sender', '')
        recipient = request.get('recipient', '')
        size = request.get('size', '0')
        nrcpt = request.get('recipient_count', '1')
        sasl_user = request.get('sasl_username', '')
        
        # Log in formato Postfix
        log_msg = (f"pypolicyd[{pid}]: {queue_id}: [CHECK] "
                  f"rule={'|'.join(rules) if rules else 'default'}, "
                  f"user={sasl_user}, sender={sender}, recipient={recipient}, "
                  f"size={size}, nrcpt={nrcpt}, action={action}")
        
        # Usa il logger configurato
        self.logger.info(log_msg)
    
    def log_connection(self, client_host: str, client_ip: str):
        """Log connessione client"""
        log_connection = self.config.get('log_connection', False)
        
        if log_connection:
            pid = os.getpid()
            log_msg = f"pypolicyd[{pid}]: connect from {client_host}[{client_ip}]"
            self.logger.info(log_msg)
    
    def log_startup(self, message: str):
        """Log messaggi di avvio del daemon"""
        self.logger.info(f"[STARTUP] {message}")

    def log_shutdown(self, message: str):
        """Log messaggi di spegnimento del daemon"""
        self.logger.info(f"[SHUTDOWN] {message}")

    def reconfigure(self, new_config: Dict[str, Any]):
        """Riconfigura il logger con nuove impostazioni"""
        self.config = new_config
        self.logger = self._setup_logger()
        
        if self.debug:
            print(f"[DEBUG] Logger riconfigurato con nuove impostazioni")
