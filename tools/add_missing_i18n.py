"""Aggiunge chiavi i18n mancanti (editor prop_/menu_, tag_, obj_) ai 5 file
strings. Aggiunge SOLO le chiavi assenti in ciascuna lingua. Byte-safe."""
import json
from pathlib import Path

STR = Path(__file__).resolve().parent.parent / "engine" / "assets" / "strings"

# key -> {it, en, es, fr, de}
T = {
    # ── Editor: menu ──────────────────────────────────────────────────────
    "menu_new_game":   {"it": "Nuovo Gioco", "en": "New Game", "es": "Nuevo Juego", "fr": "Nouveau Jeu", "de": "Neues Spiel"},
    "menu_open_game":  {"it": "Apri Gioco", "en": "Open Game", "es": "Abrir Juego", "fr": "Ouvrir un Jeu", "de": "Spiel öffnen"},
    "menu_save_scene": {"it": "Salva Scena", "en": "Save Scene", "es": "Guardar Escena", "fr": "Enregistrer la Scène", "de": "Szene speichern"},
    "menu_auditor":    {"it": "Auditor", "en": "Auditor", "es": "Auditor", "fr": "Auditeur", "de": "Auditor"},
    # ── Editor: proprietà oggetto ─────────────────────────────────────────
    "prop_transform_hdr": {"it": "TRASFORMAZIONE", "en": "TRANSFORM", "es": "TRANSFORMACIÓN", "fr": "TRANSFORMATION", "de": "TRANSFORMATION"},
    "prop_visual_hdr":    {"it": "OPZIONI VISIVE", "en": "VISUAL", "es": "VISUAL", "fr": "VISUEL", "de": "VISUELL"},
    "prop_gameplay_hdr":  {"it": "GAMEPLAY", "en": "GAMEPLAY", "es": "GAMEPLAY", "fr": "GAMEPLAY", "de": "GAMEPLAY"},
    "prop_scale":       {"it": "Scala", "en": "Scale", "es": "Escala", "fr": "Échelle", "de": "Skalierung"},
    "prop_rotation":    {"it": "Rotazione", "en": "Rotation", "es": "Rotación", "fr": "Rotation", "de": "Drehung"},
    "prop_grayscale":   {"it": "Scala di grigi", "en": "Grayscale", "es": "Escala de grises", "fr": "Niveaux de gris", "de": "Graustufen"},
    "prop_tint_color":  {"it": "Tinta", "en": "Tint", "es": "Tinte", "fr": "Teinte", "de": "Tönung"},
    "prop_layer":       {"it": "Livello", "en": "Layer", "es": "Capa", "fr": "Calque", "de": "Ebene"},
    "prop_goal":        {"it": "Obiettivo", "en": "Goal", "es": "Objetivo", "fr": "Objectif", "de": "Ziel"},
    "prop_hint":        {"it": "Indizio", "en": "Hint", "es": "Pista", "fr": "Indice", "de": "Hinweis"},
    "prop_always":      {"it": "Sempre visibile", "en": "Always visible", "es": "Siempre visible", "fr": "Toujours visible", "de": "Immer sichtbar"},
    "prop_multi_selection": {"it": "Selezione multipla", "en": "Multi-selection", "es": "Selección múltiple", "fr": "Sélection multiple", "de": "Mehrfachauswahl"},
    "prop_warp":        {"it": "Warp", "en": "Warp", "es": "Warp", "fr": "Warp", "de": "Warp"},
    # ── Tag mancanti (it = label tassonomia) ──────────────────────────────
    "tag_strumento":       {"it": "Strumento", "en": "Tool", "es": "Herramienta", "fr": "Outil", "de": "Werkzeug"},
    "tag_contenitore":     {"it": "Contenitore", "en": "Container", "es": "Contenedor", "fr": "Conteneur", "de": "Behälter"},
    "tag_vestiario":       {"it": "Vestiario", "en": "Clothing", "es": "Vestuario", "fr": "Vêtements", "de": "Kleidung"},
    "tag_rifiuto":         {"it": "Rifiuto", "en": "Trash", "es": "Basura", "fr": "Déchet", "de": "Müll"},
    "tag_morbido":         {"it": "Morbido", "en": "Soft", "es": "Blando", "fr": "Doux", "de": "Weich"},
    "tag_cura":            {"it": "Cura", "en": "Care", "es": "Cuidado", "fr": "Soin", "de": "Pflege"},
    "tag_pianta":          {"it": "Pianta", "en": "Plant", "es": "Planta", "fr": "Plante", "de": "Pflanze"},
    "tag_riposo":          {"it": "Riposo", "en": "Rest", "es": "Descanso", "fr": "Repos", "de": "Ruhe"},
    "tag_cultura":         {"it": "Cultura", "en": "Culture", "es": "Cultura", "fr": "Culture", "de": "Kultur"},
    "tag_arredo":          {"it": "Arredo", "en": "Furniture", "es": "Mobiliario", "fr": "Mobilier", "de": "Einrichtung"},
    "tag_equipaggiamento": {"it": "Equipaggiamento", "en": "Equipment", "es": "Equipamiento", "fr": "Équipement", "de": "Ausrüstung"},
    "tag_attrezzatura":    {"it": "Attrezzatura", "en": "Gear", "es": "Equipo", "fr": "Matériel", "de": "Ausstattung"},
    "tag_elettronico":     {"it": "Elettronico", "en": "Electronic", "es": "Electrónico", "fr": "Électronique", "de": "Elektronisch"},
    "tag_caccia":          {"it": "Caccia", "en": "Hunting", "es": "Caza", "fr": "Chasse", "de": "Jagd"},
    "tag_zavorra":         {"it": "Zavorra", "en": "Ballast", "es": "Lastre", "fr": "Lest", "de": "Ballast"},
    "tag_igiene":          {"it": "Igiene", "en": "Hygiene", "es": "Higiene", "fr": "Hygiène", "de": "Hygiene"},
    "tag_informazione":    {"it": "Informazione", "en": "Information", "es": "Información", "fr": "Information", "de": "Information"},
    "tag_esterno":         {"it": "Esterno", "en": "Outdoor", "es": "Exterior", "fr": "Extérieur", "de": "Außen"},
    "tag_difesa":          {"it": "Difesa", "en": "Defense", "es": "Defensa", "fr": "Défense", "de": "Verteidigung"},
    "tag_ottone":          {"it": "Ottone", "en": "Brass", "es": "Latón", "fr": "Laiton", "de": "Messing"},
    "tag_peluche":         {"it": "Peluche", "en": "Plush", "es": "Peluche", "fr": "Peluche", "de": "Plüsch"},
    # ── Oggetto senza traduzione IT (fallback EN) ─────────────────────────
    "obj_ca_amulet_arcane": {"it": "Amuleto Arcano", "en": "Arcane Amulet", "es": "Amuleto Arcano", "fr": "Amulette Arcanique", "de": "Arkanes Amulett"},
}


def main():
    for lang in ("it", "en", "es", "fr", "de"):
        p = STR / f"{lang}.json"
        text = p.read_bytes().decode("utf-8")
        cur = json.loads(text)
        missing = {k: v[lang] for k, v in T.items() if k not in cur}
        if not missing:
            print(f"{lang}: niente da aggiungere")
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
        chk = json.loads(new)
        assert all(k in chk for k in missing) and all(k in chk for k in cur)
        p.write_bytes(new.encode("utf-8"))
        print(f"{lang}: +{len(missing)} chiavi (tot {len(chk)})")
    print("Fatto.")


if __name__ == "__main__":
    main()
