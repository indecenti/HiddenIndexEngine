"""Scene backgrounds of the game Ultimo_Treno (story: games/Ultimo_Treno/STORY.md).

Rows: (level_id, scene_id, description, names en/it/de/es/fr). The description is
the "{what}" of generate_background.STYLE: keep it about the place, its few large
elements and its free surfaces - the style already asks for calm and uncluttered.
"""

LEVELS = [
    ("La_Partenza", ["The Departure", "La Partenza", "Die Abreise", "La Partida", "Le Départ"]),
    ("Il_Viaggio", ["The Journey", "Il Viaggio", "Die Reise", "El Viaje", "Le Voyage"]),
    ("Valdoria", ["Valdoria", "Valdoria", "Valdoria", "Valdoria", "Valdoria"]),
    ("Il_Segreto", ["The Secret", "Il Segreto", "Das Geheimnis", "El Secreto", "Le Secret"]),
]

SCENES = [
    ("La_Partenza", "station_hall", "the grand hall of Milan central railway station at night in 1928, marble floor, a long empty wooden bench, a closed newsstand counter, tall arched windows, one large clock", ["Station Hall", "Atrio della Stazione", "Bahnhofshalle", "Vestíbulo de la Estación", "Hall de la Gare"]),
    ("La_Partenza", "ticket_office", "inside a 1920s railway ticket office seen from behind the counter, a long wooden counter with a clear top, pigeonhole shelves partly empty, a desk lamp, a small safe, a window grille", ["Ticket Office", "Biglietteria", "Fahrkartenschalter", "Taquilla", "Guichet"]),
    ("La_Partenza", "luggage_room", "a 1920s railway left luggage room, wooden shelves with a few old suitcases and free space, a wooden counter, a hand cart, a single hanging lamp", ["Left Luggage", "Deposito Bagagli", "Gepäckaufbewahrung", "Consigna", "Consigne"]),
    ("La_Partenza", "night_platform", "a quiet railway platform at night in 1928 with one black steam locomotive waiting and soft steam, an empty bench, a lamp post, a luggage trolley, clean platform floor", ["Night Platform", "Binario di Notte", "Nächtlicher Bahnsteig", "Andén Nocturno", "Quai de Nuit"]),
    ("Il_Viaggio", "first_class_compartment", "interior of a 1920s first class train compartment, red velvet seats facing each other, a small folding table by the window, empty luggage racks, wood panelling, mountains outside at dawn", ["First Class", "Prima Classe", "Erste Klasse", "Primera Clase", "Première Classe"]),
    ("Il_Viaggio", "dining_car", "a 1920s railway dining car interior, a few tables with white tablecloths mostly bare, brass lamps, polished wood walls, windows with alpine valley", ["Dining Car", "Vagone Ristorante", "Speisewagen", "Coche Restaurante", "Wagon-restaurant"]),
    ("Il_Viaggio", "sleeping_car", "a 1920s sleeping car compartment, a made bunk bed, a small washbasin cabinet, a folding shelf, a night lamp, a window with snowy forest at night", ["Sleeping Car", "Vagone Letto", "Schlafwagen", "Coche Cama", "Wagon-lit"]),
    ("Il_Viaggio", "locomotive_cab", "inside the cab of a 1920s steam locomotive, the firebox door glowing, brass gauges and levers, a coal tender behind, a narrow shelf, view of rails in the mountains", ["Locomotive Cab", "Cabina della Locomotiva", "Führerstand", "Cabina de la Locomotora", "Cabine de la Locomotive"]),
    ("Valdoria", "village_station", "a small abandoned alpine village railway station under the first snow, a wooden station building, an empty platform with a bench, a water tower, quiet mountains", ["Valdoria Station", "Stazione di Valdoria", "Bahnhof Valdoria", "Estación de Valdoria", "Gare de Valdoria"]),
    ("Valdoria", "waiting_room", "a cold empty waiting room of an alpine station in the 1920s, wooden benches, an iron stove, a timetable board, frosted windows, bare plank floor", ["Waiting Room", "Sala d'Attesa", "Wartesaal", "Sala de Espera", "Salle d'Attente"]),
    ("Valdoria", "stationmaster_office", "a 1920s stationmaster office, a large wooden desk with a clear top, a chair, a filing cabinet, a wall shelf with some free space, a window on the tracks", ["Stationmaster's Office", "Ufficio del Capostazione", "Büro des Bahnhofsvorstehers", "Oficina del Jefe de Estación", "Bureau du Chef de Gare"]),
    ("Valdoria", "telegraph_room", "a small 1920s railway telegraph room, a telegraph desk with a morse key, a wooden cabinet, a stool, a shelf with some free space, one window", ["Telegraph Room", "Sala del Telegrafo", "Telegrafenraum", "Sala del Telégrafo", "Salle du Télégraphe"]),
    ("Il_Segreto", "signal_box", "inside a 1920s railway signal box, a row of big signal levers, a desk by the large windows over the snowy tracks, a stove, a shelf", ["Signal Box", "Cabina di Segnalamento", "Stellwerk", "Cabina de Señales", "Poste d'Aiguillage"]),
    ("Il_Segreto", "engine_shed", "a large dim 1920s engine shed with one old steam locomotive inside, rails on the floor, a workbench with free space, tall dusty windows, light beams", ["Engine Shed", "Rimessa delle Locomotive", "Lokschuppen", "Cochera de Locomotoras", "Dépôt des Locomotives"]),
    ("Il_Segreto", "mine_tunnel", "an old mine tunnel with narrow rails and a small mine cart, wooden support beams, a few oil lamps, a wide rocky floor, a faint glow at the end", ["Mine Tunnel", "Galleria della Miniera", "Minenstollen", "Túnel de la Mina", "Galerie de la Mine"]),
    ("Il_Segreto", "hidden_workshop", "a hidden 1920s railway workshop in a stone cellar, a long workbench with free space, wall tool board with gaps, a desk with a lamp, a model train on a shelf", ["Hidden Workshop", "Laboratorio Nascosto", "Versteckte Werkstatt", "Taller Oculto", "Atelier Caché"]),
]
