#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PyPolicyd - SMTP Policy Daemon in Python
Gestisce rate limiting e policy per Postfix tramite configurazione YAML
"""

from .policy_daemon import PolicyDaemon
from .policy_config import PolicyConfig  
from .rate_limit import RateLimit, MultiWindowRateTracker
from .rate_limit_store import RateLimitStore
from .logging_service import PolicyLoggingService

__version__ = "1.0.0"
__author__ = "Andrea Bettarini"
__email__ = "bettarini@monema.it"
__all__ = ['PolicyDaemon', 'PolicyConfig', 'RateLimit', 'MultiWindowRateTracker', 'RateLimitStore', 'PolicyLoggingService']