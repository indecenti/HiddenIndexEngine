# Risoluzione Anomalie Rendering (Display Scaling on Windows)

## Il Problema ("Bordi neri a destra e in basso")
Durante il cambio di risoluzione (ad es. da 1280x720 a 1920x1080) in modalità Finestra su sistemi Windows, l'esecuzione di `pygame.display.set_mode` aggiornava le logiche di rendering interne della _Surface_, ma falliva sistematicamente nel far recepire all'OS il ridimensionamento dei margini fisici della finestra.
Di riflesso, la nuova e più ampia resolution veniva compressa od omessa nella vecchia finestra statica con l'inevitabile e anti-estetica formazione letterbox parziale (i "bordi neri") perché la Canvas tagliava fuori asse il raster.

Questo avviene per tre casistiche tecniche concorrenti:
1. Impiego forzato di `os.environ['SDL_VIDEO_CENTERED'] = '1'`.
2. Assenza dell'istruzione `pygame.SCALED` o della feature `pygame.RESIZABLE` tra i `flags` di set_mode (entrambe inibite per precise ragioni architetturali del framework `HiddenIndexEngine`).
3. Intercettazione errata del context DPI (Dots per Inch) da parte del backend hardware su OS Windows.

## Soluzione Architetturale
Per ovviare al problema senza intaccare le performance né appoggiarsi a refactoring distruttivi: si dismette bruscamente e si re-inizializza il contesto video immediatamente prima di settare il nuovo display.
Poiché a partire da Pygame 2 le risorse caricate nella Virtual Memory nativa (come font o pre-calcoli via `.convert_alpha()`) persistono anche staccando l'aggancio alla GPU, questa pratica si rivela rapida, fluida e assolutamente solida contro crash applicativi.

```python
# Procedura in engine/core.py -> _apply_display_settings(self, w, h, fullscreen)

# 1. Spegnimento brutale, sgancio viewport dall'OS Windows
pygame.display.quit()

# 2. Riattivazione driver SDL per il display
pygame.display.init()

# 3. Ri-assegnazione dell'hook di centratura (essenziale ri-registrarlo post-init)
os.environ['SDL_VIDEO_CENTERED'] = '1'
pygame.display.set_caption("Hidden Engine")

# 4. Atomico set_mode finale
self.screen = pygame.display.set_mode((w, h), flags, vsync=1)
```

## Benefici Tecnici
* La finestra viene costretta da Windows a un ridisegno topologico garantito (`WM_SIZE` e `WM_NCCALCSIZE` invocate con certezza su win32).
* Totalmente compatibile e agnostico per eventuali futuri update in `ScalingManager` o conversioni full-screen.
* Previene ghosting memory leaks che solitamente SDL porta su cambi sfalsati di display.
