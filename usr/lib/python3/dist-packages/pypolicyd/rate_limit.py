"""
Rate limiting classes for PyPolicyd
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime


class RateLimit:
    """Gestisce rate limit con formato flessibile come '10/1m/REJECT', '100/5m/DEFER', etc."""
    
    UNIT_MULTIPLIERS = {
        's': 1,           # secondi
        'm': 60,          # minuti  
        'h': 3600,        # ore
        'd': 86400,       # giorni
        'M': 2592000,     # mesi (30 giorni)
    }
    
    VALID_ACTIONS = {'REJECT', 'DEFER', 'DUNNO'}
    
    def __init__(self, rate_str: str):
        self.rate_str = rate_str
        self.count, self.window_seconds, self.action = self._parse_rate(rate_str)
        
        # Proprietà per compatibilità con il daemon
        self.limit = self.count
        self.window = self.window_seconds
        
    def _parse_rate(self, rate_str: str) -> Tuple[int, int, str]:
        """Parse rate string formato 'count/time_unit' o 'count/time_unit/action'"""
        # Formato nuovo: count/time_unit/action
        pattern_with_action = r'^(\d+)/(\d+)([smhdM])/(REJECT|DEFER|DUNNO)$'
        match = re.match(pattern_with_action, rate_str)
        
        if match:
            count = int(match.group(1))
            time_value = int(match.group(2))
            time_unit = match.group(3)
            action = match.group(4)
            
            if time_unit not in self.UNIT_MULTIPLIERS:
                raise ValueError(f"Invalid time unit: {time_unit}. Valid units: {list(self.UNIT_MULTIPLIERS.keys())}")
            
            if action not in self.VALID_ACTIONS:
                raise ValueError(f"Invalid action: {action}. Valid actions: {list(self.VALID_ACTIONS)}")
                
            window_seconds = time_value * self.UNIT_MULTIPLIERS[time_unit]
            return count, window_seconds, action
        
        # Formato legacy: count/time_unit (default action: REJECT)
        pattern_legacy = r'^(\d+)/(\d+)([smhdM])$'
        match = re.match(pattern_legacy, rate_str)
        
        if match:
            count = int(match.group(1))
            time_value = int(match.group(2))
            time_unit = match.group(3)
            
            if time_unit not in self.UNIT_MULTIPLIERS:
                raise ValueError(f"Invalid time unit: {time_unit}. Valid units: {list(self.UNIT_MULTIPLIERS.keys())}")
                
            window_seconds = time_value * self.UNIT_MULTIPLIERS[time_unit]
            return count, window_seconds, 'REJECT'  # Default action
        
        raise ValueError(f"Invalid rate format: {rate_str}. Expected format: 'count/time_unit' or 'count/time_unit/action' (e.g., '10/1m', '100/5m/DEFER')")
    
    def __str__(self):
        return f"RateLimit({self.rate_str}: {self.count} per {self.window_seconds}s, action: {self.action})"
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'RateLimit':
        """Crea un RateLimit da configurazione con limit/window/action opzionale"""
        limit = config.get('limit', 10)
        window = config.get('window', 60)
        action = config.get('action', 'REJECT')
        
        # Converte in formato stringa rate_str
        if window < 60:
            rate_str = f"{limit}/{window}s/{action}"
        elif window < 3600:
            rate_str = f"{limit}/{window//60}m/{action}"
        elif window < 86400:
            rate_str = f"{limit}/{window//3600}h/{action}"
        else:
            rate_str = f"{limit}/{window//86400}d/{action}"
        
        return cls(rate_str)


class MultiWindowRateTracker:
    """Traccia rate limiting su multiple finestre temporali"""
    
    def __init__(self, rate_limits: List[RateLimit]):
        self.rate_limits = rate_limits
        self.counters: Dict[Tuple[str, float], List[float]] = {}  # key: (user, window_seconds) -> list of timestamps
        
    def check_rate_limits(self, user: str, current_time: Optional[datetime] = None) -> Tuple[bool, str, str]:
        """
        Controlla se l'utente ha superato qualche rate limit
        Returns: (is_allowed, reason, action)
        """
        if current_time is None:
            current_time = datetime.now()
            
        current_timestamp = current_time.timestamp()
        
        for rate_limit in self.rate_limits:
            key = (user, rate_limit.window_seconds)
            
            # Inizializza counter se non esiste
            if key not in self.counters:
                self.counters[key] = []
                
            # Rimuovi timestamp vecchi fuori dalla finestra
            cutoff_time = current_timestamp - rate_limit.window_seconds
            self.counters[key] = [ts for ts in self.counters[key] if ts > cutoff_time]
            
            # Controlla se abbiamo superato il limite
            current_count = len(self.counters[key])
            if current_count >= rate_limit.count:
                reason = f"Rate limit exceeded: {current_count}/{rate_limit.count} in {rate_limit.rate_str}"
                return False, reason, rate_limit.action
                
        return True, "OK", "DUNNO"
    
    def record_request(self, user: str, current_time: Optional[datetime] = None):
        """Registra una richiesta per l'utente"""
        if current_time is None:
            current_time = datetime.now()
            
        current_timestamp = current_time.timestamp()
        
        for rate_limit in self.rate_limits:
            key = (user, rate_limit.window_seconds)
            if key not in self.counters:
                self.counters[key] = []
            self.counters[key].append(current_timestamp)
    
    def cleanup_old_counters(self, current_time: Optional[datetime] = None):
        """Pulisce i counter vecchi per risparmiare memoria"""
        if current_time is None:
            current_time = datetime.now()
            
        current_timestamp = current_time.timestamp()
        
        for key in list(self.counters.keys()):
            user, window_seconds = key
            cutoff_time = current_timestamp - window_seconds
            self.counters[key] = [ts for ts in self.counters[key] if ts > cutoff_time]
            
            # Rimuovi chiavi vuote
            if not self.counters[key]:
                del self.counters[key]
