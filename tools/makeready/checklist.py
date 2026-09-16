"""Make-Ready Inspection checklist schema.

Mirrors the Doss & Spaulding hard-copy Turn/Make-Ready Checklist, with a short
plain-English hint on every item so a less-experienced staff member knows what
"good" actually looks like.

Structure:
  PROFILE  - the setup questions that decide which sections appear
  SECTIONS - the master list; each has an optional `when` (profile key) and
             an optional `repeat` (bedrooms / bathrooms)
  build(profile) -> the concrete section list for one property

Item keys are stable strings ("front_door:3", "bath2:7") so a saved walkthrough
on someone's phone still lines up after a deploy.
"""

# --------------------------------------------------------------------------
# Setup questions
# --------------------------------------------------------------------------
PROFILE = [
    {"key": "bedrooms",  "label": "Bedrooms",  "type": "count", "min": 1, "max": 6, "default": 3},
    {"key": "bathrooms", "label": "Bathrooms", "type": "count", "min": 1, "max": 4, "default": 2},
    {"key": "back_door",     "label": "Back or side exterior door", "type": "bool", "default": True},
    {"key": "dining",        "label": "Separate dining room",       "type": "bool", "default": True},
    {"key": "den",           "label": "Den / bonus room",           "type": "bool", "default": False},
    {"key": "fireplace",     "label": "Fireplace",                  "type": "bool", "default": False},
    {"key": "sliding_doors", "label": "Sliding glass doors",        "type": "bool", "default": False},
    {"key": "fridge",        "label": "Refrigerator provided",      "type": "bool", "default": True},
    {"key": "dishwasher",    "label": "Dishwasher",                 "type": "bool", "default": True},
    {"key": "disposal",      "label": "Garbage disposal",           "type": "bool", "default": True},
    {"key": "laundry",       "label": "Washer / dryer room or closet", "type": "bool", "default": True},
    {"key": "carpet",        "label": "Carpet anywhere in the unit", "type": "bool", "default": True},
    {"key": "utility",       "label": "Outside utility room",       "type": "bool", "default": False},
    {"key": "patio",         "label": "Patio or deck",              "type": "bool", "default": True},
    {"key": "garage",        "label": "Garage or basement",         "type": "bool", "default": False},
    {"key": "crawlspace",    "label": "Crawlspace",                 "type": "bool", "default": True},
    {"key": "shed",          "label": "Shed / outbuilding",         "type": "bool", "default": False},
    {"key": "fence",         "label": "Fence and gates",            "type": "bool", "default": False},
]

PROFILE_DEFAULTS = {p["key"]: p["default"] for p in PROFILE}

# --------------------------------------------------------------------------
# Master checklist.  ("label", "hint")  — hint may be "" but shouldn't be.
# --------------------------------------------------------------------------
_DOOR = [
    ("Closes correctly", "Close it fully. It should latch without lifting, shoving or slamming."),
    ("Weather stripping", "Close the door and look for daylight around the edges. Stripping should be soft, not cracked or flattened."),
    ("Door stops", "Is there a stop on the wall or floor so the knob can't punch a hole?"),
    ("Deadbolt", "With the door closed, turn it. The bolt should throw all the way into the frame with no force."),
    ("Keyless lock", "Check the keypad locks and unlocks. Note the code if there is one."),
    ("Door paint", "Look for peeling, scuffs, kick marks or bare wood — check both sides."),
    ("Lock re-keyed or changed", "Has the lock been re-keyed since the last tenant moved out? If you don't know, flag it."),
]

