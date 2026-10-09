<!-- ANIMATIONS_README_VERSION 1 -->
# Animations for the 3D viewport (Interact tab)

Put raw **.fbx** animation files in this folder (sub-folders are fine). Animations made for a
**Mixamo** rig work directly: on mixamo.com pick an animation and download it as *FBX Binary*,
*Without Skin*, 30 fps. Other humanoid rigs work if their bones use Mixamo names (`Hips`, `Spine`,
`LeftArm`, `mixamorig:LeftForeArm`...). The animation is retargeted onto the VRoid model when
it is played. Press **Reload animations** in the Interact tab after adding files.

The **file name** decides when an animation plays. Names are not case-sensitive, and words
are separated by `_`. Add a number at the end for variations (`idle_happy_2.fbx`,
`emote_wave (3).fbx`); one variation is picked at random.

## Kinds

| Prefix | Plays | Example |
|---|---|---|
| `idle` | looping, while nothing else happens | `idle.fbx`, `idle_happy.fbx`, `idle_sleeping.fbx` |
| `pose` | looping; chosen in the Pose menu, or automatically like an idle when every word is a context word below | `pose_sitting.fbx`, `pose_beach.fbx` |
| `emote` | once, as a reaction in the chat, then back to the idle | `emote_wave.fbx`, `emote_laugh_shy.fbx` |

## Context words (for idles, poses and emotes)

After the prefix (and for emotes, after the event name) you can add any number of context
words. An animation is only used when **all** of its context words match the character's
current state. When several match, the one with the most matching words wins, so
`idle_beach_happy.fbx` beats `idle_happy.fbx` at the beach, and `idle.fbx` is the fallback.

### Activity
| Word | Activity |
|---|---|
| `lounging` | Lounging at home |
| `errands` | Casual / errands |
| `work` | Work / office |
| `studying` | School / studying |
| `formal` | Formal event |
| `date` | Date |
| `party` | Party / night out |
| `workout` | Workout / sports |
| `swimming` | Swimming / beach |
| `adventure` | Outdoors / adventure |
| `combat` | Combat / battle |
| `sleeping` | Sleeping |
| `crafting` | Manual work / crafting |
| `festival` | Ceremony / festival |

### Mood
| Word | Mood |
|---|---|
| `happy` | Happy |
| `calm` | Calm |
| `sad` | Sad |
| `energetic` | Energetic |
| `romantic` | Romantic |
| `confident` | Confident |
| `tired` | Cozy / tired |
| `grumpy` | Grumpy / dark |
| `mysterious` | Mysterious |
| `focused` | Focused |
| `adventurous` | Adventurous |
| `playful` | Playful |
| `fancy` | Fancy |

### Setting
| Word | Setting |
|---|---|
| `public` | Public |
| `home` | Private / at home |
| `beach` | Beach / pool |

### Weather
| Word | Weather |
|---|---|
| `hot` | Scorching hot |
| `warm` | Warm |
| `mild` | Mild |
| `cool` | Cool |
| `cold` | Cold |
| `snow` | Freezing / snowy |
| `rain` | Rainy |
| `windy` | Windy |

### Personality (the character's speaking style, from their profile)
`cheerful`, `shy`, `confident`, `edgy`, `elegant`, `flirty`, `mysterious`, `laidback`

## Emote events

`emote_<event>[_<context words>].fbx`

| Event | Played when |
|---|---|
| `wave` | Greeting |
| `goodbye` | Saying goodbye |
| `talk` | Any reply with no more specific emote (light talking gesture) |
| `laugh` | Laughing at a joke, joking about the outfit |
| `happy` | Receiving a compliment, cheering up |
| `blush` | Shy / flirty reaction to a compliment or flirting |
| `flirt` | Flirting back |
| `proud` | Showing off; confident reaction to compliments or an unusual outfit |
| `tease` | Teasing the player |
| `embarrassed` | Embarrassed about the outfit (e.g. underwear in public) |
| `frustrated` | Frustrated about the outfit or a suggestion |
| `angry` | Being annoyed by the player |
| `sad` | Being teased while shy / sad |
| `shrug` | Not caring much |
| `nod` | Accepting a suggestion |
| `shake_head` | Declining a suggestion |
| `think` | Talking about themselves, not understanding, asking a question |
| `surprised` | Sudden mood change |
| `shiver` | Too cold for the outfit |
| `fan` | Too warm for the outfit |
| `stretch` | Getting bored and changing activity |

## Examples

```
idle.fbx                     default idle
idle_happy.fbx               idle while happy
idle_shy.fbx                 idle for shy characters
idle_sleeping.fbx            idle while the activity is Sleeping
idle_beach_hot.fbx           at the beach in scorching weather
pose_sitting.fbx             a pose you can pick from the Pose menu
pose_lounging.fbx            used automatically while lounging at home
emote_wave.fbx               greeting
emote_wave_shy.fbx           greeting, shy characters only
emote_laugh.fbx              laughing
emote_embarrassed_public.fbx embarrassed while out in public
emote_shiver.fbx             cold
```
