## Cosa cambia

<!-- Una frase. Cosa fa questa PR. -->

## Perche'

<!-- Il problema che risolve. Se e' un fix, come si riproduceva il bug. -->

## Checklist

- [ ] `pytest` passa in locale
- [ ] Type hints presenti sulle firme nuove o modificate
- [ ] Nessun `print()`, nessun magic number, nessuna emoji
- [ ] Path risorse via `get_resource_path` / `get_writable_path`
- [ ] Scritture JSON via `safe_write_json`
- [ ] Nessuna dipendenza nuova (o discussa prima in una issue)

### Se tocca engine/ (regola vincolante)

- [ ] Non tocca i moduli replicati nel runtime web
- [ ] Oppure: `docs/web/WEB_EXPORT_SYNC.md` aggiornato, runtime JS propagato e
      `pytest tests/test_web_sync.py` verde

### Se tocca scene o cataloghi

- [ ] `python tools/audit_catalog.py` eseguito
- [ ] Stringhe nuove passate dal sistema i18n

## Screenshot

<!-- Obbligatorio se cambia qualcosa a schermo. -->
