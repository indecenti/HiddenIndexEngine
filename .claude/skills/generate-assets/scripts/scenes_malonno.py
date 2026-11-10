"""16:9 backgrounds for the eight Malonno_Survivors scenes that only had a 1024x1024 draft.

Rows: (level_id, scene_id, description, names en/it/de/es/fr). Rendered with
generate_background.py --dark --hq (the night painted look of the other Malonno scenes).
Each description keeps the place of the old draft and stages it for hidden objects: a
focal point, three depth layers, free surfaces at different heights, one or two warm
lights against cold moonlight, a few shadowed nooks. Story: games/Malonno_Survivors/STORY.md.
"""

SCENES = [
    ("Welcome_To_Malonno", "Albergo_Lobby",
     "the lobby of an old abandoned mountain hotel, a long carved wooden reception desk in "
     "the centre with an old rotary telephone and an open guest register, a wall of "
     "wooden key pigeonholes behind it, a big stone fireplace on the left with a cold "
     "hearth and a mantelpiece, a small round table and two worn armchairs, a brass "
     "chandelier with one candle lit, a half open door showing the dark staircase, "
     "cracked stone floor with a faded rug, cold blue moonlight from the doorway",
     ["Hotel Lobby", "Hall dell'Albergo", "Hotelhalle", "Vestíbulo del Hotel",
      "Hall de l'Hôtel"]),
    ("Welcome_To_Malonno", "Caserma_Pompieri",
     "inside an old alpine volunteer fire station garage at night, a heavy wooden "
     "workbench in the centre, a tool wall with a few hanging tools and free hooks, "
     "metal shelving with gaps, a row of dented steel lockers on the right, coiled canvas "
     "hoses and a bucket on the concrete floor, tall wooden garage doors with small "
     "windows letting in moonlight, a red rotating emergency lamp glowing on the wall",
     ["Fire Station", "Caserma dei Pompieri", "Feuerwache", "Cuartel de Bomberos",
      "Caserne des Pompiers"]),
    ("Welcome_To_Malonno", "Chiesa_Abbandonata",
     "the nave of an abandoned small mountain church, rows of old wooden pews in the "
     "foreground, a pointed stained glass window letting in pale moonbeams through dust, "
     "a stone side altar with a lace cloth and a few lit candles, a wooden confessional, "
     "a font of holy water, fallen plaster and leaves on the flagstone floor, frescoes "
     "faded to shadows on the vault",
     ["Abandoned Church", "Chiesa Abbandonata", "Verlassene Kirche", "Iglesia Abandonada",
      "Église Abandonnée"]),
    ("Welcome_To_Malonno", "Cimitero_Montagna",
     "a small mountain cemetery at night, a low dry stone wall and an open wrought iron "
     "gate in the foreground, old leaning gravestones and iron crosses in the grass, a "
     "stone ossuary chapel with three arches at the back, two bare twisted trees, an oil "
     "lantern glowing on the wall, a bench by the path, dark peaks under a stormy moonlit "
     "sky with low clouds",
     ["Mountain Cemetery", "Cimitero di Montagna", "Bergfriedhof", "Cementerio de Montaña",
      "Cimetière de Montagne"]),
    ("Welcome_To_Malonno", "Infermeria_Alpina",
     "an abandoned alpine infirmary ward, two old white iron hospital beds with crumpled "
     "sheets, a glass fronted wooden medicine cabinet with half empty shelves, an enamel "
     "basin on a stand, a small bedside table with a candle, a window onto the misty "
     "mountains, peeling teal painted walls, a flickering fluorescent tube, chequered "
     "tile floor",
     ["Alpine Infirmary", "Infermeria Alpina", "Alpine Krankenstation", "Enfermería Alpina",
      "Infirmerie Alpine"]),
    ("Welcome_To_Malonno", "Municipio_Abbandonato",
     "the registry office of an abandoned village town hall, a big wooden desk in the "
     "centre with an old valve radio set and a green desk lamp glowing, tall archive "
     "shelves with folders and gaps, a wooden filing cabinet, a bench for the public "
     "along the wall, a tall window onto a cobbled square in the fog, parquet floor, "
     "one faded flag in the corner",
     ["Town Hall", "Municipio", "Rathaus", "Ayuntamiento", "Mairie"]),
    ("Welcome_To_Malonno", "Officina_Abbandonata",
     "an abandoned village mechanic's workshop, a long workbench with a vice and free "
     "space, metal shelves with a few cans and boxes, a stack of old tyres, a hydraulic "
     "car lift in the middle, a hanging enamel lamp glowing warm, oil stains on the "
     "concrete floor, tall dusty windows with moonlight, a rolling tool cart",
     ["Old Workshop", "Officina Abbandonata", "Verlassene Werkstatt", "Taller Abandonado",
      "Atelier Abandonné"]),
    ("Welcome_To_Malonno", "Stazione_Abbandonata",
     "the platform of an abandoned small valley railway station at night seen close up at "
     "eye level: a wooden waiting bench, a luggage trolley with old suitcases, the ticket "
     "window of the stone station building with a wide counter ledge, crates and milk churns "
     "on the platform, a wall lamp glowing warm, the dark side of an old steam locomotive at "
     "the platform edge, weeds between the paving stones",
     ["Old Station", "Stazione Abbandonata", "Verlassener Bahnhof", "Estación Abandonada",
      "Gare Abandonnée"]),
]
