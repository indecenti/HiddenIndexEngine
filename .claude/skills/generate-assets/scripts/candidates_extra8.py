"""Eight generic objects: four new ones for any railway/period scene, and four
redone because the first render missed (Malonno batch). Rows as candidates_100.
Generic by rule: no character, place, date or readable text in id, names or prompt.
"""

C = [
    ("opened_telegram", "old opened telegram envelope with a folded paper slip, no readable text", (40, 30), ["carta", "ufficio", "antico", "piccolo"], ["Opened Telegram", "Telegramma Aperto", "Geöffnetes Telegramm", "Telegrama Abierto", "Télégramme Ouvert"]),
    ("logbook_torn_pages", "old open leather logbook with several pages torn out, ragged edges, blank lines", (55, 40), ["cuoio", "carta", "libro", "ufficio", "antico", "medio"], ["Torn Logbook", "Registro Strappato", "Zerrissenes Logbuch", "Registro Arrancado", "Registre Déchiré"]),
    ("fireman_shovel", "old short steel locomotive fireman coal shovel with a wooden D handle, sooty", (30, 70), ["ferro", "legno", "attrezzo", "viaggio", "antico", "medio"], ["Fireman's Shovel", "Pala del Fuochista", "Heizerschaufel", "Pala de Fogonero", "Pelle de Chauffeur"]),
    ("brass_station_bell", "old brass station departure bell mounted on a small iron wall bracket", (35, 45), ["ottone", "ferro", "viaggio", "antico", "medio"], ["Station Bell", "Campana di Stazione", "Bahnhofsglocke", "Campana de Estación", "Cloche de Gare"]),
    ("alpine_hat", "italian alpine troops grey felt hat with a single long black raven feather on the left side, brim turned down, no badge", (55, 40), ["abbigliamento", "cappello", "militare", "medio"], ["Alpine Hat", "Cappello Alpino", "Alpinihut", "Sombrero Alpino", "Chapeau Alpin"]),
    ("brass_bed_warmer", "antique brass bed warming pan: a round lidded brass pan attached to a very long straight wooden handle, whole handle visible, lying diagonally", (40, 80), ["ottone", "legno", "arredamento", "antico", "grande"], ["Bed Warmer", "Scaldaletto", "Bettwärmer", "Calentador de Cama", "Bassinoire"]),
    ("napoletane_cards", "fanned deck of old italian regional playing cards with suit symbols of cups, coins, swords and wooden clubs, worn, no french suits", (50, 40), ["carta", "gioco", "vintage", "medio"], ["Old Playing Cards", "Carte da Gioco Antiche", "Alte Spielkarten", "Naipes Antiguos", "Vieilles Cartes à Jouer"]),
    ("mandolin", "old italian neapolitan mandolin with a deep rounded bowl back made of wooden ribs, eight strings, short neck, seen from the front at an angle", (40, 85), ["legno", "musica", "antico", "grande"], ["Mandolin", "Mandolino", "Mandoline", "Mandolina", "Mandoline"]),
]