SECTIONS = [
    # ---------------- INTERIOR ----------------
    {"id": "front_door", "zone": "Interior", "name": "Front Door", "items": _DOOR + [
        ("2 keys ready for tenant (doors and mailbox)", "Count them. Two door keys plus a mailbox key ready to hand over?"),
        ("2 keys for management office (all doors / mail)", "Two more full sets for the office."),
    ]},

    {"id": "back_door", "zone": "Interior", "name": "Back Door", "when": "back_door", "items": _DOOR + [
        ("2 keys ready for tenant", "Two keys for this door ready to hand over?"),
        ("2 keys for management office", "Two more for the office."),
    ]},

    {"id": "living", "zone": "Interior", "name": "Living Room", "items": [
        ("Lights & fixtures", "Flip every switch. All bulbs working, globes present and not cracked?"),
        ("Tile / flooring", "Walk the whole floor. Look for gaps, lifting edges, stains and soft spots."),
        ("Bookcase / built-ins", "Any built-in shelving solid and not sagging?"),
        ("Blinds installed and in good condition", "Raise and lower each one. Bent slats, missing wands, broken cords?"),
        ("Receptacle & switch covers installed", "Every outlet and switch needs a cover plate."),
    ]},

    {"id": "fireplace", "zone": "Interior", "name": "Fireplace", "when": "fireplace", "items": [
        ("Damper", "Reach up and work the damper open and closed. It should move and hold position."),
        ("Screen", "Screen or glass doors present, and do they slide or close?"),
        ("Grate", "Is the grate there and not burned through?"),
        ("Paint / surround", "Check the surround and mantel for soot, peeling and cracks."),
    ]},

    {"id": "slider", "zone": "Interior", "name": "Sliding Glass Doors", "when": "sliding_doors", "items": [
        ("Rolls smoothly", "Slide it end to end with one hand. Sticking or grinding means the rollers are shot."),
        ("Locks easily", "The latch should catch without lifting or shoving the door."),
        ("Lock pin / security bar", "Is the bar or pin present in the track?"),
        ("Screen", "Screen on its track, no holes or tears?"),
    ]},

    {"id": "dining", "zone": "Interior", "name": "Dining Room", "when": "dining", "items": [
        ("Lights & fixtures", "Switch on. Bulbs working and the fixture secure to the ceiling?"),
        ("Shelves / cabinets", "Built-ins solid, doors close, shelves not sagging?"),
        ("Screens", "Window screens present and intact?"),
        ("Doors", "Open, close and latch without rubbing?"),
    ]},

    {"id": "den", "zone": "Interior", "name": "Den", "when": "den", "items": [
        ("Lights & fixtures", "Switch on. Bulbs working and the fixture secure?"),
        ("Shelves / cabinets", "Built-ins solid, doors close, shelves not sagging?"),
        ("Screens", "Window screens present and intact?"),
        ("Doors", "Open, close and latch without rubbing?"),
    ]},

    {"id": "range", "zone": "Interior", "name": "Kitchen — Range & Vent Hood", "items": [
        ("Vent hood / microwave works (all speeds & light)", "Run the fan through every speed and turn the light on. Check the filter for grease."),
        ("All burners work", "Turn each one on. Gas should light evenly, electric should glow."),
        ("Indicator lights", "Do the burner and oven 'on' lights come on?"),
        ("Oven racks", "Right number of racks, not warped or rusted?"),
        ("Oven heats up", "Set it to 350 and come back to it later in the walk. It should be hot."),
        ("Range clean inside and out", "Check under the burners, inside the oven and the drip pans."),
    ]},

    {"id": "fridge", "zone": "Interior", "name": "Kitchen — Refrigerator", "when": "fridge", "items": [
        ("Filter(s) replaced", "Water filter changed? Check the indicator light or the date written on it."),
        ("Fridge & freezer cooling properly", "It should be cold now, not just humming. Check the freezer is actually frozen."),
        ("Icemaker / water dispenser works", "Dispense water and look for ice in the bin."),
        ("Clean inside, and gaskets seal", "Check the door seals close tight and there's no odor."),
    ]},

    {"id": "dishwasher", "zone": "Interior", "name": "Kitchen — Dishwasher", "when": "dishwasher", "items": [
        ("Runs a full cycle", "Start it early in your walk and check back. It should fill, wash and drain."),
        ("Drains fully, no standing water", "Open it at the end — a puddle in the bottom means a drain problem."),
        ("No leaks at the door or underneath", "Feel the floor in front and look under the toe kick."),
        ("Racks, wheels and spray arm intact", "Pull both racks out. Missing wheels and rusted tines are common."),
        ("Clean inside", "Check the filter at the bottom for debris."),
    ]},

    {"id": "disposal", "zone": "Interior", "name": "Kitchen — Disposal", "when": "disposal", "items": [
        ("Clear & free", "Look down with a flashlight for silverware or debris. Never put your hand in it."),
        ("Reset not tripped", "Press the small red reset button on the underside of the unit."),
        ("Stopper in place", "Is the sink stopper / splash plug there?"),
        ("Switch works", "Run water and flip the switch. Humming without spinning means it's jammed."),
        ("Splash guard", "The rubber baffle in the drain opening — present and not torn?"),
        ("Check operation", "Runs smooth with water, no grinding or rattling, and drains clear."),
    ]},

    {"id": "kitchen_plumb", "zone": "Interior", "name": "Kitchen — Plumbing", "items": [
        ("No leaking faucet", "Run hot and cold, then shut off. Watch for drips at the spout and around the base."),
        ("Aerator clean and present", "Weak or spraying flow means a clogged aerator."),
        ("No leaking drains — check connections are tight", "Open the cabinet, run water, and feel every joint under the sink with a dry hand."),
        ("Stoppers & pop-ups present", "Sink stopper there and holding water?"),
        ("Sink undamaged, strainers & covers present", "Check for chips, rust and a missing basket strainer."),
        ("Caulking", "The bead around the sink rim and backsplash — cracked, moldy or missing?"),
    ]},

    {"id": "kitchen_cab", "zone": "Interior", "name": "Kitchen — Floor, Cabinets & Drawers", "items": [
        ("Floor tile good", "Cracked, loose or missing tiles? Look hardest in front of the sink."),
        ("Caulk & moldings at floor", "Baseboard and shoe molding attached, caulk not split."),
        ("Caulk at cabinet connections", "Where the counter meets the backsplash and cabinets meet the wall."),
        ("No broken or sagging shelves", "Press on each shelf. Sagging or water-swollen?"),
        ("Drawers slide easily", "Pull every drawer all the way out and back in."),
        ("Cabinet doors close and align", "Check hinges, knobs and pulls are all there and tight."),
        ("Countertop undamaged", "Burns, deep cuts, lifting laminate or open seams."),
    ]},

    {"id": "bath", "zone": "Interior", "name": "Bathroom", "repeat": "bathrooms", "items": [
        ("Toilet seat", "Seat and lid present, not cracked, bolts tight so it doesn't slide."),
        ("Toilet working & flapper good", "Flush it. Does it refill and shut off, or keep running?"),
        ("Toilet base solid — no rocking", "Grab the bowl and rock it gently. Movement means a bad wax ring and possible floor damage."),
        ("Sink stopper working", "Fill the sink and see whether it holds."),
        ("No leaky pipes — check under sink", "Open the cabinet, run water, and feel the trap and supply lines with a dry hand."),
        ("Tub stopper works", "Fill a few inches and watch whether it drains on its own."),
        ("Hot & cold water at sink", "Run both. Hot should get hot within a minute."),
        ("Hot & cold water at tub / shower", "Same test at the tub."),
        ("Tub / shower drains quickly", "Standing water after a minute means a slow drain."),
        ("Aerator clean", "Weak or spitting flow means the aerator needs cleaning."),
        ("Shower head", "Secure, not dripping, spray pattern even and not crusted over."),
        ("Sink not damaged", "Chips, cracks, staining or rust."),
        ("Pop-ups, screens & stoppers present", "All the small drain parts actually there?"),
        ("Cabinet shelves not broken or sagging", "Look under the sink for water damage and swelling."),
        ("Tile & flooring", "Check the grout lines and the floor around the toilet base for soft spots."),
        ("Lights & fixtures (all work & have bulbs)", "Every bulb lit, globes present, vanity light secure to the wall."),
        ("Exhaust fan works", "Turn it on and hold a tissue to the grille — it should hold against it. Listen for rattling."),
        ("Cabinets & drawers work", "Doors close and drawers slide."),
        ("Shower rod & ends", "Rod up, both end caps on, not sliding down."),
        ("Door stop", "Stop present so the knob doesn't hit the wall."),
        ("Medicine cabinet", "Door, hinges, shelves and mirror all sound?"),
        ("Mirror(s)", "Cracked, de-silvered (black creeping in at the edges) or loose?"),
        ("Linen closet shelves", "Level and supported."),
        ("Caulking — remove old & re-caulk if needed", "Around the tub, shower and sink. Moldy or split caulk gets replaced, not covered over."),
        ("Shower walls grouted", "Missing or crumbling grout lets water behind the wall. Flag it."),
        ("Door lock works", "Privacy lock turns and releases, and can still be opened from outside in an emergency."),
        ("Toilet paper holder securely attached", "Give it a tug."),
        ("Toilet paper roller", "Is the bar itself there?"),
        ("Towel bar(s) securely attached", "Pull on it — loose anchors pull straight out of drywall."),
        ("Receptacle is GFCI and trips correctly", "Press TEST then RESET. If it doesn't trip, flag it — this is a safety item."),
    ]},

    {"id": "bed", "zone": "Interior", "name": "Bedroom", "repeat": "bedrooms", "items": [
        ("Lights & fixtures", "Switch on. Bulbs working; a ceiling fan should run all speeds without wobbling."),
        ("Screens", "Screen on every window, no holes."),
        ("Closet poles", "Pole present and seated in both brackets. Push up on it."),
        ("Closet shelves", "Level, not sagging or pulled loose from the wall."),
        ("Door stop", "Stop present behind the door."),
        ("All windows open and stay open", "Open and close every window. It should stay up on its own."),
        ("Window locks", "Each window latches. Missing latches are a security and code issue."),
        ("Receptacle & switch covers installed", "Every outlet and switch has a cover plate."),
        ("Blinds installed and in good condition", "Raise and lower each one. Bent slats or a missing wand?"),
        ("Working smoke detector", "Press the test button and listen for the alarm."),
        ("No water spots", "Look at the ceiling and the wall under each window for brown staining."),
        ("All nails / wall anchors removed", "Run your eye along every wall for nails, screws and plastic anchors."),
        ("Sheetrock repaired / holes patched", "Patches should be sanded flush and painted, not just spackled white."),
        ("Closet door works", "Bi-folds and sliders on track and not rubbing."),
    ]},

    {"id": "laundry", "zone": "Interior", "name": "Washer / Dryer Room", "when": "laundry", "items": [
        ("Washer & dryer connections", "Hot and cold valves present, turn freely and don't drip. Drain standpipe in place."),
        ("Dryer vent clear", "Pull the vent hose off. Look for lint packed in the duct or a crushed hose."),
        ("Dryer outlet / gas connection correct", "Confirm it matches the dryer type the unit is set up for."),
        ("Shelving", "Shelf present and anchored."),
        ("Doors", "Door or bi-fold opens and closes on its track."),
        ("Flooring", "Check under and behind for old water stains or soft spots."),
    ]},

    {"id": "safety", "zone": "Interior", "name": "Safety", "items": [
        ("Smoke alarm present on each floor & working", "One per floor minimum. Press the test button on each and listen."),
        ("Smoke alarm present in each bedroom", "Every bedroom needs its own. Test each one."),
        ("CO alarm present on each level", "Required where there's gas, a fireplace or an attached garage. Press test."),
        ("Alarm batteries fresh / units not expired", "Look at the date stamped on the back. Smoke alarms expire at 10 years."),
        ("Handrail present & secure for more than 3 steps", "Any stair run over 3 steps needs a rail. Grab it and pull — no wobble."),
        ("Extinguisher present & fully charged", "The gauge needle should sit in the green."),
        ("All switches & receptacles have covers", "Walk every room. A missing or cracked cover plate is a flag."),
        ("Electrical panel labeled and accessible", "Breakers labeled and nothing stacked in front of the panel."),
    ]},

    {"id": "hvac", "zone": "Interior", "name": "Heating & Cooling Systems", "items": [
        ("Check & change filter", "Pull the filter out. Write the size down. Dirty or wrong size is a flag."),
        ("Thermostat not loose or broken", "Secure to the wall, screen readable, buttons respond."),
        ("Check / clean evaporator & drain lines", "Indoor coil area clean, no slime or clog in the drain line."),
        ("Clean drain lines & check pan", "The pan under the air handler should be dry, with no rust or standing water."),
        ("Heat works", "Set it to heat and feel the vents. Give it a few minutes."),
        ("A/C works", "Set it to cool and feel the vents. Wait about 10 minutes before judging it."),
        ("Check electrical connections", "The disconnect box at the outside unit is present and closed up."),
        ("Blower wheel alignment & tightness", "Listen for rattle or vibration when the blower runs."),
        ("Covers tight at evaporator / drain", "Access panels screwed back on, not just leaning in place."),
        ("Air returns, registers & covers", "Every register and return has its grille, and none are painted shut."),
        ("Clean condenser, blade turns freely", "Outside unit clear of leaves and grass; the fan spins freely by hand with the power off."),
        ("Covers & line insulation in place", "Insulation on the copper line set, not cracked or missing."),
    ]},

    {"id": "water_heater", "zone": "Interior", "name": "Water Heater", "items": [
        ("Check for leaks", "Look at the top connections and at the floor around the base."),
        ("Connections tight / pan / no rust", "Drip pan in place, no rust streaks running down the tank."),
        ("Correct thermostat setting", "120°F is the target. Higher than that is a scald risk."),
        ("Check for operation", "Run hot water at the nearest fixture and confirm it gets hot and stays hot."),
        ("T&P relief valve and discharge pipe present", "There should be a pipe running from the valve down toward the floor."),
    ]},

    {"id": "carpet", "zone": "Interior", "name": "Carpet", "when": "carpet", "items": [
        ("Seams & spots", "Walk the seams. Look for staining, pet damage and burns."),
        ("Baseboard", "Attached, caulked and not scuffed along the carpet line."),
        ("Carpet needs replacement", "Your call — is this cleanable, or does it need replacing? Flag it if it needs replacing."),
        ("Carpet cleaned (if not replaced)", "Has it actually been professionally cleaned for this turn?"),
        ("Tack strips or Z-bar", "Check thresholds and edges for exposed tack strip — that's a safety issue."),
        ("Padding sound, no ripples", "Walk it barefoot-flat. Ripples and crunching mean the pad is gone."),
    ]},

    {"id": "paint", "zone": "Interior", "name": "Paint, Sheetrock, Moldings & Other", "items": [
        ("All nails / wall anchors removed", "Whole unit, every room."),
        ("Sheetrock repaired / holes patched", "Patches sanded flush — corners and doorways included."),
        ("Walls repainted or touched up", "Does the touch-up blend, or does the whole wall need a coat?"),
        ("Hardware & other fixtures", "Knobs, handles, switch plates and registers all present and matching."),
        ("Ceilings painted if necessary", "Look for stains, cobwebs and roller marks."),
        ("Trim & doors painted if necessary", "Baseboards, casings and door faces."),
        ("Interior doors operate and latch", "Walk through every interior door — rubbing, missing stops, loose knobs."),
    ]},

    # ---------------- EXTERIOR ----------------
    {"id": "utility", "zone": "Exterior", "name": "Outside Utility Room", "when": "utility", "items": [
        ("Condition of doors", "Opens, closes, latches and locks."),
        ("Shelf", "Present and solid."),
        ("Paint / sheetrock", "Any holes, water stains or peeling?"),
    ]},

    {"id": "patio", "zone": "Exterior", "name": "Patio or Deck", "when": "patio", "items": [
        ("Patio light / globe is working", "Flip the switch. Bulb and globe both present?"),
        ("Paint is clean and in good shape", "Look for peeling, mildew and bare wood."),
        ("Hand rails are sturdy and free of rot", "Push on each rail. Poke suspect spots — soft wood is rot."),
        ("Decking boards sound, no protruding nails", "Walk the whole deck. Springy boards and popped nails both get flagged."),
        ("Steps solid and even", "No cracked stringers or wobbling treads."),
    ]},

    {"id": "structures", "zone": "Exterior", "name": "Exterior Structures, Garage & Crawlspace", "items": [
        ("Gutters are clean and clear", "Look for plants growing out of them, or overflow staining down the siding."),
        ("Downspouts drain away from the foundation", "Extension present and pointed away, not dumping right at the wall."),
        ("Windows are in good shape / not broken", "Walk the outside. Cracked panes, fogged double panes, rotten sills."),
        ("Roof is in good condition", "From the ground: missing or lifted shingles, sagging lines, debris."),
        ("All exterior lights are operable", "Front, back, any flood light and the post light."),
        ("Siding and trim sound", "Loose boards, holes, cracked vinyl, and wasp nests in the corners."),
        ("Soffits & fascia clean, free of rot and flaking paint", "Look up along the roof edge. Dark streaks or holes mean rot or animals getting in."),
        ("Shed / storage area clean and in good shape", "Door latches, roof sound, nothing left inside.", "shed"),
        ("Basement / garage broom-swept, free of trash and belongings", "Nothing left behind, floor swept.", "garage"),
        ("Garage door opens, closes and auto-reverses", "Run the opener, then block the beam or lay something in the path — it must reverse.", "garage"),
        ("Crawlspace free of musty odors and standing water", "Open the access and smell it. Damp or musty means a moisture problem — flag it.", "crawlspace"),
        ("Crawlspace vents and access door secure", "Screens intact, door latched so animals stay out.", "crawlspace"),
    ]},

    {"id": "grounds", "zone": "Exterior", "name": "Grounds", "items": [
        ("Lawn is cut and maintained", "Cut, edged, and no bare dirt patches out at the street."),
        ("No dead trees or limbs near structures", "Look up for dead limbs hanging over the roof or driveway."),
        ("Mailbox & house numbers are in good shape", "Box closes, post is straight, numbers readable from the street."),
        ("Driveway & walkways clean and in good shape", "Oil stains, cracks and trip hazards."),
        ("Fences & gates are in good shape", "Walk the line. Leaning panels, missing boards, gates that won't latch.", "fence"),
        ("Bushes & shrubs are pruned", "Cut back off the siding and away from the windows."),
        ("Flower beds weeded, fresh mulch / pine needles", "Beds defined, weeded and freshly topped."),
        ("Grounds free of trash, debris and belongings", "Including behind the shed and under the deck."),
    ]},
]


