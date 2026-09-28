# Il Segreto della Casa sul Lago (The Secret of the Lake House)

Hidden object game, real style, present day in old places. Four levels of four scenes.
Backgrounds: `.claude/skills/generate-assets/scripts/scenes_casa_lago.py`, rendered with
`generate_background.py --hog --hq` (photographic, same rendering as the real object
library, so both vintage and modern objects fit).

## Story

Chiara, a furniture restorer from the city, inherits the villa of her great-aunt
Margherita on a quiet mountain lake. Margherita, a collector and traveller, vanished a
year ago; the villagers say she rowed to the island one night and never came back.

In the villa Chiara finds a note: "Every room keeps one piece. Put them together
before the lighthouse lights up again." Margherita had hidden, room by room and shop
by shop, the pieces of an old brass mechanism - the key that opens the lighthouse
lens room, where she kept the proof that the villa and the island belong to the
village and not to the developer who wants to buy them.

Chiara searches the villa, then the village where Margherita left the pieces with
old friends, then the lake shore, and finally the island. In the lantern room she
lights the lighthouse: Margherita, who had been hiding in the keeper's room to stay
safe, sees the signal and comes home.

## Levels and scenes

| Level | Scene | What the player finds / learns |
|---|---|---|
| 1 L'Arrivo | villa_entrance_hall - entrance hall at dusk | the note, the first brass gear |
| | villa_kitchen - old kitchen with the lake view | a recipe book with a coded page |
| | villa_study - study with fireplace | Margherita's travel diary |
| | villa_attic - attic under the beams | a map of the lake with marks |
| 2 Il Paese | antique_shop - the antique dealer friend | the second gear, kept "for Chiara" |
| | village_cafe - café on the square | the barman remembers the last night |
| | old_pharmacy - old pharmacy | a vial label with the lighthouse code |
| | bookshop_backroom - bookshop back room | the deed of the island in an old book |
| 3 Il Lago | boathouse - boathouse | Margherita's boat, the oar with a key |
| | lake_pier - pier at sunset | the island's signal lamp |
| | fisherman_hut - fisherman's hut | the fisherman's logbook of her trips |
| | greenhouse - villa greenhouse | the last gear, buried in a pot |
| 4 L'Isola | lighthouse_room - keeper's room | traces of someone living there |
| | island_chapel - chapel | the mechanism's case |
| | grotto_cave - hidden grotto | the lens room key |
| | lantern_room - lantern room | the lighthouse is lit: the ending |

Objects: generic pieces from the global real catalog (vintage, kitchen, study, tools,
nautical, garden), placed per scene in the editor. Level names and scene names are in
`strings/<lang>.json` (5 languages).
