"""Hidden object restyle of the Ultimo_Treno scenes (painted + hq pass).

Same level/scene ids and names as scenes_ultimo_treno; only the descriptions change.
Each description is written for a hidden object stage: a clear focal point, three
depth layers (foreground ledge, middle furniture, background wall or view), several
free surfaces at different heights where objects will be placed, a few nooks and
shadows that invite searching, one or two warm light sources, and period details
carried by the furniture and materials rather than by clutter, posters or text.
"""
from scenes_ultimo_treno import LEVELS  # noqa: F401  (re-exported for build_game)

_NAMES = {s[1]: s[3] for s in __import__("scenes_ultimo_treno").SCENES}

_ROWS = [
    ("La_Partenza", "station_hall",
     "the grand waiting hall of a 1920s city railway station at night, seen from a raised "
     "gallery step, polished marble floor with a large inlaid pattern, a long carved wooden "
     "bench in the foreground, a closed wooden newsstand kiosk with an empty counter, a "
     "brass luggage trolley, tall arched windows with iron tracery showing blue night, a "
     "big round station clock hanging in the centre, warm globe lamps on iron columns"),
    ("La_Partenza", "ticket_office",
     "inside a 1920s railway ticket office seen from behind the counter, a long polished "
     "wooden counter with a glass top in the foreground, a wall of wide wooden shelves "
     "with empty compartments, a brass desk lamp, a small iron safe on a low cabinet, a "
     "cast iron stove in the corner, a wooden swivel chair, one coat stand, a ticket "
     "window with a decorative iron grille, soft evening light from a tall window"),
    ("La_Partenza", "luggage_room",
     "a 1920s railway left luggage room, tall wooden racks with a few old leather "
     "suitcases and trunks and plenty of empty shelf space, a heavy wooden counter with "
     "a brass bell in the foreground, a wooden hand cart, a steamer trunk on the floor, "
     "a single green enamel pendant lamp casting warm light, a small high window, worn "
     "plank floor"),
    ("La_Partenza", "night_platform",
     "a quiet railway platform at night in the 1920s, a black steam locomotive waiting "
     "on the right with soft white steam, an iron and glass canopy overhead, a long "
     "wooden bench and a stack of wooden crates in the foreground, a luggage trolley, "
     "a cast iron lamp post with a warm glow, a small wooden kiosk with a closed "
     "shutter, wet cobbled platform edge reflecting the lights"),
    ("Il_Viaggio", "first_class_compartment",
     "interior of a 1920s first class train compartment, deep red velvet seats facing "
     "each other, a small folding mahogany table under the window, brass luggage racks "
     "above with free space, polished wood panelling with marquetry, small brass wall "
     "lamps, lace curtains tied back, a window showing alpine mountains at dawn"),
    ("Il_Viaggio", "dining_car",
     "a 1920s railway dining car interior seen along the aisle, a few tables with white "
     "tablecloths and empty surfaces, upholstered chairs, small brass table lamps with "
     "pleated shades, a wooden serving sideboard in the foreground, polished wood walls "
     "with brass fittings, an arched ceiling, windows showing a sunny alpine valley"),
    ("Il_Viaggio", "sleeping_car",
     "a 1920s sleeping car compartment at night, a made lower bunk with a folded "
     "blanket, an upper bunk with a ladder, a small wooden washbasin cabinet with a "
     "mirror, a folding shelf and a small table in the foreground, a brass night lamp "
     "with a warm glow, polished wood panels, a window showing a snowy forest in "
     "moonlight"),
    ("Il_Viaggio", "locomotive_cab",
     "inside the cab of a 1920s steam locomotive, the open firebox door glowing orange, "
     "brass pressure gauges, valves and levers on the backhead, a wooden seat, a narrow "
     "metal shelf and a toolbox in the foreground, a coal tender with a shovel behind, "
     "side window showing rails curving through mountains, warm firelight and cool "
     "daylight"),
    ("Valdoria", "village_station",
     "a small remote alpine village railway station under the first snow, a wooden "
     "station building with a covered porch, an empty platform with a bench and a few "
     "wooden barrels, a stone water tower, a hand pump, a cart with a tarp, pine trees "
     "and quiet snowy mountains, soft overcast light with a warm lit window"),
    ("Valdoria", "waiting_room",
     "a cold empty waiting room of an alpine railway station in the 1920s, long wooden "
     "benches along the walls, a round iron stove with a pipe in the centre, a blank "
     "timetable board, a wooden shelf and a small table in the foreground, frosted "
     "windows with snow outside, bare plank floor, one warm hanging lamp"),
    ("Valdoria", "stationmaster_office",
     "a 1920s stationmaster office, a large wooden desk with a clear top and a green "
     "desk lamp, a leather chair, a tall wooden filing cabinet, a wall shelf with some "
     "free space, a small stove, a coat rack, a window looking onto snowy tracks, "
     "warm lamplight against cool daylight"),
    ("Valdoria", "telegraph_room",
     "a small 1920s railway telegraph room, a wooden telegraph desk with a brass morse "
     "key and sounder, a tall wooden cabinet with small drawers, a stool, a wall shelf "
     "with free space, coils of wire, a single window with snow, a warm desk lamp in a "
     "dim room"),
    ("Il_Segreto", "signal_box",
     "inside a 1920s railway signal box, a long row of big red and blue signal levers "
     "across the floor, a wooden desk under the large windows over snowy tracks, a "
     "small iron stove, a wooden shelf and a bench in the foreground, a hanging oil "
     "lamp, dusk light"),
    ("Il_Segreto", "engine_shed",
     "a large dim 1920s engine shed with one old steam locomotive inside, rails set in "
     "the floor, a long workbench with free space and a vice in the foreground, oil "
     "drums, a chain hoist, tall dusty windows with shafts of light, a few hanging "
     "lamps with warm glow"),
    ("Il_Segreto", "mine_tunnel",
     "an old mine tunnel with narrow gauge rails and a small wooden mine cart, sturdy "
     "timber support beams, a few oil lamps hanging on hooks, a rough wooden crate and "
     "a plank shelf in the foreground, a wide rocky floor, a faint warm glow at the "
     "end of the tunnel"),
    ("Il_Segreto", "hidden_workshop",
     "a hidden 1920s railway workshop in a vaulted stone cellar, a long wooden "
     "workbench with free space in the foreground, a wall tool board with gaps, a "
     "drafting desk with a brass lamp, wooden shelves with a model steam train and "
     "empty space, a small forge glowing in the corner, warm light on stone walls"),
]

SCENES = [(lvl, sid, what, _NAMES[sid]) for lvl, sid, what in _ROWS]
