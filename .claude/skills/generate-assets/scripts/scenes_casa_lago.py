"""Scene backgrounds of the game Casa_sul_Lago (story: games/Casa_sul_Lago/STORY.md).

Rows: (level_id, scene_id, description, names en/it/de/es/fr). Rendered with
generate_background.py --hog --hq (photographic, same rendering as the real object
library). Each description is written for a hidden object stage: a focal point, three
depth layers, several free surfaces at different heights, one or two warm practical
lights, a few shadowed nooks, period character carried by furniture and materials.
Present day, but in old places, so both vintage and modern library objects fit.
"""

LEVELS = [
    ("L_Arrivo", ["The Arrival", "L'Arrivo", "Die Ankunft", "La Llegada", "L'Arrivée"]),
    ("Il_Paese", ["The Village", "Il Paese", "Das Dorf", "El Pueblo", "Le Village"]),
    ("Il_Lago", ["The Lake", "Il Lago", "Der See", "El Lago", "Le Lac"]),
    ("L_Isola", ["The Island", "L'Isola", "Die Insel", "La Isla", "L'Île"]),
]

SCENES = [
    # Level 1 - the villa
    ("L_Arrivo", "villa_entrance_hall",
     "the entrance hall of an old lakeside villa at dusk, a wide stone staircase with a "
     "carved wooden banister, a round marble side table in the centre, a long console "
     "table under a tall gilded mirror, an umbrella stand and a wooden bench by the "
     "door, patterned terracotta floor tiles, a brass chandelier and a wall lamp glowing "
     "warm, tall door with coloured glass panes",
     ["Entrance Hall", "Ingresso della Villa", "Eingangshalle", "Vestíbulo", "Hall d'Entrée"]),
    ("L_Arrivo", "villa_kitchen",
     "the big old kitchen of a lakeside villa, a long scrubbed wooden table in the "
     "foreground, a cream enamel cooking range, open wooden shelves with a few jars and "
     "free space, a stone sink under a window with a view of the lake, copper pans "
     "hanging on a rail, a dresser with plates, hexagonal tile floor, warm morning sun",
     ["Villa Kitchen", "Cucina della Villa", "Villenküche", "Cocina de la Villa",
      "Cuisine de la Villa"]),
    ("L_Arrivo", "villa_study",
     "a grandmother's study in an old villa, a large walnut writing desk with a green "
     "desk lamp, a leather armchair by a stone fireplace with a mantelpiece, tall "
     "bookcases with gaps on the shelves, a globe on a stand, a small round table by the "
     "window, a worn oriental rug on parquet, warm lamplight and fire glow",
     ["The Study", "Lo Studio", "Das Arbeitszimmer", "El Estudio", "Le Bureau"]),
    ("L_Arrivo", "villa_attic",
     "the attic of an old villa under sloping wooden beams, a round window letting in "
     "a shaft of light, a few old trunks and a dressmaker's dummy, a long wooden table "
     "with free space, open shelves with some boxes, a rocking chair, a hanging bare "
     "bulb, dusty plank floor, soft warm light and deep corners",
     ["The Attic", "La Soffitta", "Der Dachboden", "El Desván", "Le Grenier"]),
    # Level 2 - the village
    ("Il_Paese", "antique_shop",
     "inside a small village antique shop, a glass display counter with a brass cash "
     "register in the foreground, tall wooden shelves with some old objects and free "
     "space, a grandfather clock, a velvet armchair, a round table with a lace cloth, "
     "old lamps glowing warm, a shop window onto a cobbled street",
     ["Antique Shop", "Negozio di Antiquariato", "Antiquitätenladen", "Tienda de "
      "Antigüedades", "Boutique d'Antiquités"]),
    ("Il_Paese", "village_cafe",
     "an old village café with a long zinc bar counter and a polished espresso machine, "
     "a few marble topped bistro tables with bentwood chairs, wooden shelves behind the "
     "bar with free space, a large mirror, pendant lamps glowing warm, big windows onto "
     "the lake square, checkered floor",
     ["Village Café", "Caffè del Paese", "Dorfcafé", "Café del Pueblo", "Café du Village"]),
    ("Il_Paese", "old_pharmacy",
     "an old village pharmacy, a long carved wooden counter with a brass scale, tall "
     "walnut cabinets with small drawers and glass doors, shelves with a few apothecary "
     "jars and free space, a ladder on a rail, green glass lamps, a tiled floor, soft "
     "daylight from a window",
     ["Old Pharmacy", "Antica Farmacia", "Alte Apotheke", "Farmacia Antigua",
      "Vieille Pharmacie"]),
    ("Il_Paese", "bookshop_backroom",
     "the back room of a village bookshop, a large wooden work table with free space in "
     "the foreground, bookcases up to the ceiling with gaps, a reading armchair with a "
     "floor lamp, a small iron spiral staircase, stacks of crates, a desk with a lamp "
     "under an arched window, warm cosy light",
     ["Bookshop Back Room", "Retro della Libreria", "Hinterzimmer der Buchhandlung",
      "Trastienda de la Librería", "Arrière-boutique de la Librairie"]),
    # Level 3 - the lake
    ("Il_Lago", "boathouse",
     "inside an old wooden boathouse on a lake, a varnished wooden rowing boat in the "
     "water in the centre, a plank walkway around it, a workbench with free space in the "
     "foreground, oars and ropes on the wall, wooden shelves, a lantern glowing warm, "
     "light reflections dancing on the water and the beams, open doors onto the lake",
     ["Boathouse", "Rimessa delle Barche", "Bootshaus", "Cobertizo de Barcas",
      "Hangar à Bateaux"]),
    ("Il_Lago", "lake_pier",
     "an old wooden pier on a calm mountain lake at golden sunset, a small wooden hut "
     "at the end, a bench, a few barrels and crates, a lamp post with a warm light, a "
     "moored rowing boat, mountains and the distant island with a lighthouse, clear "
     "water reflections",
     ["Lake Pier", "Pontile sul Lago", "Seesteg", "Muelle del Lago", "Ponton du Lac"]),
    ("Il_Lago", "fisherman_hut",
     "inside a fisherman's hut by the lake, a rough wooden table with free space in the "
     "foreground, nets and floats hanging on the walls, a small iron stove, wooden "
     "shelves with some free space, a bunk with a wool blanket, an oil lamp glowing "
     "warm, a small window onto the water",
     ["Fisherman's Hut", "Capanno del Pescatore", "Fischerhütte", "Cabaña del Pescador",
      "Cabane du Pêcheur"]),
    ("Il_Lago", "greenhouse",
     "an old Victorian style glass greenhouse in the villa garden, long wooden potting "
     "benches with free space, terracotta pots and a few plants, an iron spiral "
     "decoration, a watering can on the brick floor, a wicker chair and a small table, "
     "soft sunlight through the glass panes and hanging vines",
     ["Greenhouse", "Serra", "Gewächshaus", "Invernadero", "Serre"]),
    # Level 4 - the island
    ("L_Isola", "lighthouse_room",
     "the round keeper's room inside an old island lighthouse, curved stone walls, a "
     "wooden desk under a small window with free space, a narrow iron staircase going "
     "up, a small bed, shelves along the curve with gaps, a brass barometer, an oil "
     "lamp glowing warm, stormy blue light outside",
     ["Lighthouse Room", "Stanza del Faro", "Leuchtturmzimmer", "Cuarto del Faro",
      "Chambre du Phare"]),
    ("L_Isola", "island_chapel",
     "a small abandoned stone chapel on the island, a simple wooden altar table with "
     "free space, a few wooden pews, candles in iron holders glowing, niches in the "
     "walls, a round rose window casting coloured light, ivy coming through a crack, "
     "worn stone floor",
     ["Island Chapel", "Cappella dell'Isola", "Inselkapelle", "Capilla de la Isla",
      "Chapelle de l'Île"]),
    ("L_Isola", "grotto_cave",
     "a hidden cave under the island lit by lanterns, a flat rock ledge and an old "
     "wooden table with free space in the foreground, a few wooden crates, a small "
     "underground pool with turquoise water reflecting light on the rock, a narrow "
     "passage in the back with a warm glow",
     ["Hidden Grotto", "Grotta Nascosta", "Versteckte Grotte", "Gruta Oculta",
      "Grotte Cachée"]),
    ("L_Isola", "lantern_room",
     "the top lantern room of the lighthouse at night, a big brass and glass lighthouse "
     "lens in the centre glowing warm, a circular iron gallery, a small wooden table and "
     "a stool with free surfaces, a wooden chest, panoramic windows onto the moonlit "
     "lake and the villa lights far away",
     ["Lantern Room", "Lanterna del Faro", "Laternenraum", "Linterna del Faro",
      "Salle de la Lanterne"]),
]
