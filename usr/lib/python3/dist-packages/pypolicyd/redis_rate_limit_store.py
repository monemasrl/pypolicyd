"""
Redis-based rate limiting store for PyPolicyd
"""

import redis
import json
from typing import Tuple, Optional
from datetime import datetime, timedelta


class RedisRateLimitStore:
    """Gestione Redis per rate limiting"""
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, 
                 redis_db: int = 0, redis_password: Optional[str] = None,
                 key_prefix: str = 'pypolicyd:ratelimit:'):
        """
        Inizializza connessione Redis
        
        Args:
            redis_host: Host Redis (default: localhost)
            redis_port: Porta Redis (default: 6379)
            redis_db: Database Redis (default: 0)
            redis_password: Password Redis (opzionale)
            key_prefix: Prefisso per le chiavi Redis
        """
        self.key_prefix = key_prefix
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True  # Decodifica automaticamente le risposte
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
        """
        Rimuove entry scadute - con Redis non è necessario perché usa TTL automatico
        Manteniamo il metodo per compatibilità con l'interfaccia SQLite
        """
        # Redis gestisce automaticamente la scadenza delle chiavi con TTL
        pass
    
    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Controlla rate limit per una chiave usando Redis
        Returns: (is_allowed, current_count)
        
        Utilizza una strategia sliding window counter con Redis:
        - Chiave: prefisso + key
        - Valore: JSON con {count, first_seen, last_seen}
        - TTL: window_seconds dalla prima richiesta
        """
        redis_key = self._get_redis_key(key)
        now = datetime.now()
        
        # Usa una pipeline per operazioni atomiche
        pipe = self.redis_client.pipeline()
        
        try:
            # Controlla se la chiave esiste e non è scaduta
            existing_data = self.redis_client.get(redis_key)
            
            if existing_data:
                # Deserializza i dati esistenti
                data = json.loads(existing_data)
                first_seen = datetime.fromisoformat(data['first_seen'])
                current_count = data['count']
                
                # Controlla se siamo ancora nella finestra temporale
                if now <= first_seen + timedelta(seconds=window_seconds):
                    # Siamo nella stessa finestra - incrementa il contatore
                    new_count = current_count + 1
                    
                    # Aggiorna i dati
                    updated_data = {
                        'count': new_count,
                        'first_seen': data['first_seen'],  # Mantieni il first_seen originale
                        'last_seen': now.isoformat()
                    }
                    
                    # Calcola TTL rimanente
                    expires_at = first_seen + timedelta(seconds=window_seconds)
                    ttl_seconds = int((expires_at - now).total_seconds())
                    
                    if ttl_seconds > 0:
                        # Aggiorna con il TTL rimanente
                        pipe.setex(redis_key, ttl_seconds, json.dumps(updated_data))
                        pipe.execute()
                        
                        is_allowed = new_count <= limit
                        return is_allowed, new_count
                    else:
                        # La finestra è scaduta, ricomincia
                        current_count = 0
                else:
                    # La finestra è scaduta, ricomincia
                    current_count = 0
            else:
                # Nessun dato esistente
                current_count = 0
            
            # Prima richiesta nella finestra o finestra scaduta
            new_count = 1
            new_data = {
                'count': new_count,
                'first_seen': now.isoformat(),
                'last_seen': now.isoformat()
            }
            
            # Imposta con TTL = window_seconds
            pipe.setex(redis_key, window_seconds, json.dumps(new_data))
            pipe.execute()
            
            is_allowed = new_count <= limit
            return is_allowed, new_count
            
        except (redis.RedisError, json.JSONDecodeError, KeyError, ValueError) as e:
            # In caso di errore Redis, logga e permetti l'accesso (fail-open)
            # Questo evita che problemi di Redis blocchino tutto il sistema
            print(f"[WARNING] Errore Redis rate limiting per {key}: {e}")
            return True, 1
    
    def get_current_count(self, key: str) -> int:
        """
        Ottiene il conteggio corrente per una chiave senza incrementarlo
        Utile per monitoraggio e statistiche
        """
        redis_key = self._get_redis_key(key)
        
        try:
            existing_data = self.redis_client.get(redis_key)
            if existing_data:
                data = json.loads(existing_data)
                return data['count']
            return 0
        except (redis.RedisError, json.JSONDecodeError, KeyError):
            return 0
    
    def reset_rate_limit(self, key: str):
        """
        Resetta il rate limit per una chiave specifica
        Utile per testing o reset manuale
        """
        redis_key = self._get_redis_key(key)
        try:
            self.redis_client.delete(redis_key)
        except redis.RedisError as e:
            print(f"[WARNING] Errore durante reset rate limit per {key}: {e}")
    
    def get_all_keys(self) -> list:
        """
        Restituisce tutte le chiavi di rate limiting attive
        Utile per monitoraggio e debug
        """
        try:
            pattern = f"{self.key_prefix}*"
            keys = self.redis_client.keys(pattern)
            # Rimuovi il prefisso dalle chiavi
            return [key.replace(self.key_prefix, '') for key in keys]
        except redis.RedisError:
            return []
    
    def get_stats(self) -> dict:
        """
        Restituisce statistiche generali del rate limiting
        """
        try:
            all_keys = self.get_all_keys()
            stats = {
                'total_active_keys': len(all_keys),
                'keys': []
            }
            
            for key in all_keys[:50]:  # Limita a 50 per performance
                redis_key = self._get_redis_key(key)
                data = self.redis_client.get(redis_key)
                if data:
                    parsed_data = json.loads(data)
                    ttl = self.redis_client.ttl(redis_key)
                    stats['keys'].append({
                        'key': key,
                        'count': parsed_data['count'],
                        'first_seen': parsed_data['first_seen'],
                        'last_seen': parsed_data['last_seen'],
                        'ttl_seconds': ttl
                    })
            
            return stats
        except (redis.RedisError, json.JSONDecodeError):
            return {'total_active_keys': 0, 'keys': []}
    
    def close(self):
        """Chiude la connessione Redis"""
        try:
            self.redis_client.close()
        except:
            pass


# Alias per compatibilità - mantieni la stessa interfaccia del SQLite store
class RateLimitStore(RedisRateLimitStore):
    """
    Alias per RedisRateLimitStore per mantenere compatibilità
    """
    
    def __init__(self, db_path: str = None, **kwargs):
        """
        Mantiene compatibilità con l'interfaccia SQLite ma usa Redis
        
        Args:
            db_path: Ignorato (per compatibilità con SQLite)
            **kwargs: Parametri Redis (redis_host, redis_port, etc.)
        """
        # Estrai parametri Redis dai kwargs se presenti
        redis_config = {
            'redis_host': kwargs.get('redis_host', 'localhost'),
            'redis_port': kwargs.get('redis_port', 6379),
            'redis_db': kwargs.get('redis_db', 0),
            'redis_password': kwargs.get('redis_password', None),
            'key_prefix': kwargs.get('key_prefix', 'pypolicyd:ratelimit:')
        }
        
        super().__init__(**redis_config)
