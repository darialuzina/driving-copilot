from __future__ import annotations

# Single source of truth for the CBR competency matrix (spec section 4).
# Imported by the Alembic migration (to seed) and by tests (to set up fixtures).

SKILLS: list[dict[str, object]] = [
    # 1. Vehicle control (bediening)
    {
        "category": "Vehicle control",
        "name": "pulling away & stopping",
        "name_nl": "wegrijden/stoppen",
    },
    {"category": "Vehicle control", "name": "gear use & clutch control", "name_nl": "schakelen"},
    {"category": "Vehicle control", "name": "steering technique", "name_nl": "stuurtechniek"},
    {
        "category": "Vehicle control",
        "name": "dashboard & controls knowledge",
        "name_nl": "voertuigkennis",
    },
    # 2. Observation (kijkgedrag)
    {"category": "Observation", "name": "mirror routine", "name_nl": "spiegels"},
    {"category": "Observation", "name": "blind spot checks", "name_nl": "dode hoek"},
    {"category": "Observation", "name": "scanning at speed", "name_nl": "kijktechniek"},
    # 3. Intersections (kruispunten)
    {"category": "Intersections", "name": "priority rules", "name_nl": "voorrang"},
    {"category": "Intersections", "name": "roundabouts", "name_nl": "rotondes"},
    {"category": "Intersections", "name": "left turns", "name_nl": "linksaf"},
    {"category": "Intersections", "name": "traffic lights", "name_nl": "verkeerslichten"},
    # 4. Highway (in-/uitvoegen)
    {"category": "Highway", "name": "merging", "name_nl": "invoegen"},
    {"category": "Highway", "name": "exiting", "name_nl": "uitvoegen"},
    {"category": "Highway", "name": "lane changes & overtaking", "name_nl": "inhalen/wisselen"},
    {"category": "Highway", "name": "speed adaptation", "name_nl": "snelheid aanpassen"},
    # 5. Special maneuvers (bijzondere verrichtingen)
    {"category": "Special maneuvers", "name": "parallel parking", "name_nl": "fileparkeren"},
    {
        "category": "Special maneuvers",
        "name": "bay parking forward/reverse",
        "name_nl": "parkeervak",
    },
    {
        "category": "Special maneuvers",
        "name": "turning around / three-point turn",
        "name_nl": "omkeren",
    },
    {"category": "Special maneuvers", "name": "reversing in a curve", "name_nl": "achteruit bocht"},
    {"category": "Special maneuvers", "name": "hill start", "name_nl": "hellingproef"},
    {"category": "Special maneuvers", "name": "stopping assignment", "name_nl": "stopopdracht"},
    # 6. Independent driving (zelfstandig rijden)
    {"category": "Independent driving", "name": "navigation-led driving", "name_nl": "navigatie"},
    {"category": "Independent driving", "name": "route signs", "name_nl": "borden volgen"},
    {"category": "Independent driving", "name": "cluster assignments", "name_nl": "clusterritten"},
    # 7. Attitude & environment (rijstijl)
    {"category": "Attitude & environment", "name": "eco driving", "name_nl": "milieubewust"},
    {
        "category": "Attitude & environment",
        "name": "anticipating other road users",
        "name_nl": "anticiperen",
    },
    {
        "category": "Attitude & environment",
        "name": "special road sections",
        "name_nl": "bijzondere weggedeelten",
    },
]
