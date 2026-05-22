"""Ripristina le chiavi di traduzione presenti nei .bak ma assenti nel working
tree (perse per un git checkout). Aggiunge SOLO le chiavi mancanti: i valori
attuali e l'ordine esistente restano intatti. Byte-safe (preserva CRLF/escape)."""
import json
from pathlib import Path

STR = Path(__file__).resolve().parent.parent / "engine" / "assets" / "strings"


def main():
    for lang in ("it", "en", "es", "fr", "de"):
        p = STR / f"{lang}.json"
        bak = STR / f"{lang}.json.bak"
        if not bak.exists():
            print(f"{lang}: nessun .bak, salto")
            continue
        text = p.read_bytes().decode("utf-8")
        cur = json.loads(text)
        bdata = json.loads(bak.read_bytes().decode("utf-8"))
        missing = {k: v for k, v in bdata.items() if k not in cur}
        if not missing:
            print(f"{lang}: niente da ripristinare")
            continue
        nl = "\r\n" if "\r\n" in text else "\n"
        trailing = text[len(text.rstrip()):]
        idx = text.rstrip().rfind("}")
        head = text[:idx].rstrip()
        if not head.endswith(","):
            head += ","
        lines = ["  " + json.dumps(k, ensure_ascii=True) + ": " + json.dumps(v, ensure_ascii=True)
                 for k, v in missing.items()]
        new = head + nl + (("," + nl).join(lines)) + nl + "}" + (trailing or nl)
        # validazione
        chk = json.loads(new)
        assert all(k in chk for k in missing)
        assert all(k in chk for k in cur)  # nessuna chiave attuale persa
        p.write_bytes(new.encode("utf-8"))
        print(f"{lang}: +{len(missing)} chiavi ripristinate (tot {len(chk)})")
    print("Fatto.")


if __name__ == "__main__":
    main()
