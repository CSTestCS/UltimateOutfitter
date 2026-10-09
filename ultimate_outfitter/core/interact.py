"""Template ("madlibs") conversation engine for the Interact tab.

No language model is used. Replies are chosen from a library of sentence templates
written per *intent* (what the player did) and per *tone* (how this character talks,
derived from the personality profile), then the placeholders are filled in:

    {name} {player} {mood} {mood_adj} {activity} {doing} {setting} {where} {weather}
    {item} {items} {color} {trait} {hi} {bye} {interj} {laugh} {good} {bad}
    {new_activity} {new_doing} {new_where} {fav_activity} {fav_doing}

The character keeps a small state (mood, activity, setting, weather, affinity) that
conversation can change, and reacts to how well the current outfit suits that state:
underdressed, too hot / cold, too formal / casual, wrong for the activity...
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .categories import ACTIVITIES, WEATHER, WEATHER_WARMTH
from .outfit import ACTIVITY_FORMALITY, ACTIVITY_TRAITS, MOODS, SETTINGS, _parse
from .traits import cosine

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

TONES = {
    "cheerful": "cheerful playful cute",
    "shy": "reserved modest cute",
    "confident": "confident bold glamorous regal",
    "edgy": "edgy rebellious gothic tough",
    "elegant": "elegant professional intellectual traditional",
    "flirty": "flirty romantic",
    "mysterious": "mysterious magical",
    "laidback": "laid_back cozy practical nature_loving",
}

WORDS = {
    "hi": {"cheerful": ["Hiii", "Hey hey", "Oh, hi!"], "shy": ["Oh... h-hi", "Um, hello", "Hi..."],
           "confident": ["Well, hello", "There you are", "Hey"], "edgy": ["Yo", "Sup", "Oh. It's you"],
           "elegant": ["Good day", "Hello", "Ah, hello"], "flirty": ["Hey, you", "Well hi there", "Hello, gorgeous"],
           "mysterious": ["Ah... you came", "Greetings", "Hm. Hello"], "laidback": ["Hey", "Heya", "Oh hey"]},
    "bye": {"cheerful": ["See ya!", "Bye bye!", "Later!"], "shy": ["B-bye...", "See you...", "Okay, bye"],
            "confident": ["Until next time", "Don't miss me too much", "Later"], "edgy": ["Whatever. Later", "Bye", "Peace"],
            "elegant": ["Farewell", "Take care", "Goodbye for now"], "flirty": ["Don't keep me waiting", "Bye, cutie", "Miss you already"],
            "mysterious": ["We'll meet again", "Until the stars align", "Farewell"], "laidback": ["Catch you later", "See ya", "Take it easy"]},
    "interj": {"cheerful": ["Ooh", "Yay", "Eee", "Hehe"], "shy": ["Um", "Eep", "Oh", "Ah"],
               "confident": ["Hah", "Naturally", "Please", "Obviously"], "edgy": ["Ugh", "Tch", "Heh", "Whatever"],
               "elegant": ["Hm", "Well", "Indeed", "Ah"], "flirty": ["Mm", "Ooh", "Oh my", "Heh"],
               "mysterious": ["Hm", "Interesting", "Ah", "Mm"], "laidback": ["Eh", "Meh", "Oh", "Huh"]},
    "laugh": {"cheerful": ["*giggles*", "haha!", "*laughs*"], "shy": ["*small laugh*", "hehe...", "*covers mouth*"],
              "confident": ["*smirks*", "ha!", "*laughs*"], "edgy": ["*snorts*", "heh", "*rolls eyes*"],
              "elegant": ["*chuckles*", "*polite laugh*", "*smiles*"], "flirty": ["*winks*", "*giggles*", "hehe~"],
              "mysterious": ["*faint smile*", "*quiet laugh*", "*smiles knowingly*"], "laidback": ["haha", "*chuckles*", "lol"]},
    "good": ["great", "nice", "lovely", "fun", "perfect", "wonderful"],
    "bad": ["awful", "rough", "annoying", "weird", "a mess", "terrible"],
}

MOOD_ADJ = {
    "Happy": "happy", "Calm": "calm", "Sad": "a little down", "Energetic": "full of energy",
    "Romantic": "romantic", "Confident": "confident", "Cozy / tired": "sleepy", "Grumpy / dark": "grumpy",
    "Mysterious": "mysterious", "Focused": "focused", "Adventurous": "adventurous", "Playful": "playful",
    "Fancy": "fancy",
}

# activity -> (noun phrase, -ing phrase)
ACTIVITY_PHRASES = {
    "Lounging at home": ("a lazy day at home", "lounging around"),
    "Casual / errands": ("some errands", "running errands"),
    "Work / office": ("work", "working"),
    "School / studying": ("studying", "studying"),
    "Formal event": ("a formal event", "going to a formal event"),
    "Date": ("a date", "going on a date"),
    "Party / night out": ("a night out", "partying"),
    "Workout / sports": ("a workout", "working out"),
    "Swimming / beach": ("a swim", "swimming"),
    "Outdoors / adventure": ("an adventure", "exploring outside"),
    "Combat / battle": ("a fight", "fighting"),
    "Sleeping": ("bed", "sleeping"),
    "Manual work / crafting": ("a project", "making things"),
    "Ceremony / festival": ("a festival", "going to the festival"),
}
SETTING_PHRASES = {"Public": "out in public", "Private / at home": "at home", "Beach / pool": "at the beach"}

# ---------------------------------------------------------------------------
# Templates: TEMPLATES[intent][tone or "any"] -> list of sentences
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, list[str]]] = {
    "greet": {
        "any": ["{hi}, {player}!", "{hi}! I'm {doing} right now.", "{hi}. I'm feeling {mood_adj} today."],
        "cheerful": ["{hi}, {player}! I'm so glad you're here!", "{hi}! Guess what? I'm {doing} today! {laugh}"],
        "shy": ["{hi}, {player}... I didn't expect you.", "{hi}... n-nice to see you."],
        "confident": ["{hi}, {player}. Come to admire me?", "{hi}. Good timing, I'm looking {good} today."],
        "edgy": ["{hi}. What do you want?", "{hi}, {player}. Don't make this weird."],
        "elegant": ["{hi}, {player}. A pleasure, as always.", "{hi}. I trust your day is going well?"],
        "flirty": ["{hi}, {player}~ I was hoping you'd show up.", "{hi}. You look {good}. Almost as {good} as me."],
        "mysterious": ["{hi}. I sensed you'd come.", "{hi}, {player}. The air feels different today."],
        "laidback": ["{hi}, {player}. What's up?", "{hi}. Just {doing}, nothing special."],
    },
    "how_are_you": {
        "any": ["I'm feeling {mood_adj}.", "Honestly? {mood_adj}.", "{interj}... I'd say {mood_adj}."],
        "cheerful": ["I'm {mood_adj}! Thanks for asking! {laugh}", "Super {mood_adj}! Can't you tell?"],
        "shy": ["Oh, um... {mood_adj}, I think.", "I-I'm {mood_adj}... thanks for asking."],
        "confident": ["{mood_adj}, obviously. And you?", "I'm always at least a little {mood_adj}."],
        "edgy": ["{mood_adj}. Happy now?", "Why do you care? ...Fine. {mood_adj}."],
        "elegant": ["Quite {mood_adj}, thank you for asking.", "I find myself rather {mood_adj} today."],
        "flirty": ["{mood_adj}... but better now that you're here.", "{mood_adj}. Want to make it better?"],
        "mysterious": ["{mood_adj}... like the moon before a storm.", "Hm. {mood_adj}, perhaps."],
        "laidback": ["Pretty {mood_adj}, I guess.", "Eh, {mood_adj}. Can't complain."],
    },
    "ask_activity": {
        "any": ["I'm {doing} {where}.", "Just {doing}. It's {weather} out, so...", "{doing}, mostly."],
        "cheerful": ["I'm {doing}! It's gonna be {good}!", "{doing} {where}! Wanna join?"],
        "shy": ["J-just {doing}... nothing interesting.", "I'm {doing}... is that okay?"],
        "confident": ["{doing}, and doing it well.", "I'm {doing}. Try to keep up."],
        "edgy": ["{doing}. Got a problem with that?", "{doing}. Don't ask why."],
        "elegant": ["I am {doing} {where}.", "At present, {doing}."],
        "flirty": ["{doing}... want to keep me company?", "I'm {doing}. It'd be more fun with you."],
        "mysterious": ["{doing}... or so it seems.", "Some would call it {doing}."],
        "laidback": ["Just {doing}, y'know.", "{doing}. Taking it slow."],
    },
    "ask_outfit": {
        "any": ["I'm wearing {items}.", "Today it's {items}.", "{items}. What do you think?"],
        "cheerful": ["{items}! Isn't it cute?", "I picked {items} today! {laugh}"],
        "shy": ["Just {items}... d-don't stare.", "Um, {items}. Is it okay?"],
        "confident": ["{items}. I look amazing, don't I?", "{items}. Obviously it works."],
        "edgy": ["{items}. Deal with it.", "{items}. Not that it's your business."],
        "elegant": ["Today I chose {items}.", "{items}, carefully selected."],
        "flirty": ["{items}... like what you see?", "{items}. Picked it with you in mind~"],
        "mysterious": ["{items}... chosen for reasons of my own.", "{items}. The {color} called to me."],
        "laidback": ["Eh, {items}. Comfy enough.", "{items}. Whatever was clean."],
    },
    "compliment_outfit": {
        "any": ["Thanks! I like the {item} too.", "{interj}, you noticed the {item}!"],
        "cheerful": ["Really?! Yay! The {item} is my favourite! {laugh}", "Eee, thank you!"],
        "shy": ["Y-you think so...? *blushes*", "Oh... thank you... *looks away*"],
        "confident": ["I know. But thank you.", "Of course it looks {good}. I'm wearing it."],
        "edgy": ["...Thanks, I guess.", "Heh. Not bad taste, {player}."],
        "elegant": ["How kind. The {item} was a deliberate choice.", "Thank you, I'm pleased you approve."],
        "flirty": ["Oh? Just the outfit? {laugh}", "Keep talking like that, {player}~"],
        "mysterious": ["The {color} suits me... as foretold.", "Thank you. Few notice such things."],
        "laidback": ["Oh, thanks! Didn't really think about it.", "Haha, thanks."],
    },
    "tease_outfit": {
        "any": ["Hey! What's wrong with my {item}?", "{interj}, rude."],
        "cheerful": ["Nooo, my {item} is perfect! {laugh}", "Hey! Mean! ...okay it's a little silly."],
        "shy": ["W-what? Is it that bad...? *fidgets*", "Oh no... I knew the {item} was wrong..."],
        "confident": ["Please. You wish you could pull off this {item}.", "{laugh} Jealousy isn't a good look on you."],
        "edgy": ["Say that again, I dare you.", "Like I care what you think about my {item}."],
        "elegant": ["I beg your pardon? This {item} is impeccable.", "How uncouth."],
        "flirty": ["Teasing me? Two can play at that game~", "Oh, you want me to take the {item} off?"],
        "mysterious": ["You mock what you don't understand.", "Hm. Your opinion is noted. And dismissed."],
        "laidback": ["Haha, yeah, it's whatever.", "Eh, it's comfy. Fight me."],
    },
    "compliment_them": {
        "any": ["Aw, thank you, {player}.", "That's sweet of you."],
        "cheerful": ["You're the best, {player}! {laugh}", "Aww! You're gonna make me blush!"],
        "shy": ["Eh?! M-me...? *turns red*", "...thank you. Really."],
        "confident": ["I'm aware. But it's nice to hear.", "Finally, someone with sense."],
        "edgy": ["...Shut up. *looks away*", "Whatever. ...Thanks."],
        "elegant": ["You flatter me, {player}.", "What a gracious thing to say."],
        "flirty": ["Keep going, I'm listening~", "Oh? Tell me more, {player}."],
        "mysterious": ["Kind words... I'll remember them.", "Hm. You see more than most."],
        "laidback": ["Haha, thanks, you too.", "Aw, that's cool of you."],
    },
    "favorite_color": {
        "any": ["I really like {color}.", "{color}, for sure.", "Probably {color}. It just feels like me."],
        "cheerful": ["{color}! It's so happy!", "Ooh, {color}! Definitely {color}!"],
        "shy": ["Um... {color}, maybe?", "I like {color}... it's calming."],
        "confident": ["{color}. It makes me stand out even more.", "{color}. Obviously."],
        "edgy": ["{color}. Don't make it a thing.", "{color}. Got a problem?"],
        "elegant": ["I'm partial to {color}.", "{color} has a certain refinement."],
        "flirty": ["{color}... what's yours?", "{color}. It brings out my eyes, don't you think?"],
        "mysterious": ["{color}... the colour of secrets.", "{color}. It whispers to me."],
        "laidback": ["{color}, I guess.", "Hm... {color}? Yeah, {color}."],
    },
    "about_self": {
        "any": ["People say I'm {trait}. They're not wrong.", "I'd say I'm pretty {trait}.",
                "I love {fav_doing}. That's me."],
        "cheerful": ["I'm {trait} and I love {fav_doing}! What about you?"],
        "shy": ["Me? Um... I guess I'm {trait}. I like {fav_doing}..."],
        "confident": ["I'm {trait}, I'm fabulous, and I'm great at {fav_doing}."],
        "edgy": ["I'm {trait}. That's all you need to know.", "I'm into {fav_doing}. Don't judge."],
        "elegant": ["I consider myself {trait}. In my free time I enjoy {fav_doing}."],
        "flirty": ["I'm {trait}... and I like {fav_doing}. Maybe with you?"],
        "mysterious": ["I am... {trait}. Some things are better left unsaid."],
        "laidback": ["I'm pretty {trait}. Mostly I just like {fav_doing}."],
    },
    "joke": {
        "any": ["{laugh} Okay, that was funny.", "{laugh} You're ridiculous, {player}."],
        "cheerful": ["{laugh} Stoppp, my sides!", "Hahaha! Tell another one!"],
        "shy": ["*tries not to laugh* ...{laugh}", "Pfft... {laugh}"],
        "confident": ["{laugh} Not bad. I've heard better. From me.", "Ha! Okay, that one was decent."],
        "edgy": ["...Heh. Fine, that was funny.", "{laugh} That's so dumb. I love it."],
        "elegant": ["{laugh} How droll.", "Oh my. That was rather amusing."],
        "flirty": ["{laugh} Funny and cute? Dangerous combo.", "Ha! Keep making me laugh, {player}~"],
        "mysterious": ["{laugh} ...Amusing.", "A rare smile, just for you."],
        "laidback": ["Haha, good one.", "{laugh} Classic."],
    },
    "flirt": {
        "any": ["{interj}... you're bold today, {player}.", "{laugh} Is that so?"],
        "cheerful": ["Eee! {player}! {laugh}", "Hehe, you're sweet!"],
        "shy": ["W-w-what?! *hides face*", "Y-you can't just say that..."],
        "confident": ["Naturally you're attracted to me.", "Took you long enough."],
        "edgy": ["Ugh, gross. ...Do it again.", "Smooth. Real smooth. *smirks*"],
        "elegant": ["Why, {player}, how forward of you.", "I'm flattered... truly."],
        "flirty": ["Oh, I like where this is going~", "Careful, {player}. I flirt back."],
        "mysterious": ["Hm... perhaps fate brought you here.", "Your heart is easy to read, {player}."],
        "laidback": ["Haha, smooth.", "Oh? Heh, you're cute."],
    },
    "comfort": {
        "any": ["Thanks, {player}. That helps.", "...Yeah. Thanks for being here."],
        "cheerful": ["You always know how to cheer me up!", "Okay! I feel better already! {laugh}"],
        "shy": ["...thank you. Really.", "*small smile* ...okay."],
        "confident": ["I wasn't upset. ...But thanks.", "Fine. You helped. A little."],
        "edgy": ["I don't need comfort. ...But okay.", "...Thanks. Don't tell anyone."],
        "elegant": ["Your kindness is appreciated.", "Thank you. I feel much more composed."],
        "flirty": ["Mm, keep doing that~", "You're sweet. Come here."],
        "mysterious": ["The clouds part, a little.", "...Thank you. Truly."],
        "laidback": ["Yeah, you're right. It's all good.", "Thanks, I needed that."],
    },
    "annoy": {
        "any": ["Hey! Cut it out!", "{interj}! Stop that, {player}!"],
        "cheerful": ["Heyyy, quit it! {laugh}", "Okay, that's a little annoying..."],
        "shy": ["P-please stop...", "*shrinks away* ...stop."],
        "confident": ["Do you know who you're talking to?", "Try that again and see what happens."],
        "edgy": ["Do that again and you're dead.", "Ugh. Seriously?!"],
        "elegant": ["That is quite enough.", "How tiresome."],
        "flirty": ["Annoying me? Is that how you show you care?", "Rude~"],
        "mysterious": ["You test my patience.", "...I'll remember this."],
        "laidback": ["Dude. Chill.", "Not cool, {player}."],
    },
    "goodbye": {
        "any": ["{bye}, {player}!", "{bye}."],
        "cheerful": ["{bye}! Come back soon!", "{bye}! That was fun!"],
        "shy": ["{bye}... thanks for talking to me.", "{bye}... um, come back?"],
        "confident": ["{bye}. You'll be thinking about me.", "{bye}."],
        "edgy": ["{bye}. Finally.", "{bye}. ...Don't be a stranger."],
        "elegant": ["{bye}, {player}. It was a pleasure.", "{bye}."],
        "flirty": ["{bye}~ Dream of me.", "{bye}, {player}. *blows a kiss*"],
        "mysterious": ["{bye}. Our paths will cross again.", "{bye}..."],
        "laidback": ["{bye}! Take care.", "{bye}, see you around."],
    },
    # suggestions -----------------------------------------------------------------
    "accept_activity": {
        "any": ["Sure, let's go {new_doing}!", "{new_activity}? Okay, why not.", "Fine, {new_doing} it is."],
        "cheerful": ["Ooh, {new_doing}! Let's go!", "Yes yes yes! {new_activity}!"],
        "shy": ["O-okay... {new_doing} sounds nice.", "If you want... {new_doing} is fine."],
        "confident": ["{new_doing}? I'll be the best at it.", "Lead the way. I'll make it look {good}."],
        "edgy": ["Ugh, fine. {new_doing}.", "{new_doing}? ...Okay, could be fun."],
        "elegant": ["{new_activity} sounds agreeable.", "Very well, {new_doing} it is."],
        "flirty": ["{new_doing}? With you? Absolutely~", "Only if you stay close."],
        "mysterious": ["{new_doing}... yes, the time is right.", "As you wish."],
        "laidback": ["Sure, {new_doing} sounds chill.", "Yeah, okay, let's do it."],
    },
    "decline_activity": {
        "any": ["Nah, I don't feel like {new_doing}.", "Not right now, {player}.", "Maybe later."],
        "cheerful": ["Hmm, not {new_doing}... maybe something else?", "Aww, I'm not really in the mood for that."],
        "shy": ["U-um... I'd rather not...", "Is it okay if we don't?"],
        "confident": ["{new_doing}? Beneath me.", "No. I have better plans."],
        "edgy": ["No way.", "{new_doing}? Hard pass."],
        "elegant": ["I'm afraid I must decline.", "Perhaps another time."],
        "flirty": ["Mm, not that... but I have other ideas~", "Convince me."],
        "mysterious": ["No. Not today.", "The signs say otherwise."],
        "laidback": ["Eh, too much effort.", "Nah, I'm good here."],
    },
    "accept_setting": {
        "any": ["Okay, let's head {new_where}.", "Sure, {new_where} works."],
        "shy": ["{new_where}...? Okay, if you come too.", "A-alright."],
        "edgy": ["Fine. {new_where}. Whatever.", "Sure, let's bounce."],
        "flirty": ["{new_where}? Ooh, lead the way~"],
        "elegant": ["Very well, {new_where} it is."],
    },
    "decline_setting": {
        "any": ["I'd rather stay {where}.", "Nah, I'm comfy {where}."],
        "shy": ["I-I'd rather not go {new_where}...", "Can we stay {where}?"],
        "confident": ["No, {where} suits me just fine."],
        "edgy": ["Not happening."],
    },
    "change_mood": {
        "any": ["Okay, okay, I'm feeling {mood_adj} now.", "You know what? I feel {mood_adj}."],
    },
    # outfit reactions --------------------------------------------------------------
    "outfit_ok": {
        "any": ["And I think my outfit is just right for this.", "Good thing I'm dressed for it.",
                "My {item} is perfect for {doing}."],
        "confident": ["Dressed perfectly, as usual.", "Look at me. Nailed it."],
        "laidback": ["And I'm comfy. Win-win."],
    },
    "issue_embarrassed": {
        "any": ["W-wait... I'm only in {items} {where}! *blushes furiously*",
                "Oh no... I'm not dressed for {doing}! Don't look!",
                "*covers up* This {item} is NOT okay for this!"],
    },
    "issue_frustrated": {
        "any": ["Ugh, this {item} is all wrong for {doing}.", "Seriously? I can't go {doing} dressed like this.",
                "Great. I'm wearing {items} and it's {weather}. Perfect. *sigh*"],
    },
    "issue_proud": {
        "any": ["So I'm in {items} {where}. Let them stare.", "Underdressed? I call it a statement.",
                "{laugh} Who cares if my {item} isn't for {doing}? I look {good}."],
    },
    "issue_teasing": {
        "any": ["{laugh} Bet you can't stop looking at my {item}, huh {player}?",
                "Like what you see? It's only {items}, after all~",
                "Don't tell me you're blushing because I'm in {items}! {laugh}"],
    },
    "issue_joking": {
        "any": ["{laugh} I'm {doing} in {items}! I'm a trendsetter!", "Okay, the {item} might not be ideal for {doing}. {laugh}"],
    },
    "issue_shrug": {
        "any": ["Eh, the {item} isn't really for {doing}, but whatever.", "I'm a bit {temp_word}, but I'll live."],
    },
    "issue_cold": {"any": ["Brr... it's {weather} and I'm in {items}. I'm freezing!", "*shivers* Should've worn more than {items}."]},
    "issue_hot": {"any": ["Phew, it's {weather}. I'm way too warm in this {item}.", "*fans self* This {item} is way too hot for today."]},
    "issue_formal": {"any": ["I feel so overdressed for {doing}.", "Wearing my {item} for {doing}? Bit much, huh?"]},
    "issue_casual": {"any": ["Oof, I'm way too casual for {doing}.", "Is my {item} too sloppy for {doing}?"]},
    "issue_nothing": {"any": ["I... don't actually have an outfit picked out yet.", "I haven't even got dressed yet!"]},
    # initiative ----------------------------------------------------------------------
    "init_question": {
        "any": ["So, {player}, what have you been up to?", "Hey {player}, what's your favourite colour?",
                "Do you like {fav_doing}, {player}?", "What do you think I should do today?"],
        "shy": ["Um... {player}? Can I ask you something? ...Do you like {fav_doing}?"],
        "edgy": ["Hey. You. What's your deal, anyway?"],
        "flirty": ["So, {player}... are you seeing anyone? {laugh}"],
        "mysterious": ["Tell me, {player}... what do you dream about?"],
    },
    "init_share": {
        "any": ["You know, I've been thinking about {fav_doing} a lot lately.", "I love this kind of {weather} weather.",
                "I really want to wear more {color}.", "Today feels like a {good} day for {fav_doing}."],
        "cheerful": ["Guess what! I want to try {fav_doing} today!", "I'm in such a {mood_adj} mood! {laugh}"],
        "shy": ["...I kind of want to go {fav_doing} later. Just saying."],
        "confident": ["I've decided today will be {good}. Because I said so."],
        "edgy": ["Everything's boring today. Ugh."],
        "elegant": ["I find {weather} weather rather agreeable."],
        "mysterious": ["The {color} hour approaches..."],
        "laidback": ["Man, I could go for some {fav_doing} right now."],
    },
    "init_bored": {
        "any": ["I'm bored. Let's go {new_doing}!", "Enough of {doing}. I'm going {new_doing}.",
                "You know what? I'm switching to {new_activity}."],
        "shy": ["U-um... would it be okay if we went {new_doing}?"],
        "edgy": ["This is boring. I'm going {new_doing}. Come or don't."],
        "elegant": ["I believe I shall move on to {new_activity}."],
    },
    "init_mood": {
        "any": ["Hm... suddenly I'm feeling {mood_adj}.", "I don't know why, but I feel {mood_adj} now."],
    },
    "unknown": {
        "any": ["Hm? What do you mean?", "{interj}... I'm not sure what you're saying, {player}.",
                "Huh. Okay.", "{laugh} Sure, {player}."],
    },
}

# outfit issue -> reaction template key per tone
ISSUE_REACTION = {
    "underdressed": {"shy": "issue_embarrassed", "elegant": "issue_embarrassed", "cheerful": "issue_joking",
                     "confident": "issue_proud", "edgy": "issue_proud", "flirty": "issue_teasing",
                     "mysterious": "issue_shrug", "laidback": "issue_shrug"},
    "wrong_activity": {"shy": "issue_embarrassed", "elegant": "issue_frustrated", "cheerful": "issue_joking",
                       "confident": "issue_proud", "edgy": "issue_frustrated", "flirty": "issue_teasing",
                       "mysterious": "issue_shrug", "laidback": "issue_shrug"},
}

# keyword -> intent for the free-text box
KEYWORDS = [
    (r"\b(hi|hello|hey|yo|greetings|morning)\b", "greet"),
    (r"\b(bye|goodbye|see you|later|good night)\b", "goodbye"),
    (r"how are you|how do you feel|feeling|mood", "how_are_you"),
    (r"what are you doing|what('?s| is) up|doing today|plans", "ask_activity"),
    (r"(ugly|silly|weird|ridiculous|dumb).*(outfit|clothes|wear)|(outfit|clothes).*(ugly|silly|weird)", "tease_outfit"),
    (r"(nice|cute|pretty|great|love|like).*(outfit|clothes|dress|shirt|look)", "compliment_outfit"),
    (r"wearing|outfit|clothes", "ask_outfit"),
    (r"colou?r", "favorite_color"),
    (r"about you|yourself|who are you|hobby|hobbies", "about_self"),
    (r"joke|funny|haha|lol", "joke"),
    (r"beautiful|cute|handsome|gorgeous|date me|love you|kiss", "flirt"),
    (r"you('re| are) (great|amazing|awesome|smart|kind)|proud of you", "compliment_them"),
    (r"(it'?s|it will be) ok|don'?t worry|cheer up|hug", "comfort"),
    (r"poke|annoy|boo|loser|stupid", "annoy"),
]

# mood effects of each intent, per tone (fallback "any")
MOOD_EFFECTS = {
    "compliment_outfit": {"any": ["Happy", "Confident"], "shy": ["Happy", "Romantic"], "edgy": ["Playful"]},
    "compliment_them": {"any": ["Happy"], "flirty": ["Romantic"], "shy": ["Romantic", "Happy"]},
    "tease_outfit": {"any": ["Grumpy / dark"], "cheerful": ["Playful"], "flirty": ["Playful"],
                     "shy": ["Sad"], "confident": ["Confident"]},
    "joke": {"any": ["Happy", "Playful"], "elegant": ["Happy"], "mysterious": ["Calm"]},
    "flirt": {"any": ["Romantic"], "edgy": ["Playful"], "shy": ["Romantic"], "elegant": ["Romantic"]},
    "comfort": {"any": ["Calm", "Happy"]},
    "annoy": {"any": ["Grumpy / dark"], "flirty": ["Playful"], "cheerful": ["Playful"], "shy": ["Sad"]},
}
AFFINITY = {"compliment_outfit": 1, "compliment_them": 2, "tease_outfit": -1, "joke": 1, "flirt": 1,
            "comfort": 2, "annoy": -2, "greet": 0.5}


@dataclass
class Reply:
    text: str
    changes: dict[str, Any] = field(default_factory=dict)


class Conversation:
    """Conversation state for one character. ``character`` is a core.character.Character."""

    def __init__(self, character, player: str = "you", rng: random.Random | None = None):
        self.character = character
        self.player = player
        self.rng = rng or random.Random()
        data = character.data
        st = data.setdefault("state", {})
        ctx = (data.get("current_outfit") or {}).get("context", {})
        st.setdefault("mood", ctx.get("mood") or self.rng.choice(list(MOODS)))
        st.setdefault("activity", ctx.get("activity") or self.rng.choice(ACTIVITIES))
        st.setdefault("setting", ctx.get("setting") or self.rng.choice(SETTINGS))
        st.setdefault("weather", ctx.get("weather") or self.rng.choice(WEATHER[:5]))
        st.setdefault("affinity", 0.0)
        data.setdefault("chat_log", [])

    # ------------------------------------------------------------------ helpers
    @property
    def state(self) -> dict:
        return self.character.data["state"]

    def tone(self) -> str:
        traits = self.character.traits
        scores = {t: sum(traits.get(k, 0) for k in v.split()) for t, v in TONES.items()}
        # mood nudges the tone a little
        mood = self.state["mood"]
        if mood in ("Grumpy / dark",):
            scores["edgy"] += 0.6
        elif mood in ("Romantic",):
            scores["flirty"] += 0.6
        elif mood in ("Happy", "Playful", "Energetic"):
            scores["cheerful"] += 0.4
        elif mood in ("Sad", "Cozy / tired"):
            scores["shy"] += 0.3
        ranked = sorted(scores.items(), key=lambda t: -t[1])
        if len(ranked) > 1 and ranked[1][1] > 0 and self.rng.random() < 0.25:
            return ranked[1][0]
        return ranked[0][0]

    def outfit_pieces(self) -> list[dict]:
        outfit = self.character.data.get("current_outfit") or {}
        return outfit.get("pieces", [])

    def _piece_label(self, p: dict) -> str:
        pal = p.get("palettes") or []
        return (f"{pal[0]} " if pal else "") + p["name"]

    def _fav_activity(self) -> str:
        traits = self.character.traits
        scored = [(cosine(traits, _parse(ACTIVITY_TRAITS.get(a, ""))), a) for a in ACTIVITIES
                  if a not in ("Sleeping",)]
        scored.sort(reverse=True)
        top = [a for _, a in scored[:4]] or ["Casual / errands"]
        return self.rng.choice(top)

    def _fill(self, template: str, tone: str, extra: dict | None = None) -> str:
        st = self.state
        pieces = self.outfit_pieces()
        items = [self._piece_label(p) for p in pieces]
        traits = self.character.traits
        top_traits = [k for k, _ in sorted(traits.items(), key=lambda t: -t[1])[:4]] or ["unique"]
        matched = self.character.matched_palettes() if hasattr(self.character, "matched_palettes") else []
        fav = self._fav_activity()
        values = {
            "name": self.character.name, "player": self.player,
            "mood": st["mood"].lower(), "mood_adj": MOOD_ADJ.get(st["mood"], st["mood"].lower()),
            "activity": ACTIVITY_PHRASES.get(st["activity"], (st["activity"].lower(),) * 2)[0],
            "doing": ACTIVITY_PHRASES.get(st["activity"], (st["activity"].lower(),) * 2)[1],
            "setting": st["setting"].lower(), "where": SETTING_PHRASES.get(st["setting"], st["setting"].lower()),
            "weather": st["weather"].lower(),
            "item": self.rng.choice(items) if items else "clothes",
            "items": _join(items) if items else "nothing in particular",
            "color": self.rng.choice(matched)["name"] if matched else "blue",
            "trait": self.rng.choice(top_traits).replace("_", " "),
            "hi": self.rng.choice(WORDS["hi"].get(tone, ["Hi"])),
            "bye": self.rng.choice(WORDS["bye"].get(tone, ["Bye"])),
            "interj": self.rng.choice(WORDS["interj"].get(tone, ["Oh"])),
            "laugh": self.rng.choice(WORDS["laugh"].get(tone, ["haha"])),
            "good": self.rng.choice(WORDS["good"]), "bad": self.rng.choice(WORDS["bad"]),
            "fav_activity": ACTIVITY_PHRASES[fav][0], "fav_doing": ACTIVITY_PHRASES[fav][1],
            "temp_word": "chilly" if WEATHER_WARMTH.get(st["weather"], 2) >= 3 else "warm",
        }
        values.update(extra or {})
        text = template
        for k, v in values.items():
            text = text.replace("{" + k + "}", str(v))
        text = re.sub(r"\s+", " ", text).strip()
        return text[:1].upper() + text[1:]

    def say(self, intent: str, tone: str | None = None, extra: dict | None = None) -> str:
        tone = tone or self.tone()
        bank = TEMPLATES.get(intent, TEMPLATES["unknown"])
        options = list(bank.get(tone, [])) * 2 + list(bank.get("any", []))
        if not options:
            options = TEMPLATES["unknown"]["any"]
        return self._fill(self.rng.choice(options), tone, extra)

    # ------------------------------------------------------------------ outfit check
    def outfit_issues(self) -> list[tuple[str, str]]:
        """Return [(issue, detail)] for the current outfit and state."""
        pieces = self.outfit_pieces()
        st = self.state
        if not pieces:
            return [("nothing", "")]
        wardrobe = self.character.data.get("wardrobe", {})
        lib = self.character.library
        attrs = []
        slots = set()
        for p in pieces:
            e = wardrobe.get(p.get("entry_id"), {})
            slots.add(p.get("slot") or e.get("slot"))
            item = lib.items.get(e.get("item_id"), {})
            attrs.append(item.get("attrs", {}))
        issues = []
        covering = {"base_top", "legs", "full_body", "sleepwear", "outer", "mid_layer"}
        swim = {"swim_top", "swim_bottom", "swim_full"}
        if not slots & covering and st["setting"] == "Public":
            issues.append(("underdressed", ""))
        need = WEATHER_WARMTH.get(st["weather"], 2)
        warmth = max([a.get("warmth", 1) for a in attrs] or [0]) + 0.5 * len(slots & {"outer", "mid_layer"})
        if warmth < need - 1.5:
            issues.append(("cold", ""))
        elif warmth > need + 2:
            issues.append(("hot", ""))
        target = ACTIVITY_FORMALITY.get(st["activity"], 1)
        formality = max([a.get("formality", 1) for a in attrs] or [1])
        if formality - target >= 2:
            issues.append(("formal", ""))
        elif target - formality >= 1.5:
            issues.append(("casual", ""))
        acts = {a for at in attrs for a in at.get("activities", [])}
        specialised = st["activity"] in ("Swimming / beach", "Workout / sports", "Combat / battle", "Sleeping")
        if specialised and st["activity"] not in acts:
            issues.append(("wrong_activity", ""))
        if slots & swim and st["activity"] in ("Work / office", "Formal event", "School / studying"):
            issues.append(("wrong_activity", ""))
        return issues

    def react_to_outfit(self, tone: str | None = None, always: bool = False) -> str | None:
        tone = tone or self.tone()
        issues = self.outfit_issues()
        if not issues:
            return self.say("outfit_ok", tone) if always else None
        issue = issues[0][0]
        if issue in ISSUE_REACTION:
            key = ISSUE_REACTION[issue].get(tone, "issue_shrug")
            if key == "issue_embarrassed":
                self.state["mood"] = "Sad" if tone == "shy" else "Grumpy / dark"
            elif key == "issue_frustrated":
                self.state["mood"] = "Grumpy / dark"
            elif key in ("issue_teasing", "issue_joking"):
                self.state["mood"] = "Playful"
            return self.say(key, tone)
        return self.say(f"issue_{issue}", tone)

    # ------------------------------------------------------------------ actions
    def respond(self, intent: str, **kwargs) -> Reply:
        """Player action -> character reply."""
        tone = self.tone()
        st = self.state
        changes: dict[str, Any] = {}
        if intent == "suggest_activity":
            act = kwargs["activity"]
            fit = cosine(self.character.traits, _parse(ACTIVITY_TRAITS.get(act, "laid_back")))
            chance = 0.45 + 0.4 * fit + 0.04 * st["affinity"]
            extra = {"new_activity": ACTIVITY_PHRASES[act][0], "new_doing": ACTIVITY_PHRASES[act][1]}
            if self.rng.random() < chance:
                st["activity"] = act
                changes["activity"] = act
                text = self.say("accept_activity", tone, extra)
                follow = self.react_to_outfit(tone)
                if follow:
                    text += " " + follow
            else:
                text = self.say("decline_activity", tone, extra)
            return self._finish(intent, text, changes)
        if intent == "suggest_setting":
            where = kwargs["setting"]
            extra = {"new_where": SETTING_PHRASES.get(where, where.lower())}
            shy = tone == "shy" and where == "Public"
            if self.rng.random() < (0.35 if shy else 0.7) + 0.04 * st["affinity"]:
                st["setting"] = where
                changes["setting"] = where
                text = self.say("accept_setting", tone, extra)
                follow = self.react_to_outfit(tone)
                if follow:
                    text += " " + follow
            else:
                text = self.say("decline_setting", tone, extra)
            return self._finish(intent, text, changes)
        if intent == "set_mood":
            st["mood"] = kwargs["mood"]
            changes["mood"] = st["mood"]
            return self._finish(intent, self.say("change_mood", tone), changes)
        if intent == "set_weather":
            st["weather"] = kwargs["weather"]
            changes["weather"] = st["weather"]
            text = self.react_to_outfit(tone, always=True) or self.say("init_share", tone)
            return self._finish(intent, text, changes)

        text = self.say(intent, tone)
        if intent == "ask_outfit":
            follow = self.react_to_outfit(tone, always=True)
            if follow:
                text += " " + follow
        elif intent in ("greet", "how_are_you") and self.rng.random() < 0.5:
            follow = self.react_to_outfit(tone)
            if follow:
                text += " " + follow
        effects = MOOD_EFFECTS.get(intent)
        if effects:
            moods = effects.get(tone, effects["any"])
            if self.rng.random() < 0.7:
                new = self.rng.choice(moods)
                if new != st["mood"]:
                    st["mood"] = new
                    changes["mood"] = new
        st["affinity"] = max(-10.0, min(10.0, st["affinity"] + AFFINITY.get(intent, 0)))
        return self._finish(intent, text, changes)

    def initiative(self) -> Reply:
        """The character speaks up on their own (not as a reply)."""
        tone = self.tone()
        st = self.state
        changes: dict[str, Any] = {}
        issues = self.outfit_issues()
        roll = self.rng.random()
        if issues and issues[0][0] != "nothing" and roll < 0.35:
            text = self.react_to_outfit(tone) or self.say("init_share", tone)
        elif roll < 0.55:
            act = self._fav_activity()
            if act != st["activity"]:
                extra = {"new_activity": ACTIVITY_PHRASES[act][0], "new_doing": ACTIVITY_PHRASES[act][1]}
                text = self.say("init_bored", tone, extra)
                st["activity"] = act
                changes["activity"] = act
                follow = self.react_to_outfit(tone)
                if follow:
                    text += " " + follow
            else:
                text = self.say("init_share", tone)
        elif roll < 0.7:
            new = self.rng.choice(list(MOODS))
            st["mood"] = new
            changes["mood"] = new
            text = self.say("init_mood", tone)
        elif roll < 0.85:
            text = self.say("init_question", tone)
        else:
            text = self.say("init_share", tone)
        return self._finish("initiative", text, changes)

    def _finish(self, intent: str, text: str, changes: dict) -> Reply:
        log = self.character.data["chat_log"]
        log.append({"t": time.time(), "who": "char", "text": text, "intent": intent})
        del log[:-300]
        self.character.save()
        return Reply(text, changes)

    def log_player(self, text: str) -> None:
        log = self.character.data["chat_log"]
        log.append({"t": time.time(), "who": "player", "text": text})
        del log[:-300]

    @staticmethod
    def intent_from_text(text: str) -> str:
        low = text.lower()
        for pattern, intent in KEYWORDS:
            if re.search(pattern, low):
                return intent
        return "unknown"


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    if len(words) > 4:
        words = words[:4] + ["more"]
    return ", ".join(words[:-1]) + " and " + words[-1]
