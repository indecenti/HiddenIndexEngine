"""
engine/minigames/centipede/centipede_config.py
"""

# Dimensioni Riferimento Area di Gioco (Centrata)
GAME_W = 600
GAME_H = 720
GRID_SIZE = 20
COLS = GAME_W // GRID_SIZE # 30
ROWS = GAME_H // GRID_SIZE # 36

# Colori Arcade (Palette originali)
COLOR_BG = (10, 5, 20)
COLOR_MUSHROOM = (200, 50, 200)
COLOR_MUSHROOM_POISON = (50, 200, 50)
COLOR_CENTI_HEAD = (255, 255, 255)
COLOR_CENTI_BODY = (255, 0, 255)
COLOR_PLAYER = (0, 255, 255)
COLOR_SPIDER = (255, 128, 0)
COLOR_FLEA = (200, 200, 200)
COLOR_SCORPION = (255, 50, 50)
COLOR_BULLET = (255, 255, 100)

# Game Balance
INITIAL_LIVES = 3
EXTRA_LIFE_SCORE = 12000

# Speeds (grid units per second)
PLAYER_SPEED = 300.0
BULLET_SPEED = 800.0
CENTIPEDE_SPEED_BASE = 180.0
CENTIPEDE_SPEED_INC = 10.0 # Per ogni livello o segmento perso? No, fissa.

SPIDER_SPEED = 150.0
FLEA_SPEED = 350.0
SCORPION_SPEED = 200.0

# Timings
SPIDER_SPAWN_TIME = (5.0, 10.0)
FLEA_SPAWN_TIME = (10.0, 20.0)
SCORPION_SPAWN_TIME = (15.0, 25.0)

# Points
PT_MUSHROOM = 1
PT_MUSHROOM_REGEN = 5
PT_CENTI_BODY = 10
PT_CENTI_HEAD = 100
PT_SPIDER_CLOSE = 900
PT_SPIDER_MID = 600
PT_SPIDER_FAR = 300
PT_FLEA = 200
PT_SCORPION = 1000

# SFX Names
SND_FIRE = "centi_fire.wav"
SND_KILL_CENTI = "centi_kill.wav"
SND_KILL_SPIDER = "spider_kill.wav"
SND_DEATH = "death.wav"
SND_BEAT = "beat.wav"
SND_MUSH_HIT = "mush_hit.wav"
