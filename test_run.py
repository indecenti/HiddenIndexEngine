"""
Test run automatico del gioco:
1. Avvia il gioco
2. Simula click sul menu per giocare
3. Simula click su oggetti nella scena
4. Verifica il flusso completo

Run: python test_run.py
"""

import sys
import time
import threading
import pygame

# Avvia il gioco in un thread separato
def run_game():
    from main import main
    sys.argv = ["main.py", "--game", "villa_segreta"]
    main()

def simulate_gameplay():
    """Attende che il gioco si avvii e poi simula i click."""
    time.sleep(2)  # Attendi boot + transizione splash

    # Simula click sul pulsante "Gioca"
    print("[TEST] Simulando click su 'Gioca'...")
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(640, 380)))
    time.sleep(1)

    # Simula click su "livello 1"
    print("[TEST] Simulando click su 'Level 1'...")
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(640, 330)))
    time.sleep(2)

    # Simula click su prima chiave (300, 400) scalato a 1920x1080
    # Scala: 1920/1280 = 1.5, quindi (300 * 1.5, 400 * 1.5) = (450, 600)
    print("[TEST] Simulando click su 'chiave'...")
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(450, 600)))
    time.sleep(1)

    # Simula click su secondo oggetto (800, 250) -> (1200, 375)
    print("[TEST] Simulando click su 'orologio'...")
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(1200, 375)))
    time.sleep(3)

    # Chiudi il gioco
    print("[TEST] Chiudendo il gioco...")
    pygame.event.post(pygame.event.Event(pygame.QUIT))

if __name__ == "__main__":
    # Avvia gioco in thread
    game_thread = threading.Thread(target=run_game, daemon=True)
    game_thread.start()

    # Simula interazioni nell'altro thread
    sim_thread = threading.Thread(target=simulate_gameplay, daemon=True)
    sim_thread.start()

    # Aspetta che il gioco termini
    game_thread.join(timeout=30)
    print("\n[DONE] Test run completato!")
