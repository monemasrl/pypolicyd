#!/usr/bin/env python3
"""
Test runner per tutti i test di PyPolicyd
"""

import unittest
import sys
import os

# Aggiungi il path dei moduli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'usr/lib/python3/dist-packages'))

def run_all_tests():
    """Esegue tutti i test"""
    # Discover e carica tutti i test
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(__file__)
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Esegui i test
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Restituisci codice di uscita appropriato
    return 0 if result.wasSuccessful() else 1

def run_specific_test(test_module):
    """Esegue un test specifico"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(test_module)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Esegui test specifico
        test_module = sys.argv[1]
        sys.exit(run_specific_test(test_module))
    else:
        # Esegui tutti i test
        sys.exit(run_all_tests())
