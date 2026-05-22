"""Corregge le violazioni di schema nei cataloghi (warning all'avvio editor):
  - cartoon: id/label_key con 'A' maiuscola (assi) -> minuscolo
  - real: label_key senza prefisso obj_ -> obj_<id>; default_width/default_radius mancanti
Edit programmatico a diff minimo (i cataloghi fanno round-trip identico con indent=2)."""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "engine" / "data"


def _load(p):
    raw = p.read_bytes()
    crlf = b"\r\n" in raw
    return json.loads(raw.decode("utf-8")), crlf


def _save(p, data, crlf):
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if crlf:
        out = out.replace("\n", "\r\n")
    # preserva eventuale newline finale
    p.write_bytes((out + ("\r\n" if crlf else "\n")).encode("utf-8"))


def fix_cartoon():
    p = DATA / "global_cartoon_catalog.json"
    data, crlf = _load(p)
    n = 0
    for o in data["objects"]:
        oid = o.get("id", "")
        if oid in ("ca_card_diamonds_A", "ca_card_hearts_A"):
            o["id"] = oid.lower()
            if o.get("label_key"):
                o["label_key"] = o["label_key"][:-1] + "a"  # _A -> _a
            n += 1
    _save(p, data, crlf)
    print(f"cartoon: corretti {n} assi (id/label minuscolo)")


def fix_real():
    p = DATA / "global_real_catalog.json"
    data, crlf = _load(p)
    label_fix = {"cassette_tape", "cellphone_retro", "floppy_disk", "gameboy",
                 "pager", "retro_tv", "tamagotchi", "vhs_tape", "walkman"}
    n_lbl = n_rad = n_wid = 0
    for o in data["objects"]:
        oid = o.get("id", "")
        # label_key -> obj_<id>
        if oid in label_fix and o.get("label_key") == oid:
            o["label_key"] = "obj_" + oid
            n_lbl += 1
        # default_radius mancante per detection circle
        if o.get("default_detection") == "circle" and o.get("default_radius") is None:
            o["default_radius"] = 35
            n_rad += 1
        # default_width mancante per detection rect
        if o.get("default_detection") == "rect" and o.get("default_width") is None:
            h = o.get("default_height") or 100
            o["default_width"] = max(40, int(h * 0.62))  # proporzione ragionevole
            n_wid += 1
    _save(p, data, crlf)
    print(f"real: label_key corretti {n_lbl}, default_radius aggiunti {n_rad}, default_width aggiunti {n_wid}")


if __name__ == "__main__":
    fix_cartoon()
    fix_real()
    print("Fatto.")
