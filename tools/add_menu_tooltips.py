"""Inserisce le chiavi tooltip del menu nei 5 file stringhe senza riformattare
il resto del file (inserimento testuale prima della graffa finale)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STR = ROOT / "engine" / "assets" / "strings"

TIPS = {
    "tip_play": {
        "it": "Inizia a giocare e scegli un livello",
        "en": "Start playing and choose a level",
        "es": "Empieza a jugar y elige un nivel",
        "fr": "Commence à jouer et choisis un niveau",
        "de": "Spiel starten und Level wählen",
    },
    "tip_continue": {
        "it": "Riprendi la partita salvata",
        "en": "Resume your saved game",
        "es": "Reanuda la partida guardada",
        "fr": "Reprends la partie sauvegardée",
        "de": "Gespeichertes Spiel fortsetzen",
    },
    "tip_new_game": {
        "it": "Cancella i progressi e ricomincia da capo",
        "en": "Erase your progress and start over",
        "es": "Borra el progreso y empieza de nuevo",
        "fr": "Efface ta progression et recommence",
        "de": "Fortschritt löschen und neu beginnen",
    },
    "tip_settings": {
        "it": "Audio, lingua e impostazioni schermo",
        "en": "Audio, language and display settings",
        "es": "Audio, idioma y ajustes de pantalla",
        "fr": "Audio, langue et réglages d'écran",
        "de": "Audio-, Sprach- und Anzeigeeinstellungen",
    },
    "tip_quit": {
        "it": "Esci dal gioco",
        "en": "Quit the game",
        "es": "Salir del juego",
        "fr": "Quitter le jeu",
        "de": "Spiel beenden",
    },
    "tip_back": {
        "it": "Torna alla schermata precedente",
        "en": "Go back to the previous screen",
        "es": "Volver a la pantalla anterior",
        "fr": "Revenir à l'écran précédent",
        "de": "Zurück zum vorherigen Bildschirm",
    },
    "tip_resume": {
        "it": "Riprendi la partita in corso",
        "en": "Resume the current game",
        "es": "Reanudar la partida actual",
        "fr": "Reprendre la partie en cours",
        "de": "Aktuelles Spiel fortsetzen",
    },
    "tip_quit_to_main": {
        "it": "Torna al menu principale",
        "en": "Return to the main menu",
        "es": "Volver al menú principal",
        "fr": "Retour au menu principal",
        "de": "Zurück zum Hauptmenü",
    },
    "tip_language": {
        "it": "Cambia la lingua del gioco",
        "en": "Change the game language",
        "es": "Cambia el idioma del juego",
        "fr": "Change la langue du jeu",
        "de": "Spielsprache ändern",
    },
    "tip_resolution": {
        "it": "Cambia la risoluzione dello schermo",
        "en": "Change the screen resolution",
        "es": "Cambia la resolución de pantalla",
        "fr": "Change la résolution de l'écran",
        "de": "Bildschirmauflösung ändern",
    },
    "tip_fullscreen": {
        "it": "Attiva o disattiva lo schermo intero",
        "en": "Toggle fullscreen mode",
        "es": "Activa o desactiva la pantalla completa",
        "fr": "Active ou désactive le plein écran",
        "de": "Vollbildmodus umschalten",
    },
}


def main():
    for lang in ("it", "en", "es", "fr", "de"):
        p = STR / f"{lang}.json"
        text = p.read_bytes().decode("utf-8")  # byte-safe: preserva i line ending
        data = json.loads(text)
        to_add = {k: v[lang] for k, v in TIPS.items() if k not in data}
        if not to_add:
            print(f"{lang}: niente da aggiungere")
            continue
        nl = "\r\n" if "\r\n" in text else "\n"
        trailing = text[len(text.rstrip()):]  # newline finale originale
        idx = text.rstrip().rfind("}")
        head = text[:idx].rstrip()
        if not head.endswith(","):
            head += ","
        lines = [
            "  " + json.dumps(k, ensure_ascii=True) + ": " + json.dumps(val, ensure_ascii=True)
            for k, val in to_add.items()
        ]
        new = head + nl + (("," + nl).join(lines)) + nl + "}" + (trailing or nl)
        chk = json.loads(new)
        assert all(k in chk for k in to_add)
        p.write_bytes(new.encode("utf-8"))
        print(f"{lang}: +{len(to_add)} chiavi tooltip ({'CRLF' if nl == chr(13)+chr(10) else 'LF'})")
    print("Fatto.")


if __name__ == "__main__":
    main()
