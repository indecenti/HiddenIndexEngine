"""
engine/minigames/asteroids/asteroids_config.py

Costanti per il minigioco Asteroids in stile Arcade 1979 (Vettoriale).
"""

# Colori (Stile Vettore Originale)
COLOR_BG = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_THRUST = (200, 200, 255) # Leggermente azzurrato per il motore

# Dimensioni di Riferimento
REF_W = 1280
REF_H = 720

# Nave (Ship)
SHIP_RADIUS = 15
SHIP_THRUST = 600.0
SHIP_ROT_SPEED = 280.0
SHIP_DRAG = 0.99  # Attrito minimo spaziale
SHIP_MAX_SPEED = 500.0
SHIP_RESPAWN_TIME = 2.0
SHIP_INVULNERABLE_TIME = 3.0

# Asteroidi
ASTER_LARGE_RADIUS = 50.0
ASTER_MEDIUM_RADIUS = 25.0
ASTER_SMALL_RADIUS = 12.0

ASTER_LARGE_SPEED = (80, 150)
ASTER_MEDIUM_SPEED = (150, 220)
ASTER_SMALL_SPEED = (220, 320)

ASTER_LARGE_POINTS = 20
ASTER_MEDIUM_POINTS = 50
ASTER_SMALL_POINTS = 100

# Proiettili (Bullets)
BULLET_SPEED = 800.0
BULLET_LIFETIME = 1.0  # Secondi prima di sparire
BULLET_MAX = 4        # Limite arcade originale

# UFO
UFO_BIG_POINTS = 200
UFO_SMALL_POINTS = 1000
UFO_SPAWN_CHANCE = 0.05 # Per secondo, dopo un certo tempo
UFO_MIN_INTERVAL = 15.0

# Suoni (Placeholder o Percorsi)
SND_FIRE = "fire.wav"
SND_THRUST = "thrust.wav"
SND_BANG_LARGE = "bang_large.wav"
SND_BANG_MEDIUM = "bang_medium.wav"
SND_BANG_SMALL = "bang_small.wav"
SND_BEAT1 = "beat1.wav"
SND_BEAT2 = "beat2.wav"
SND_EXTRA_SHIP = "extra_ship.wav"

# Lives
INITIAL_LIVES = 3
EXTRA_LIFE_SCORE = 10000
