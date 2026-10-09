"""FBX animation library for the 3D viewport.

Drop raw ``.fbx`` files (Mixamo rigs work out of the box; download "Without Skin") into the
library's ``Animations`` folder. The file name decides when an animation is used - see
ANIMATIONS_README below, which is also written into the folder as README.md.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path


ACTIVITY_TOKENS = {
    "Lounging at home": "lounging", "Casual / errands": "errands", "Work / office": "work",
    "School / studying": "studying", "Formal event": "formal", "Date": "date",
    "Party / night out": "party", "Workout / sports": "workout", "Swimming / beach": "swimming",
    "Outdoors / adventure": "adventure", "Combat / battle": "combat", "Sleeping": "sleeping",
    "Manual work / crafting": "crafting", "Ceremony / festival": "festival",
}
MOOD_TOKENS = {
    "Happy": "happy", "Calm": "calm", "Sad": "sad", "Energetic": "energetic", "Romantic": "romantic",
    "Confident": "confident", "Cozy / tired": "tired", "Grumpy / dark": "grumpy", "Mysterious": "mysterious",
    "Focused": "focused", "Adventurous": "adventurous", "Playful": "playful", "Fancy": "fancy",
}
SETTING_TOKENS = {"Public": "public", "Private / at home": "home", "Beach / pool": "beach"}
WEATHER_TOKENS = {
    "Scorching hot": "hot", "Warm": "warm", "Mild": "mild", "Cool": "cool", "Cold": "cold",
    "Freezing / snowy": "snow", "Rainy": "rain", "Windy": "windy",
}
PERSONALITY_TOKENS = ["cheerful", "shy", "confident", "edgy", "elegant", "flirty", "mysterious", "laidback"]
CONTEXT_TOKENS = (set(ACTIVITY_TOKENS.values()) | set(MOOD_TOKENS.values()) | set(SETTING_TOKENS.values())
                  | set(WEATHER_TOKENS.values()) | set(PERSONALITY_TOKENS))

# emote events, what triggers them in the chat
EMOTE_EVENTS = {
    "wave": "Greeting",
    "goodbye": "Saying goodbye",
    "talk": "Any reply with no more specific emote (light talking gesture)",
    "laugh": "Laughing at a joke, joking about the outfit",
    "happy": "Receiving a compliment, cheering up",
    "blush": "Shy / flirty reaction to a compliment or flirting",
    "flirt": "Flirting back",
    "proud": "Showing off; confident reaction to compliments or an unusual outfit",
    "tease": "Teasing the player",
    "embarrassed": "Embarrassed about the outfit (e.g. underwear in public)",
    "frustrated": "Frustrated about the outfit or a suggestion",
    "angry": "Being annoyed by the player",
    "sad": "Being teased while shy / sad",
    "shrug": "Not caring much",
    "nod": "Accepting a suggestion",
    "shake_head": "Declining a suggestion",
    "think": "Talking about themselves, not understanding, asking a question",
    "surprised": "Sudden mood change",
    "shiver": "Too cold for the outfit",
    "fan": "Too warm for the outfit",
    "stretch": "Getting bored and changing activity",
}

_VARIANT = re.compile(r"(?:[_ -]\d+|\s*\(\d+\))$")


@dataclass
class Anim:
    path: Path
    kind: str          # idle / pose / emote
    event: str         # emote event or pose name ("" for idles)
    tokens: tuple      # qualifier tokens


def parse_name(path: Path) -> Anim | None:
    stem = _VARIANT.sub("", path.stem.lower().strip())
    parts = [p for p in re.split(r"[_\s]+", stem) if p]
    if not parts or parts[0] not in ("idle", "pose", "emote"):
        return None
    kind, rest = parts[0], parts[1:]
    event = ""
    if kind == "emote":
        for ev in sorted(EMOTE_EVENTS, key=lambda e: -len(e.split("_"))):
            ev_parts = ev.split("_")
            if rest[:len(ev_parts)] == ev_parts:
                event, rest = ev, rest[len(ev_parts):]
                break
        else:
            return None
    elif kind == "pose":
        event = "_".join(rest)
    return Anim(path, kind, event, tuple(rest))


class AnimationLibrary:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        readme = self.folder / "README.md"
        if not readme.exists() or "ANIMATIONS_README_VERSION 1" not in readme.read_text(encoding="utf-8", errors="ignore"):
            readme.write_text(ANIMATIONS_README, encoding="utf-8")
        self.anims: list[Anim] = []
        self.rescan()

    def rescan(self) -> None:
        self.anims = []
        for p in sorted(self.folder.rglob("*.fbx")):
            a = parse_name(p)
            if a:
                self.anims.append(a)

    def poses(self) -> list[Anim]:
        return [a for a in self.anims if a.kind == "pose"]

    def idles(self) -> list[Anim]:
        return [a for a in self.anims if a.kind == "idle"]

    @staticmethod
    def context(state: dict, tone: str) -> set[str]:
        return {ACTIVITY_TOKENS.get(state.get("activity"), ""), MOOD_TOKENS.get(state.get("mood"), ""),
                SETTING_TOKENS.get(state.get("setting"), ""), WEATHER_TOKENS.get(state.get("weather"), ""),
                tone} - {""}

    def _best(self, candidates: list[Anim], ctx: set[str], rng: random.Random) -> Anim | None:
        scored = []
        for a in candidates:
            quals = [t for t in a.tokens if t in CONTEXT_TOKENS]
            if a.kind == "pose" and len(quals) != len(a.tokens):
                continue  # named pose (e.g. pose_sitting): only used when picked by hand
            if all(t in ctx for t in quals):
                scored.append((len(quals) + (0.5 if a.kind == "idle" else 0), a))
        if not scored:
            return None
        top = max(s for s, _ in scored)
        return rng.choice([a for s, a in scored if s == top])

    def choose_idle(self, state: dict, tone: str, rng: random.Random | None = None) -> Anim | None:
        rng = rng or random.Random()
        return self._best(self.idles() + self.poses(), self.context(state, tone), rng)

    def choose_emote(self, event: str, state: dict, tone: str, rng: random.Random | None = None) -> Anim | None:
        rng = rng or random.Random()
        cands = [a for a in self.anims if a.kind == "emote" and a.event == event]
        return self._best(cands, self.context(state, tone), rng)


def _token_table(mapping: dict[str, str]) -> str:
    return "\n".join(f"| `{tok}` | {label} |" for label, tok in mapping.items())


ANIMATIONS_README = f"""<!-- ANIMATIONS_README_VERSION 1 -->
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
{_token_table(ACTIVITY_TOKENS)}

### Mood
| Word | Mood |
|---|---|
{_token_table(MOOD_TOKENS)}

### Setting
| Word | Setting |
|---|---|
{_token_table(SETTING_TOKENS)}

### Weather
| Word | Weather |
|---|---|
{_token_table(WEATHER_TOKENS)}

### Personality (the character's speaking style, from their profile)
{", ".join(f"`{p}`" for p in PERSONALITY_TOKENS)}

## Emote events

`emote_<event>[_<context words>].fbx`

| Event | Played when |
|---|---|
""" + "\n".join(f"| `{ev}` | {desc} |" for ev, desc in EMOTE_EVENTS.items()) + """

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
"""
