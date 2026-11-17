"""Oggetti nuovi per la libreria comune (real, globali), pensati per gli scaffali di Lince.

Mancavano soprattutto ceramica, ottone, cuoio, carta, legno, stoffa e vetro in oggetti "da ripiano":
in piedi, di misura media o piccola, con un lato diverso dall'altro (manico, beccuccio, cerniera)
perche' la differenza "specchio" si veda. Niente verde (la griglia e' su verde), niente marchi.

Righe: id, descrizione, rettangolo, tag (dalla tassonomia), nomi en/it/de/es/fr.
CM: lato piu' lungo reale in centimetri.
"""

C = [
    # ---- ceramica
    ("ceramic_pitcher_floral", "old white ceramic water pitcher with a spout, a curved handle and a hand painted blue floral band", (45, 55), ["ceramica", "casa", "cucina", "antico", "medio"], ["Ceramic Pitcher", "Brocca di Ceramica", "Keramikkrug", "Jarra de Cerámica", "Broc en Céramique"]),
    ("gravy_boat_porcelain", "white porcelain sauce boat with a pouring spout, a curved handle and a thin gold rim", (50, 30), ["ceramica", "cucina", "antico", "medio"], ["Sauce Boat", "Salsiera", "Sauciere", "Salsera", "Saucière"]),
    ("chamberstick_ceramic", "white ceramic chamber candlestick with a round dish and a finger ring handle, burnt down candle", (40, 30), ["ceramica", "luce", "antico", "piccolo"], ["Chamber Candlestick", "Candeliere a Bugia", "Handleuchter", "Palmatoria", "Bougeoir à Main"]),
    ("beer_stein_ceramic", "grey stoneware beer stein with a hinged pewter lid, a thumb lever, a curved handle and a blue pattern", (40, 45), ["ceramica", "bevanda", "tradizione", "medio"], ["Beer Stein", "Boccale da Birra", "Bierkrug", "Jarra de Cerveza", "Chope en Grès"]),
    ("stoneware_jug_brown", "brown glazed stoneware jug with a narrow neck and a single loop handle, chipped", (35, 50), ["ceramica", "casa", "tradizione", "medio"], ["Stoneware Jug", "Brocca di Gres", "Steinzeugkrug", "Jarra de Gres", "Cruche en Grès"]),
    ("toast_rack_ceramic", "white porcelain toast rack with a loop handle on top and slots for slices", (40, 30), ["ceramica", "cucina", "vintage", "piccolo"], ["Toast Rack", "Portatoast", "Toastständer", "Tostadero", "Porte-toasts"]),
    ("teapot_blue_ceramic", "round blue and white ceramic teapot with a long curved spout, a handle on the other side and a small lid knob", (50, 40), ["ceramica", "cucina", "bevanda", "antico", "medio"], ["Blue Teapot", "Teiera Blu", "Blaue Teekanne", "Tetera Azul", "Théière Bleue"]),
    ("oil_cruet_ceramic", "small cream ceramic oil cruet with a pouring spout, a cork stopper and a side handle", (30, 40), ["ceramica", "cucina", "contenitore", "piccolo"], ["Oil Cruet", "Oliera", "Ölkännchen", "Aceitera", "Huilier"]),
    ("milk_pitcher_stripe", "small ceramic milk pitcher with a spout and a handle, white with blue horizontal stripes", (30, 40), ["ceramica", "cucina", "casa", "piccolo"], ["Striped Milk Pitcher", "Lattiera a Righe", "Gestreifte Milchkanne", "Lechera a Rayas", "Pot à Lait Rayé"]),
    ("tankard_pottery_glazed", "rustic glazed pottery tankard with a thick handle, brown and cream drip glaze", (35, 40), ["ceramica", "bevanda", "tradizione", "medio"], ["Pottery Tankard", "Boccale in Terracotta", "Tonkrug", "Jarra de Barro", "Pichet en Terre"]),

    # ---- ottone
    ("brass_candlestick_tall", "tall polished brass candlestick with a round dish, a ring handle and a half burnt candle", (30, 60), ["ottone", "luce", "antico", "medio"], ["Brass Candlestick", "Candeliere d'Ottone", "Messingleuchter", "Candelabro de Latón", "Chandelier en Laiton"]),
    ("brass_hand_bell", "old brass hand bell with a turned wooden handle and a clapper", (30, 50), ["ottone", "antico", "collezione", "medio"], ["Brass Hand Bell", "Campanella d'Ottone", "Messingglocke", "Campana de Latón", "Cloche en Laiton"]),
    ("brass_kettle_old", "old brass kettle with a curved spout, a swing handle and a hinged lid, slightly tarnished", (50, 45), ["ottone", "cucina", "antico", "medio"], ["Brass Kettle", "Bollitore d'Ottone", "Messingkessel", "Hervidor de Latón", "Bouilloire en Laiton"]),
    ("brass_door_knocker_hand", "heavy brass door knocker in the shape of a hand holding a ball, on a round back plate", (30, 40), ["ottone", "antico", "decorazione", "piccolo"], ["Hand Door Knocker", "Battente a Mano", "Türklopfer Hand", "Aldaba de Mano", "Heurtoir en Main"]),
    ("brass_bugle_horn", "polished brass bugle with a wide bell and a curled tube, tasselled cord", (50, 40), ["ottone", "musica", "antico", "medio"], ["Brass Bugle", "Tromba d'Ottone", "Messinghorn", "Corneta de Latón", "Clairon en Laiton"]),
    ("brass_watering_can_small", "small brass watering can with a long spout, a rose head and an arched handle", (45, 40), ["ottone", "giardino", "vintage", "medio"], ["Brass Watering Can", "Annaffiatoio d'Ottone", "Messinggießkanne", "Regadera de Latón", "Arrosoir en Laiton"]),
    ("brass_inkwell_pen", "brass desk inkwell with a hinged lid and a feather quill resting in a side holder", (35, 40), ["ottone", "studio", "antico", "piccolo"], ["Brass Inkwell", "Calamaio d'Ottone", "Messingtintenfass", "Tintero de Latón", "Encrier en Laiton"]),
    ("brass_stirrup_cup", "brass trophy cup with two uneven curved handles and a short stem", (35, 45), ["ottone", "prezioso", "collezione", "medio"], ["Brass Cup", "Coppa d'Ottone", "Messingpokal", "Copa de Latón", "Coupe en Laiton"]),

    # ---- cuoio
    ("leather_satchel_school", "old brown leather school satchel with two buckled straps and a shoulder strap, scuffed", (45, 40), ["cuoio", "vintage", "viaggio", "medio"], ["Leather Satchel", "Cartella di Cuoio", "Lederranzen", "Cartera de Cuero", "Cartable en Cuir"]),
    ("leather_suitcase_small", "small old brown leather suitcase with two brass latches, a carrying handle and a worn corner", (50, 40), ["cuoio", "viaggio", "vintage", "medio"], ["Small Suitcase", "Valigetta di Cuoio", "Lederkoffer", "Maleta de Cuero", "Valise en Cuir"]),
    ("leather_riding_boot", "single tall brown leather riding boot with a worn heel and a buckled strap", (35, 65), ["cuoio", "calzatura", "vintage", "medio"], ["Riding Boot", "Stivale da Cavallo", "Reitstiefel", "Bota de Montar", "Botte d'Équitation"]),
    ("fireplace_bellows", "old wooden fireplace bellows with brown leather sides, a brass nozzle and two wooden handles", (50, 45), ["cuoio", "legno", "casa", "antico", "medio"], ["Bellows", "Soffietto", "Blasebalg", "Fuelle", "Soufflet"]),
    ("leather_hip_flask", "curved leather covered hip flask with a stitched seam and a screw cap on a short chain", (25, 40), ["cuoio", "bevanda", "viaggio", "piccolo"], ["Hip Flask", "Borraccia di Cuoio", "Flachmann", "Petaca de Cuero", "Gourde en Cuir"]),
    ("leather_camera_case", "brown leather camera case with a front flap, a metal clasp and a thin shoulder strap", (35, 35), ["cuoio", "viaggio", "vintage", "medio"], ["Camera Case", "Custodia per Macchina Fotografica", "Kameratasche", "Funda de Cámara", "Étui d'Appareil Photo"]),
    ("aviator_cap_leather", "old brown leather aviator cap with ear flaps, a chin strap and a pair of round goggles on the front", (40, 35), ["cuoio", "cappello", "vintage", "medio"], ["Aviator Cap", "Cuffia da Aviatore", "Fliegerkappe", "Gorro de Aviador", "Casque d'Aviateur"]),
    ("leather_doctor_bag", "classic black leather doctor bag with a brass clasp and two arched handles, worn", (50, 40), ["cuoio", "medico", "vintage", "medio"], ["Doctor Bag", "Borsa del Medico", "Arzttasche", "Maletín de Médico", "Sacoche de Médecin"]),

    # ---- legno
    ("wooden_spinning_top", "painted wooden spinning top with a pointed tip and a pull string, red and cream stripes", (25, 35), ["legno", "giocattolo", "vintage", "piccolo"], ["Spinning Top", "Trottola", "Kreisel", "Peonza", "Toupie"]),
    ("wooden_abacus", "old wooden abacus frame with coloured beads on rods, a slightly crooked frame", (40, 35), ["legno", "giocattolo", "studio", "vintage", "medio"], ["Abacus", "Abaco", "Abakus", "Ábaco", "Abaque"]),
    ("wooden_recorder_flute", "wooden recorder flute with finger holes and a brown mouthpiece, standing upright", (15, 55), ["legno", "musica", "piccolo"], ["Recorder", "Flauto Dolce", "Blockflöte", "Flauta Dulce", "Flûte à Bec"]),
    ("wooden_mallet_old", "old wooden mallet with a thick head and a long worn handle", (35, 50), ["legno", "attrezzo", "officina", "medio"], ["Wooden Mallet", "Maglio di Legno", "Holzhammer", "Mazo de Madera", "Maillet en Bois"]),
    ("hand_plane_wood", "old wooden hand plane with an iron blade and a wedge, worn sole", (50, 30), ["legno", "metallo", "attrezzo", "officina", "medio"], ["Hand Plane", "Pialla", "Handhobel", "Cepillo", "Rabot"]),
    ("wooden_toy_crane", "painted wooden toy crane with a swivel arm, a hook on a string and a yellow and red body", (40, 55), ["legno", "giocattolo", "vintage", "medio"], ["Toy Crane", "Gru Giocattolo", "Spielzeugkran", "Grúa de Juguete", "Grue Jouet"]),
    ("wooden_pencil_box", "old wooden pencil case with a sliding lid half open and coloured pencils inside", (40, 25), ["legno", "studio", "vintage", "piccolo"], ["Pencil Box", "Astuccio di Legno", "Griffelkasten", "Plumier de Madera", "Plumier en Bois"]),
    ("wooden_toolbox_small", "small old wooden toolbox with a rope handle on one side, a few tools sticking out", (50, 35), ["legno", "attrezzo", "officina", "medio"], ["Wooden Toolbox", "Cassetta degli Attrezzi", "Holzwerkzeugkasten", "Caja de Herramientas", "Boîte à Outils en Bois"]),
    ("wooden_ship_model", "small wooden sailing ship model with three masts, white sails and a wooden stand", (50, 50), ["legno", "giocattolo", "collezione", "medio"], ["Ship Model", "Modellino di Veliero", "Segelschiffmodell", "Maqueta de Barco", "Maquette de Voilier"]),
    ("wooden_bowl_ladle", "round wooden bowl with a carved wooden ladle leaning on its rim", (45, 35), ["legno", "cucina", "tradizione", "medio"], ["Bowl and Ladle", "Ciotola con Mestolo", "Holzschüssel", "Cuenco con Cucharón", "Bol et Louche"]),

    # ---- carta
    ("rolled_diploma_ribbon", "rolled paper diploma tied with a red ribbon and a small wax seal", (50, 20), ["carta", "studio", "antico", "medio"], ["Diploma Scroll", "Pergamena con Nastro", "Urkunde", "Diploma Enrollado", "Diplôme Roulé"]),
    ("old_ledger_book", "tall old account ledger with a worn red cloth spine, leather corners and a ribbon bookmark hanging out", (40, 55), ["carta", "libro", "studio", "antico", "medio"], ["Old Ledger", "Registro Contabile", "Hauptbuch", "Libro de Cuentas", "Grand Livre"]),
    ("letters_bundle_string", "bundle of old yellowed letters and envelopes tied with a string, uneven edges", (40, 30), ["carta", "studio", "antico", "piccolo"], ["Bundle of Letters", "Mazzo di Lettere", "Briefbündel", "Fajo de Cartas", "Liasse de Lettres"]),
    ("paper_folding_fan", "half open Japanese paper folding fan with a painted red sun and bamboo ribs", (45, 30), ["carta", "decorazione", "asia", "medio"], ["Paper Fan", "Ventaglio di Carta", "Papierfächer", "Abanico de Papel", "Éventail en Papier"]),
    ("accordion_file_folder", "brown cardboard accordion file folder with a string tie and a paper label, bulging", (40, 40), ["carta", "ufficio", "vintage", "medio"], ["Accordion File", "Cartella a Soffietto", "Fächermappe", "Archivador Acordeón", "Classeur Accordéon"]),
    ("pop_up_book_open", "open children pop up book standing on its spine with a paper castle rising from the pages", (45, 40), ["carta", "libro", "giocattolo", "medio"], ["Pop-up Book", "Libro Pop-up", "Pop-up-Buch", "Libro Desplegable", "Livre Pop-up"]),

    # ---- stoffa
    ("rag_doll_cloth", "old cloth rag doll with red wool hair, a patched dress and uneven button eyes, sitting", (40, 50), ["stoffa", "giocattolo", "vintage", "medio"], ["Rag Doll", "Bambola di Pezza", "Stoffpuppe", "Muñeca de Trapo", "Poupée de Chiffon"]),
    ("knitted_wool_hat_bobble", "knitted wool winter hat with a big bobble on top and a folded brim, red and cream pattern", (35, 40), ["stoffa", "cappello", "abbigliamento", "medio"], ["Knitted Hat", "Cappello di Lana", "Strickmütze", "Gorro de Lana", "Bonnet en Laine"]),
    ("sewing_basket_cloth", "round wicker sewing basket with a half open lid, spools, scissors and a tape measure hanging over the edge", (45, 40), ["stoffa", "casa", "vintage", "medio"], ["Sewing Basket", "Cestino da Cucito", "Nähkorb", "Costurero", "Panier à Couture"]),
    ("patchwork_pillow", "square patchwork cushion with mismatched fabric squares, one corner dog-eared", (40, 40), ["stoffa", "arredamento", "casa", "medio"], ["Patchwork Cushion", "Cuscino Patchwork", "Patchworkkissen", "Cojín Patchwork", "Coussin Patchwork"]),
    ("sailor_hat_cloth", "white cloth sailor hat with a blue ribbon band and two long ribbons hanging on one side", (35, 30), ["stoffa", "cappello", "abbigliamento", "piccolo"], ["Sailor Hat", "Cappello da Marinaio", "Matrosenmütze", "Gorro de Marinero", "Bonnet de Marin"]),
    ("hanging_cloth_apron", "folded striped cotton apron with a pocket and a long tie string trailing on one side", (40, 45), ["stoffa", "cucina", "casa", "medio"], ["Cotton Apron", "Grembiule", "Schürze", "Delantal", "Tablier"]),

    # ---- vetro
    ("glass_perfume_atomizer", "glass perfume atomizer with a rubber squeeze bulb and a silk tassel, amber liquid", (30, 40), ["vetro", "bellezza", "antico", "piccolo"], ["Perfume Atomizer", "Vaporizzatore", "Parfümzerstäuber", "Atomizador", "Vaporisateur"]),
    ("glass_kerosene_lamp", "old glass kerosene lamp with a brass collar, a tall glass chimney and a side wick knob", (30, 55), ["vetro", "luce", "antico", "medio"], ["Kerosene Lamp", "Lampada a Petrolio", "Petroleumlampe", "Lámpara de Queroseno", "Lampe à Pétrole"]),
    ("glass_dropper_bottle", "brown glass apothecary bottle with a glass dropper pipette and a rubber teat, paper label with no text", (25, 45), ["vetro", "medicina", "contenitore", "antico", "piccolo"], ["Dropper Bottle", "Flacone Contagocce", "Tropfflasche", "Frasco Cuentagotas", "Flacon Compte-gouttes"]),
    ("glass_paperweight_dome", "round glass paperweight dome with a coloured flower inside on a flat base", (25, 25), ["vetro", "studio", "collezione", "piccolo"], ["Paperweight", "Fermacarte di Vetro", "Briefbeschwerer", "Pisapapeles", "Presse-papier"]),
    ("glass_carafe_handle", "clear glass water carafe with a curved handle, a pouring lip and a small glass cup upside down on top", (35, 50), ["vetro", "casa", "bevanda", "medio"], ["Glass Carafe", "Caraffa di Vetro", "Glaskaraffe", "Garrafa de Vidrio", "Carafe en Verre"]),
    ("glass_candy_jar_scoop", "glass candy jar with a lid and a metal scoop hanging on the side, filled with striped boiled sweets", (30, 45), ["vetro", "dolce", "contenitore", "medio"], ["Candy Jar", "Barattolo di Caramelle", "Bonbonglas", "Tarro de Caramelos", "Bocal à Bonbons"]),
]

