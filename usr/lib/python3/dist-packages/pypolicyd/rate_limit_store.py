"""
SQLite-based rate limiting store for PyPolicyd
"""

import sqlite3
from typing import Tuple
from datetime import datetime, timedelta


class RateLimitStore:
    """Gestione SQLite per rate limiting"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inizializza il database SQLite"""
        conn = sqlite3.connect(self.db_path)
        
        # Tabella per rate limiting
        conn.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                key TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                expires TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_expires ON rate_limits(expires)
        ''')
        
        conn.commit()
        conn.close()
    
    def cleanup_expired(self):
        """Rimuove entry scadute"""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now()
        conn.execute('DELETE FROM rate_limits WHERE expires < ?', (now.isoformat(),))
        conn.commit()
        conn.close()
    
    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Controlla rate limit per una chiave
        Returns: (is_allowed, current_count)
        """
        conn = sqlite3.connect(self.db_path)
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        
        # Cleanup entry scadute per questa chiave
        conn.execute('DELETE FROM rate_limits WHERE key = ? AND expires < ?', (key, now.isoformat()))
        
        # Conta richieste nella finestra temporale
        cursor = conn.execute(
            'SELECT count, first_seen FROM rate_limits WHERE key = ? AND first_seen >= ?',
            (key, window_start.isoformat())
        )
        result = cursor.fetchone()
        
        if result:
            current_count, first_seen = result
            # Incrementa contatore
            new_count = current_count + 1
            expires = datetime.fromisoformat(first_seen) + timedelta(seconds=window_seconds)
            
            conn.execute(
                'UPDATE rate_limits SET count = ?, last_seen = ?, expires = ? WHERE key = ?',
                (new_count, now.isoformat(), expires.isoformat(), key)
            )
        else:
            # Prima richiesta nella finestra
            new_count = 1
            expires = now + timedelta(seconds=window_seconds)
            
            conn.execute(
                'INSERT OR REPLACE INTO rate_limits (key, count, first_seen, last_seen, expires) VALUES (?, ?, ?, ?, ?)',
                (key, new_count, now.isoformat(), now.isoformat(), expires.isoformat())
            )
        
        conn.commit()
        conn.close()
        
        is_allowed = new_count <= limit
        return is_allowed, new_count
