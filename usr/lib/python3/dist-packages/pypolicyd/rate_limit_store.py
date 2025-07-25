"""
Rate limiting store for PyPolicyd - supports both SQLite and Redis
"""

import sqlite3
import json
from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timedelta

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None


class SQLiteRateLimitStore:
    """Gestione SQLite per rate limiting (implementazione originale)"""
    
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


class RedisRateLimitStore:
    """Gestione Redis per rate limiting - più veloce e scalabile"""
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, 
                 redis_db: int = 0, redis_password: Optional[str] = None,
                 key_prefix: str = 'pypolicyd:ratelimit:'):
        """
        Inizializza connessione Redis
        """
        if not REDIS_AVAILABLE:
            raise ImportError("Redis library not available. Install with: pip install redis")
            
        self.key_prefix = key_prefix
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        
        # Test connessione
        try:
            self.redis_client.ping()
        except redis.ConnectionError as e:
            raise ConnectionError(f"Impossibile connettersi a Redis: {e}")
    
    def _get_redis_key(self, key: str) -> str:
        """Genera chiave Redis con prefisso"""
        return f"{self.key_prefix}{key}"
    
    def cleanup_expired(self):
        """Redis gestisce automaticamente la scadenza con TTL"""
        pass
    
    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Controlla rate limit usando Redis con sliding window
        Returns: (is_allowed, current_count)
        """
        redis_key = self._get_redis_key(key)
        now = datetime.now()
        
        try:
            # Controlla se la chiave esiste
            existing_data = self.redis_client.get(redis_key)
            
            if existing_data:
                # Deserializza i dati esistenti
                data = json.loads(existing_data)
                first_seen = datetime.fromisoformat(data['first_seen'])
                current_count = data['count']
                
                # Controlla se siamo nella finestra temporale
                if now <= first_seen + timedelta(seconds=window_seconds):
                    # Incrementa il contatore
                    new_count = current_count + 1
                    
                    # Aggiorna i dati
                    updated_data = {
                        'count': new_count,
                        'first_seen': data['first_seen'],
                        'last_seen': now.isoformat()
                    }
                    
                    # Calcola TTL rimanente
                    expires_at = first_seen + timedelta(seconds=window_seconds)
                    ttl_seconds = int((expires_at - now).total_seconds())
                    
                    if ttl_seconds > 0:
                        self.redis_client.setex(redis_key, ttl_seconds, json.dumps(updated_data))
                        is_allowed = new_count <= limit
                        return is_allowed, new_count
            
            # Prima richiesta nella finestra o finestra scaduta
            new_count = 1
            new_data = {
                'count': new_count,
                'first_seen': now.isoformat(),
                'last_seen': now.isoformat()
            }
            
            # Imposta con TTL
            self.redis_client.setex(redis_key, window_seconds, json.dumps(new_data))
            
            is_allowed = new_count <= limit
            return is_allowed, new_count
            
        except (redis.RedisError, json.JSONDecodeError, KeyError, ValueError) as e:
            # Fail-open in caso di errore Redis
            print(f"[WARNING] Errore Redis rate limiting per {key}: {e}")
            return True, 1


class RateLimitStore:
    """
    Factory class che crea SQLite o Redis store basato sulla configurazione
    """
    
    @staticmethod
    def create(config: Dict[str, Any]) -> object:
        """
        Crea uno store basato sulla configurazione
        
        Args:
            config: Dizionario con configurazione, può contenere:
                - 'type': 'sqlite' o 'redis' 
                - 'db_path': per SQLite
                - 'redis_host', 'redis_port', etc: per Redis
        
        Returns:
            SQLiteRateLimitStore o RedisRateLimitStore
        """
        store_type = config.get('type', 'sqlite').lower()
        
        if store_type == 'redis':
            if not REDIS_AVAILABLE:
                print("[WARNING] Redis non disponibile, fallback a SQLite")
                return SQLiteRateLimitStore(config.get('db_path', '/tmp/pypolicyd_fallback.db'))
            
            redis_config = {
                'redis_host': config.get('redis_host', 'localhost'),
                'redis_port': config.get('redis_port', 6379),
                'redis_db': config.get('redis_db', 0),
                'redis_password': config.get('redis_password', None),
                'key_prefix': config.get('key_prefix', 'pypolicyd:ratelimit:')
            }
            
            try:
                return RedisRateLimitStore(**redis_config)
            except ConnectionError as e:
                print(f"[WARNING] Impossibile connettersi a Redis: {e}, fallback a SQLite")
                return SQLiteRateLimitStore(config.get('db_path', '/tmp/pypolicyd_fallback.db'))
        
        else:  # SQLite (default)
            db_path = config.get('db_path', '/tmp/pypolicyd.db')
            return SQLiteRateLimitStore(db_path)
    
    def __init__(self, db_path: str):
        """Mantiene compatibilità con l'interfaccia originale (solo SQLite)"""
        self._store = SQLiteRateLimitStore(db_path)
    
    def cleanup_expired(self):
        """Delega al store sottostante"""
        return self._store.cleanup_expired()
    
    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """Delega al store sottostante"""
        return self._store.check_rate_limit(key, limit, window_seconds)