# lato piu' lungo reale in cm (misure della libreria: servono a Lince per le proporzioni fra oggetti)
CM = {
    "ceramic_pitcher_floral": 24, "gravy_boat_porcelain": 20, "chamberstick_ceramic": 14, "beer_stein_ceramic": 20,
    "stoneware_jug_brown": 25, "toast_rack_ceramic": 14, "teapot_blue_ceramic": 20, "oil_cruet_ceramic": 14,
    "milk_pitcher_stripe": 14, "tankard_pottery_glazed": 15,
    "brass_candlestick_tall": 30, "brass_hand_bell": 22, "brass_kettle_old": 28, "brass_door_knocker_hand": 17,
    "brass_bugle_horn": 30, "brass_watering_can_small": 28, "brass_inkwell_pen": 22, "brass_stirrup_cup": 18,
    "leather_satchel_school": 36, "leather_suitcase_small": 45, "leather_riding_boot": 45, "fireplace_bellows": 48,
    "leather_hip_flask": 15, "leather_camera_case": 15, "aviator_cap_leather": 28, "leather_doctor_bag": 38,
    "wooden_spinning_top": 12, "wooden_abacus": 30, "wooden_recorder_flute": 32, "wooden_mallet_old": 32,
    "hand_plane_wood": 26, "wooden_toy_crane": 32, "wooden_pencil_box": 22, "wooden_toolbox_small": 38,
    "wooden_ship_model": 40, "wooden_bowl_ladle": 30,
    "rolled_diploma_ribbon": 35, "old_ledger_book": 36, "letters_bundle_string": 18, "paper_folding_fan": 30,
    "accordion_file_folder": 32, "pop_up_book_open": 28,
    "rag_doll_cloth": 36, "knitted_wool_hat_bobble": 26, "sewing_basket_cloth": 30, "patchwork_pillow": 40,
    "sailor_hat_cloth": 24, "hanging_cloth_apron": 38,
    "glass_perfume_atomizer": 15, "glass_kerosene_lamp": 40, "glass_dropper_bottle": 12, "glass_paperweight_dome": 8,
    "glass_carafe_handle": 25, "glass_candy_jar_scoop": 25,
}
