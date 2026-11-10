# Malonno Survivors - story

Hidden object game, night painted style, present day in an alpine village of Valle
Camonica that the fog has emptied. Three chapters, fourteen scenes. The story is told by
story cards (intro and outro of every scene), one clue object per scene and a journal.
Engine features: `docs/engine/STORY_AND_REPLAY.md`. Texts: `strings/<lang>.json`, keys
listed below; Italian is the source language.

## Premise

For twelve days the player's grandmother, Teresa, has not answered the phone. The news
says the state road to Malonno is closed by a landslide; nobody has seen the landslide.
The player drives up the Brescia-Edolo road at night. At the fork the fog is so thick the
engine dies, and the car radio crackles: someone in the village is still talking.

The voice is Nives, the town hall switchboard operator. She guides the player by radio
through the empty village. Everything was left as it was on the night of 2 November, All
Souls' night: the slicer stopped on the ham, the pizzas cold on the tables, the trains
still on the platform. People are not dead: the fog took them and they are asleep
somewhere inside it.

The cause is in Villa Rosa. In 1966 the fog of All Souls took Lucia Rosa, seven years old.
Her brother Ottavio, now an old engineer, read in the village papers that the old Camunni
carved the Rosa Camuna on a stone to hold the fog still, and that if the stone is broken
the fog gives back what it took. His family had walled the stone up in the cellar. On 2
November he invited half of the village to the villa, broke the stone with a chisel and
waited for Lucia. The fog came down and took everyone. An antique dealer from Milan, who
had come for the stone, carried off a piece; the firemen and the mechanic who tried to stop
him carried off others; the train never left.

The player collects the five pieces and carries them to the mountain cemetery, where the
stone stood in the ossuary before the Rosa family walled it up. Whole again, the Rose holds
the fog: it withdraws at dawn and the village wakes, grandmother Teresa included. Ottavio
wakes last on the bench and leaves Lucia's locket by the stone.

Twist, last page: nobody finds Nives. In the town hall the valve radio has been dead for
years, its wires cut and grey with dust. In the registry, under B: "Bonomi Nives,
switchboard operator. Lost in the All Souls' fog, 2 November 1966."

Secret epilogue (journal, all 14 roses found): on the cemetery bench there is a fifteenth
rose, freshly carved, small, the way a child would carve it, with two initials: L. and N.

## Chapters, scenes, clues

| Ch. | Scene | Clue object | What the player learns |
|---|---|---|---|
| 1 La Nebbia | Brescia_Edolo - the fork on the state road | walkie_talkies | someone in the village is on channel 9 |
| | Welcome - the village entrance and the bar | torn_newspaper | it all happened on All Souls' night |
| | Formis - the grocery | faded_letter | grandmother's list: the pizzas for the villa |
| | Pizza_King - the pizzeria | receipt_roll | fourteen pizzas to Villa Rosa, and a warning about the stone |
| | Municipio_Abbandonato - the registry office | sepia_portrait_photo | Lucia Rosa, lost in the fog in 1966 |
| 2 Villa Rosa | Albergo_Lobby - the hotel lobby | carved_stone_fragment_a | first piece of the Rosa Camuna, at the dealer's |
| | Infermeria_Alpina - the infirmary | spiral_notebook | the people in the fog are asleep, not dead |
| | Villa_Rosa - the villa | ancient_key | Ottavio's key: "Cellar. Forgive me, Lucia." |
| | Sotterranei_Villa_Rosa - the cellar | chisel | the empty niche, five pieces carried off |
| 3 L'Alba | Caserma_Pompieri - the fire station | carved_stone_fragment_b | the second piece, in a fireman's jacket |
| | Officina_Abbandonata - the workshop | carved_stone_fragment_c | the third piece, labelled for Milano Centrale |
| | Stazione_Abbandonata - the station | carved_stone_fragment_a | the fourth piece, in the dealer's suitcase |
| | Chiesa_Abbandonata - the church | carved_stone_fragment_b | the heart of the Rose, by a child's shoe |
| | Cimitero_Montagna - the cemetery | silver_locket | Ottavio, asleep on the bench; the ending |

Collectible: a small stone with a carved Camunian rose (`rose_carved_pebble`), hidden in
every scene on one of several spots. Name: `collectible_name`. Epilogue:
`epilogue_title`, `epilogue_text` (journal).

## String keys

- `game_title`, level names `<level_id>_name`, chapter headings `ch1_title`..`ch3_title`
- scene names `<scene_id>_name`
- story cards `<scene_id>_intro_<n>`, `<scene_id>_outro_<n>`
- clues `clue_<scene_id>`
- `collectible_name`, `epilogue_title`, `epilogue_text`

## Replay

Every scene: a pool of about 30 objects placed by the camouflage auto-scatter, 12 of them
drawn as goals on each run (the clue is always one of them), and two or three alternative
hiding spots per object, so both the list and the places change from run to run. The
rose moves too. Finding all fourteen roses unlocks the epilogue.
