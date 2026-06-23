"""
tests/test_haptics.py

Fase 3 mobile: modulo feedback aptico. Su desktop (no Android) ogni funzione e'
un no-op che non deve mai sollevare; l'enable/disable utente e' rispettato.
"""

import engine.haptics as haptics


class TestHaptics:
    def teardown_method(self):
        haptics.set_enabled(True)  # ripristina default tra i test

    def test_enable_disable_flag(self):
        haptics.set_enabled(False)
        assert haptics.is_enabled() is False
        haptics.set_enabled(True)
        assert haptics.is_enabled() is True

    def test_all_calls_noop_on_desktop(self):
        # Nessuna eccezione: su desktop is_android_runtime() e' False -> no-op.
        haptics.set_enabled(True)
        haptics.tick()
        haptics.found()
        haptics.miss()
        haptics.success_strong()

    def test_calls_noop_when_disabled(self):
        haptics.set_enabled(False)
        haptics.tick()
        haptics.found()
        haptics.miss()
        haptics.success_strong()
