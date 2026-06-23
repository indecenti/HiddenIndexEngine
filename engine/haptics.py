"""
engine/haptics.py

Feedback aptico (vibrazione) per Android. No-op completo su desktop/EXE.

Best-effort via pyjnius/Vibrator, stesso pattern difensivo di
utils.get_android_safe_insets: qualsiasi errore degrada silenziosamente a no-op.
Le durate sono brevi e calibrate per un HOG (feedback discreto, non invadente).

API pubblica:
    haptics.set_enabled(bool)   # da impostazioni utente (opt_vibration)
    haptics.is_enabled()
    haptics.tick()              # micro feedback (UI/hint)
    haptics.found()             # oggetto trovato
    haptics.miss()              # errore / click a vuoto
    haptics.success_strong()    # ultimo oggetto / vittoria
"""

from engine.utils import is_android_runtime, get_logger

log = get_logger(__name__)

# Stato modulo (singleton): attivazione utente + handle lazy al servizio Vibrator.
_enabled: bool = True
_vibrator = None
_resolved: bool = False
_has_effect: bool = False
_VibrationEffect = None


def set_enabled(value: bool) -> None:
    """Abilita/disabilita gli haptics (impostazione utente). Default: abilitato."""
    global _enabled
    _enabled = bool(value)


def is_enabled() -> bool:
    return _enabled


def _resolve() -> None:
    """Risolve (una volta) il servizio Vibrator via pyjnius. Se l'Activity non e'
    ancora pronta lascia _resolved=False per riprovare al prossimo evento."""
    global _vibrator, _resolved, _has_effect, _VibrationEffect
    if _resolved:
        return
    if not is_android_runtime():
        _resolved = True
        return
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        if activity is None:
            return  # riprova piu' tardi: non segnamo _resolved
        Context = autoclass('android.content.Context')
        _vibrator = activity.getSystemService(Context.VIBRATOR_SERVICE)
        try:
            _VibrationEffect = autoclass('android.os.VibrationEffect')  # API 26+
            _has_effect = _VibrationEffect is not None
        except Exception:
            _has_effect = False
        _resolved = True
    except Exception as exc:
        log.debug(f"[haptics] non disponibile: {exc}")
        _vibrator = None
        _resolved = True


def _vibrate_ms(ms: int) -> None:
    if not _enabled or not is_android_runtime():
        return
    _resolve()
    v = _vibrator
    if v is None:
        return
    try:
        if not v.hasVibrator():
            return
    except Exception:
        pass
    try:
        if _has_effect and _VibrationEffect is not None:
            eff = _VibrationEffect.createOneShot(int(ms), _VibrationEffect.DEFAULT_AMPLITUDE)
            v.vibrate(eff)
        else:
            v.vibrate(int(ms))  # deprecato (API < 26), ma valido
    except Exception as exc:
        log.debug(f"[haptics] vibrate fallita: {exc}")


def tick() -> None:
    """Micro feedback per interazioni UI (hint, pulsanti)."""
    _vibrate_ms(12)


def found() -> None:
    """Feedback al ritrovamento di un oggetto."""
    _vibrate_ms(28)


def miss() -> None:
    """Feedback su click a vuoto / errore."""
    _vibrate_ms(45)


def success_strong() -> None:
    """Feedback piu' marcato per l'ultimo oggetto / vittoria scena."""
    _vibrate_ms(70)
