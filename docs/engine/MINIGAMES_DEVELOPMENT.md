# Guida allo Sviluppo di Minigiochi (HiddenIndexEngine)

Questa guida descrive lo standard professionale per creare, integrare e localizzare nuovi minigiochi nell'engine. Seguendo questi passaggi, ogni minigioco erediterà automaticamente le funzionalità di pausa, scaling e la coerenza visiva del sistema principale.

## 1. Struttura del File System
Ogni minigioco deve risiedere in una sottocartella dedicata dentro `engine/minigames/`.

```text
engine/minigames/<minigame_id>/
├── strings/            # File JSON per le 5 lingue (it, en, fr, es, de)
├── manifest.json       # Configurazione per il caricamento dinamico
└── <minigame_id>_game.py  # Classe principale del gioco
```

## 2. Il Manifest (`manifest.json`)
Il manifest permette al `MinigameManager` di individuare la classe corretta senza doverla importare manualmente nel codice dell'engine.
```json
{
  "id": "nome_gioco",
  "name": "Titolo Visualizzato",
  "main_class": "MyNewGame",
  "version": "1.0.0"
}
```

## 3. Localizzazione (Mandatoria)
Ogni minigioco **DEVE** supportare le 5 lingue ufficiali per evitare warning o testi vuoti.
- Percorso: `engine/minigames/<id>/strings/*.json`
- Caricamento: Deve avvenire nel costruttore `__init__`.

> [!IMPORTANT]
> Per garantire la corretta visualizzazione nel **Selettore Minigiochi dell'Editor**, ogni file `.json` della lingua deve contenere obbligatoriamente queste due chiavi:
> - `mg_title`: Il nome del minigioco localizzato (es: "SFIDA PONG").
> - `mg_description`: Una breve descrizione (max 2 righe) delle meccaniche di gioco.
>
> Queste chiavi vengono utilizzate dall'editor per popolare l'interfaccia di selezione e permettere all'utente di capire cosa sta associando all'oggetto.

```python
from engine.utils import get_resource_path

def __init__(self, **kwargs):
    super().__init__(**kwargs)
    # Carica le traduzioni locali (it, en, fr, es, de)
    strings_path = get_resource_path("engine", "minigames", "my_id", "strings")
    self.load_local_strings(strings_path)
```

## 4. Logica di Gioco (Ereditarietà)
La classe deve ereditare da `BaseMinigame` implementando i metodi standard di Pygame.

```python
from engine.minigames.minigame_base import BaseMinigame

class MyNewGame(BaseMinigame):
    def start(self) -> None:
        """Invocato una sola volta all'attivazione del gioco."""
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        """Gestione input. NOTA: ESC attiva automaticamente la pausa globale tramite il MinigameManager."""
        pass

    def update(self, dt: float) -> None:
        """Logica dei frame (movimento, collisioni)."""
        pass

    def draw(self) -> None:
        """Rendering grafico dello stato attuale."""
        self.screen.fill((20, 20, 20))
```

## 5. Gestione Risultati e Punteggio
Per chiudere il minigioco e tornare alla scena principale, invoca `self.finish(results)`.
- `success`: Se `True`, viene considerato un obiettivo completato.
- `score`: Punti bonus sommati al punteggio della run principale.

```python
results = {
    "success": True, 
    "score": 1000      # Bonus per la vittoria
}
self.finish(results)
```

## 6. Sincronizzazione con l'Engine
Il minigioco deve essere pronto a recepire cambiamenti di stato globali:
- **Pausa**: Il pulsante in alto a sinistra è gestito dall'engine. Non disegnarlo.
- **Resize**: Implementa `on_resize(self)` se vuoi ricalcolare il layout quando l'utente cambia risoluzione durante la pausa.
- **Scaling**: Usa `self.scaling_manager.scale` per mantenere le proporzioni (font, velocità, dimensioni).

## 7. Registrazione
Nessuna registrazione manuale richiesta. Una volta presente la cartella con il manifest, il minigioco può essere richiamato da qualsiasi oggetto della scena tramite l'editor semplicemente inserendo il suo `id`.
