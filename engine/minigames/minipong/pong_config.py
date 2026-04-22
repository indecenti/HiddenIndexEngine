"""
engine/minigames/minipong/pong_config.py

Costanti per il minigioco Pong in stile Arcade 1972.
Documentazione: Riferimento a 1280x720 (HiddenIndexEngine Standard).
"""

# Colori (Bianco e Nero Puro — No Grigi, No Gradienti)
COLOR_BG = (0, 0, 0)
COLOR_MAIN = (255, 255, 255)

# Dimensioni di Riferimento
REF_W = 1280
REF_H = 720

# Elementi (Manteniamo proporzioni blocky)
PADDLE_W = 16
PADDLE_H = 120
BALL_SIZE = 20 # Leggermente più grande per visibilità classica
MARGIN_SIDE = 60

# Meccaniche di Movimento
INITIAL_BALL_SPEED = 600.0  
SPEED_INCREMENT = 50.0      # Incremento più marcato
MAX_BALL_SPEED = 1800.0
AI_SPEED_BASE = 700.0       # Più veloce e competitiva

# "Hardware Glitch" Originale: Il paddle non arriva alla sommità (richiesto 30px)
PADDLE_TOP_LIMIT = 30.0
PADDLE_BOTTOM_LIMIT = 0.0

# Punteggio
WIN_LIMIT = 11

# Linea Centrale
DASH_W = 12
DASH_H = 30
DASH_GAP = 25

# Suoni (Generati in formato Square Wave per fedeltà 1972)
SND_HIT = "engine/minigames/minipong/assets/sounds/paddle.wav"
SND_WALL = "engine/minigames/minipong/assets/sounds/wall.wav"
SND_SCORE = "engine/minigames/minipong/assets/sounds/score.wav"
SFX_VOLUME = 0.3