def _mk_items(sec_id, raw, profile):
    out = []
    for i, entry in enumerate(raw):
        label, hint = entry[0], entry[1]
        cond = entry[2] if len(entry) > 2 else None
        if cond and not profile.get(cond, PROFILE_DEFAULTS.get(cond)):
            continue
        out.append({"key": "%s:%d" % (sec_id, i), "label": label, "hint": hint})
    return out


def build(profile=None):
    """Return the concrete ordered section list for one property."""
    p = dict(PROFILE_DEFAULTS)
    p.update(profile or {})
    out = []
    for sec in SECTIONS:
        when = sec.get("when")
        if when and not p.get(when):
            continue
        rep = sec.get("repeat")
        if rep:
            try:
                n = int(p.get(rep, PROFILE_DEFAULTS.get(rep, 1)))
            except (TypeError, ValueError):
                n = 1
            n = max(0, min(n, 6))
            for k in range(1, n + 1):
                sid = "%s%d" % (sec["id"], k)
                out.append({"id": sid, "zone": sec["zone"],
                            "name": "%s %d" % (sec["name"], k) if n > 1 else sec["name"],
                            "items": _mk_items(sid, sec["items"], p)})
        else:
            out.append({"id": sec["id"], "zone": sec["zone"], "name": sec["name"],
                        "items": _mk_items(sec["id"], sec["items"], p)})
    return [s for s in out if s["items"]]


def total_items(sections):
    return sum(len(s["items"]) for s in sections)
