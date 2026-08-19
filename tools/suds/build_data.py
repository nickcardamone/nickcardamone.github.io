#!/usr/bin/env python3
"""Build the SUDS measures hierarchy JSON consumed by /suds-measures.

Source is the joined dataset exported from the original Shiny app
(`source-joined2.csv`). Only rows marked review == "Include" carry a construct
and psychometric ratings, so those are the ones that make it into the
substance -> construct -> measure hierarchy.

Usage:  python3 tools/suds/build_data.py
"""

import csv
import json
import os
import re
from collections import OrderedDict
from urllib.parse import quote_plus

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SOURCE = os.path.join(HERE, "source-joined2.csv")
TARGET = os.path.join(REPO, "assets", "data", "suds-measures.json")

# The source spells this "Cannabanoid"; correct it for the public site.
SUBSTANCE_FIXES = {"Cannabanoid": "Cannabinoid"}

# Order substances deliberately rather than by size, so the layout is stable
# when the underlying data is refreshed.
SUBSTANCE_ORDER = [
    "Alcohol",
    "Nicotine",
    "Cannabinoid",
    "Opioid",
    "Stimulant",
    "Benzodiazepine",
    "General",
    "Treatment Related",
]

CONSTRUCT_ORDER = [
    "Use",
    "Severity",
    "Consequences",
    "Withdrawal",
    "Urges",
    "Expectancies",
    "Motives",
    "Self-Efficacy",
    "Recovery",
]

RATING_TIER = {"Adequate": 1, "Good": 2, "Excellent": 3}

VALIDITY_NAMES = {
    "CONCUR": "Concurrent",
    "CONVERG": "Convergent",
    "DIVERG": "Discriminant",
    "PREDICT": "Predictive",
    "CONSTRUCT": "Construct",
    "CRITERION": "Criterion",
}

CONSTRUCT_BLURBS = {
    "Use": "Quantity, frequency, and pattern of consumption.",
    "Severity": "How entrenched the disorder is — dependence and problem severity.",
    "Consequences": "Harms and negative outcomes that follow from use.",
    "Withdrawal": "Symptoms experienced on cessation or reduction.",
    "Urges": "Craving and momentary desire to use.",
    "Expectancies": "What a person believes the substance will do for them.",
    "Motives": "Reasons a person gives for using.",
    "Self-Efficacy": "Confidence in the ability to abstain or cut back.",
    "Recovery": "Progress, readiness, and change over the course of treatment.",
}


def clean(value):
    """Normalise a CSV cell; R wrote literal 'NA' strings for missing data."""
    text = (value or "").strip()
    return "" if text in ("NA", "N/A", "#N/A") else text


def split_list(value):
    return [part.strip() for part in value.split(",") if part.strip()]


def scholar_url(name):
    return "https://scholar.google.com/scholar?q=" + quote_plus('"%s"' % name)


def sort_key(value, ordering):
    return ordering.index(value) if value in ordering else len(ordering)


def build_measure(row):
    name = clean(row.get("Name.y"))
    constructs = [c for c in split_list(clean(row.get("construct")))]
    validity = [
        VALIDITY_NAMES.get(code, code.title())
        for code in split_list(clean(row.get("validity")))
    ]
    treatment_sensitivity = clean(row.get("ts"))
    accessible = clean(row.get("Accessibility")) == "Yes"
    rating = clean(row.get("rating"))

    measure = OrderedDict()
    measure["abbr"] = clean(row.get("Abbreviation.y")) or "—"
    measure["name"] = name
    measure["items"] = int(clean(row.get("Items")) or 0)
    measure["rating"] = rating
    measure["tier"] = RATING_TIER.get(rating, 0)
    measure["constructs"] = constructs
    measure["accessible"] = accessible
    measure["accessType"] = clean(row.get("access_type"))
    measure["link"] = clean(row.get("link"))
    measure["scholar"] = scholar_url(name)
    measure["source"] = clean(row.get("Report"))
    measure["psychometrics"] = OrderedDict(
        [
            ("norms", clean(row.get("norms"))),
            ("internalConsistency", clean(row.get("internal_cons"))),
            ("testRetest", clean(row.get("test_retest"))),
            ("validity", validity),
            (
                "treatmentSensitivity",
                True
                if treatment_sensitivity == "X"
                else (False if treatment_sensitivity else None),
            ),
        ]
    )
    return measure


def main():
    with open(SOURCE, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    included = [r for r in rows if clean(r.get("review")) == "Include"]
    excluded = [r for r in rows if clean(r.get("review")) == "Exclude"]

    # substance -> construct -> [measure]
    tree = OrderedDict()
    for row in included:
        substance = clean(row.get("Category.y"))
        substance = SUBSTANCE_FIXES.get(substance, substance)
        measure = build_measure(row)
        # A handful of measures span several constructs; file each under its
        # first-listed (primary) construct and surface the rest in the detail
        # panel, so every measure appears exactly once in the hierarchy.
        primary = measure["constructs"][0] if measure["constructs"] else "Other"
        tree.setdefault(substance, OrderedDict()).setdefault(primary, []).append(measure)

    substances = []
    for substance in sorted(tree, key=lambda s: sort_key(s, SUBSTANCE_ORDER)):
        constructs = []
        for construct in sorted(tree[substance], key=lambda c: sort_key(c, CONSTRUCT_ORDER)):
            measures = sorted(
                tree[substance][construct],
                key=lambda m: (-m["tier"], m["items"], m["abbr"]),
            )
            constructs.append(
                OrderedDict(
                    [
                        ("name", construct),
                        ("blurb", CONSTRUCT_BLURBS.get(construct, "")),
                        ("count", len(measures)),
                        ("measures", measures),
                    ]
                )
            )
        substances.append(
            OrderedDict(
                [
                    ("name", substance),
                    ("count", sum(c["count"] for c in constructs)),
                    ("constructs", constructs),
                ]
            )
        )

    exclusion_reasons = OrderedDict()
    for row in excluded:
        reason = clean(row.get("exclusion_reason")) or "Unspecified"
        exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1

    payload = OrderedDict(
        [
            (
                "meta",
                OrderedDict(
                    [
                        ("searched", "Summer–Fall 2021"),
                        ("screened", len(included) + len(excluded)),
                        ("included", len(included)),
                        ("excluded", len(excluded)),
                        (
                            "exclusionReasons",
                            OrderedDict(
                                sorted(
                                    exclusion_reasons.items(),
                                    key=lambda kv: -kv[1],
                                )
                            ),
                        ),
                        ("constructOrder", CONSTRUCT_ORDER),
                    ]
                ),
            ),
            ("substances", substances),
        ]
    )

    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    with open(TARGET, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)
        handle.write("\n")

    print("wrote %s" % os.path.relpath(TARGET, REPO))
    print(
        "  %d measures across %d substances / %d construct groups"
        % (
            payload["meta"]["included"],
            len(substances),
            sum(len(s["constructs"]) for s in substances),
        )
    )
    for substance in substances:
        print(
            "  %-18s %2d  %s"
            % (
                substance["name"],
                substance["count"],
                ", ".join(
                    "%s(%d)" % (c["name"], c["count"]) for c in substance["constructs"]
                ),
            )
        )


if __name__ == "__main__":
    main()
