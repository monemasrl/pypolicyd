#!/usr/bin/env python3
"""
SMTP Policy Daemon in Python
Gestisce rate limiting e policy per Postfix tramite configurazione YAML
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from pypolicyd import PolicyDaemon


def setup_logging():
    """Configura logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def signal_handler(daemon):
    """Gestisce segnali di terminazione"""
    def handler(signum, frame):
        print(f"\nRicevuto segnale {signum}, fermando il daemon...")
        daemon.stop_server()
        sys.exit(0)
    return handler


async def main():
    """Funzione principale"""
    parser = argparse.ArgumentParser(description='PyPolicyd - SMTP Policy Daemon')
    parser.add_argument('--config', '-c', 
                       default='/etc/pypolicyd/main.yml',
                       help='File di configurazione (default: /etc/pypolicyd/main.yml)')
    parser.add_argument('--debug', '-d',
                       action='store_true',
                       help='Abilita modalità debug')
    
    args = parser.parse_args()
    
    # Controlla se il file di configurazione esiste
    if not Path(args.config).exists():
        print(f"ERRORE: File di configurazione non trovato: {args.config}")
        sys.exit(1)
    
    setup_logging()
    
    try:
        # Crea e avvia daemon
        daemon = PolicyDaemon(args.config, debug=args.debug)
        
        # Gestione segnali
        signal.signal(signal.SIGINT, signal_handler(daemon))
        signal.signal(signal.SIGTERM, signal_handler(daemon))
        
        # Avvia server
        await daemon.start_server()
        
    except Exception as e:
        print(f"ERRORE: {e}")
        logging.error(f"Errore fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
