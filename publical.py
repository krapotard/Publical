#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publical.py — Publical: generates a French semester desk calendar (the kind
traditionally handed out as promotional material / "sous-main publicitaire"),
front and back side, six months each, one column per month and one text line
per day (weekday initial, date, name day / public holiday / note space), as
SVG ready to open in Inkscape.

This engine is specific to France: public holidays, name days ("fêtes du
jour"/saints) and school holiday zones (A/B/C) all follow French rules and
calendars. All GUI labels, CLI help text and generated calendar content are
in French, since the tool targets French users; these code comments and
docstrings are in English for reviewers.

No dependency: Python 3.8+ is enough.

Two ways to use it:
  1) With no argument: the script asks questions one by one (year, name days,
     public holidays, colors…)
       python3 publical.py
  2) On the command line, with options (see --help):
       python3 publical.py 2027
       python3 publical.py 2027 --format A3 --couleur rouge --titre "Ma structure"
       python3 publical.py 2027 --sans-saints --sans-feries     # blank lines for notes
       python3 publical.py 2027 --couleur "#1f3a5f" --couleur-feries "#c8102e" --couleur-weekend "#e6eef7"
       python3 publical.py 2027 --semaines --orientation portrait

Output: calendrier_2027_S1.svg (January–June) and calendrier_2027_S2.svg (July–December).
For a PDF: inkscape calendrier_2027_S1.svg --export-type=pdf

Events file (--evenements fichier.json), grouped in colored categories, e.g.:
  {
    "Association": {"couleur": "#1f7a8c", "dates": {"2027-06-23": "Assemblée générale"}},
    "Féminisme":   {"couleur": "#7b3fa0", "dates": {"03-08": "Lutte pour les droits des femmes"}}
  }
Category names are free text; without "couleur", a color is assigned automatically.
Dates: YYYY-MM-DD (once) or MM-DD (every year). The simple format {"2027-03-15": "AG"}
is still accepted.

Data source: name days ("fêtes du jour") from the GitHub project
theofidry/ephemeris, cleaned up (mobile/astronomical dates and one duplicate
removed: Feb 21, May 31, Jun 21, Sep 23, Dec 21; Mar 25 replaced with
"Annonciation"). PROOFREAD before printing. Use --evenements to fix or add entries.
Public holidays: mainland France (excluding Alsace-Moselle), computed automatically.
School holidays: zones A, B, C as color bars, next to the dates or against the
month's right edge (2026-2028 dates built in). Month columns on a white
background, optional border.
Bridge days ("ponts": a single working day between a holiday and a non-working
day) and payday markers (money-bag pictogram).
Events in colored categories via a JSON file (--evenements option).
"""
import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from xml.sax.saxutils import escape

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
INITIALES = "LMMJVSD"  # Monday -> Sunday (weekday initials, in French)
FORMATS = {"A3": (420, 297), "A4": (297, 210), "A5": (210, 148), "A6": (148, 105)}  # landscape, in mm
POLICE = "DejaVu Sans, Liberation Sans, Arial, sans-serif"
COULEURS_NOMMEES = {"rouge": "#c8102e", "bleu": "#1f3a5f", "vert": "#2e7d32", "orange": "#e07b00",
                    "violet": "#6a1b9a", "gris": "#555555", "noir": "#111111"}
ZONE_COULEURS = {"A": "#e0201b", "B": "#1f4fbf", "C": "#f6c700"}  # red, blue, yellow
# French school holidays (mainland France), format "start Saturday - end-of-holiday Monday".
# Source: Service-Public.fr fact sheet F31952 (checked 2026-09-02): decrees of 2025-10-22
# for 2026-2027, and of 2026-07-21 for 2027-2028.
VACANCES_DEFAUT = {
    "toussaint": "17/10/2026-02/11/2026; 23/10/2027-08/11/2027",
    "noel": "19/12/2026-04/01/2027; 18/12/2027-03/01/2028",
    "hiver_a": "13/02/2027-01/03/2027; 19/02/2028-06/03/2028",
    "hiver_b": "20/02/2027-08/03/2027; 05/02/2028-21/02/2028",
    "hiver_c": "06/02/2027-22/02/2027; 12/02/2028-28/02/2028",
    "printemps_a": "10/04/2027-26/04/2027; 22/04/2028-09/05/2028",
    "printemps_b": "17/04/2027-03/05/2027; 08/04/2028-24/04/2028",
    "printemps_c": "03/04/2027-19/04/2027; 15/04/2028-02/05/2028",
    "ete": "03/07/2027-02/09/2027; 04/07/2028",
}
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
# Colors auto-assigned to event categories that have no "couleur" (in file order)
PALETTE_CATEGORIES = ["#7b3fa0", "#c8102e", "#1f7a8c", "#e07b00", "#2e7d32", "#b5179e", "#4361ee", "#8d6e63"]
CLE_DATE_RE = re.compile(r"^(\d{4}-)?\d{2}-\d{2}$")
# Dates where the name-day source lists a public holiday rather than a saint
FERIES_FIXES = {"01-01", "05-01", "05-08", "07-14", "08-15", "11-01", "11-11", "12-25"}

SAINTS = {
    "01-01": "Jour de l'An", "01-02": "Basile", "01-03": "Geneviève",
    "01-04": "Odilon", "01-05": "Édouard", "01-06": "Mélaine",
    "01-07": "Raymond", "01-08": "Lucien", "01-09": "Alix",
    "01-10": "Guillaume", "01-11": "Pauline", "01-12": "Tatiana",
    "01-13": "Yvette", "01-14": "Nina", "01-15": "Rémi",
    "01-16": "Marcel", "01-17": "Roseline", "01-18": "Prisca",
    "01-19": "Marius", "01-20": "Sébastien", "01-21": "Agnès",
    "01-22": "Vincent", "01-23": "Barnard", "01-24": "François de Sales",
    "01-25": "Conversion de Paul", "01-26": "Paule", "01-27": "Angèle",
    "01-28": "Thomas d'Aquin", "01-29": "Gildas", "01-30": "Martine",
    "01-31": "Marcelle", "02-01": "Ella", "02-02": "Chandeleur",
    "02-03": "Blaise", "02-04": "Véronique", "02-05": "Agathe",
    "02-06": "Gaston", "02-07": "Eugénie", "02-08": "Jacqueline",
    "02-09": "Apolline", "02-10": "Arnaud", "02-11": "Notre Dame de Lourdes",
    "02-12": "Félix", "02-13": "Béatrice", "02-14": "Valentin",
    "02-15": "Claude", "02-16": "Julienne", "02-17": "Alexis",
    "02-18": "Bernadette", "02-19": "Gabin", "02-20": "Aimée",
    "02-22": "Isabelle", "02-23": "Lazare", "02-24": "Modeste",
    "02-25": "Roméo", "02-26": "Nestor", "02-27": "Honorine",
    "02-28": "Romain", "02-29": "Auguste", "03-01": "Aubin",
    "03-02": "Charles le Bon", "03-03": "Guénolé", "03-04": "Casimir",
    "03-05": "Olive", "03-06": "Colette", "03-07": "Félicité",
    "03-08": "Jean de Dieu", "03-09": "Françoise", "03-10": "Vivien",
    "03-11": "Rosine", "03-12": "Justine", "03-13": "Rodrigue",
    "03-14": "Mathilde", "03-15": "Louise", "03-16": "Bénédicte",
    "03-17": "Patrice", "03-18": "Cyrille", "03-19": "Joseph",
    "03-20": "Herbert", "03-21": "Clémence", "03-22": "Léa",
    "03-23": "Victorien", "03-24": "Karine", "03-25": "Annonciation",
    "03-26": "Larissa", "03-27": "Habib", "03-28": "Gontran",
    "03-29": "Gwladys", "03-30": "Amédée", "03-31": "Benjamin",
    "04-01": "Hugues", "04-02": "Sandrine", "04-03": "Richard",
    "04-04": "Isidore", "04-05": "Irène", "04-06": "Marcellin",
    "04-07": "Jean-Baptiste de la Salle", "04-08": "Julie", "04-09": "Gautier",
    "04-10": "Fulbert", "04-11": "Stanislas", "04-12": "Jules",
    "04-13": "Ida", "04-14": "Maxime", "04-15": "Paterne",
    "04-16": "Benoît-Joseph", "04-17": "Anicet", "04-18": "Parfait",
    "04-19": "Emma", "04-20": "Odette", "04-21": "Anselme",
    "04-22": "Alexandre", "04-23": "Georges", "04-24": "Fidèle",
    "04-25": "Marc", "04-26": "Alida", "04-27": "Zita",
    "04-28": "Valérie", "04-29": "Catherine de Sienne", "04-30": "Robert",
    "05-01": "Fête du travail", "05-02": "Boris", "05-03": "Philippe",
    "05-04": "Sylvain", "05-05": "Judith", "05-06": "Prudence",
    "05-07": "Gisèle", "05-08": "Armistice de 1945", "05-09": "Pacôme",
    "05-10": "Solange", "05-11": "Estelle", "05-12": "Achille",
    "05-13": "Rolande", "05-14": "Matthias", "05-15": "Denise",
    "05-16": "Honoré", "05-17": "Pascal", "05-18": "Éric",
    "05-19": "Yves", "05-20": "Bernardin", "05-21": "Constantin",
    "05-22": "Émile", "05-23": "Didier", "05-24": "Donatien",
    "05-25": "Sophie", "05-26": "Bérenger", "05-27": "Augustin",
    "05-28": "Germain", "05-29": "Aymar", "05-30": "Ferdinand",
    "06-01": "Justin", "06-02": "Blandine", "06-03": "Kévin",
    "06-04": "Clotilde", "06-05": "Igor", "06-06": "Norbert",
    "06-07": "Gilbert", "06-08": "Médard", "06-09": "Diane",
    "06-10": "Landry", "06-11": "Barnabé", "06-12": "Guy",
    "06-13": "Antoine de Padoue", "06-14": "Élisée", "06-15": "Germaine",
    "06-16": "Jean-François Régis", "06-17": "Hervé", "06-18": "Léonce",
    "06-19": "Romuald", "06-20": "Silvère", "06-22": "Alban",
    "06-23": "Audrey", "06-24": "Jean-Baptiste", "06-25": "Prosper",
    "06-26": "Anthelme", "06-27": "Fernand", "06-28": "Irénée",
    "06-29": "Pierre", "06-30": "Martial", "07-01": "Thierry",
    "07-02": "Martinien", "07-03": "Thomas", "07-04": "Florent",
    "07-05": "Antoine", "07-06": "Mariette", "07-07": "Raoul",
    "07-08": "Thibault", "07-09": "Amandine", "07-10": "Ulrich",
    "07-11": "Benoît", "07-12": "Olivier", "07-13": "Henri",
    "07-14": "Fête nationale", "07-15": "Donald", "07-16": "N.-D. du Mont-Carmel",
    "07-17": "Charlotte", "07-18": "Frédéric", "07-19": "Arsène",
    "07-20": "Marina", "07-21": "Victor", "07-22": "Marie-Madeleine",
    "07-23": "Brigitte", "07-24": "Christine", "07-25": "Jacques",
    "07-26": "Anne", "07-27": "Nathalie", "07-28": "Samson",
    "07-29": "Marthe", "07-30": "Juliette", "07-31": "Ignace de Loyola",
    "08-01": "Alphonse", "08-02": "Julien Eymard", "08-03": "Lydie",
    "08-04": "Jean-Marie Vianney", "08-05": "Abel", "08-06": "Transfiguration",
    "08-07": "Gaétan", "08-08": "Dominique", "08-09": "Amour",
    "08-10": "Laurent", "08-11": "Claire", "08-12": "Clarisse",
    "08-13": "Hippolyte", "08-14": "Evrard", "08-15": "Assomption",
    "08-16": "Armel", "08-17": "Hyacinthe", "08-18": "Hélène",
    "08-19": "Jean-Eudes", "08-20": "Bernard", "08-21": "Christophe",
    "08-22": "Fabrice", "08-23": "Rose de Lima", "08-24": "Barthélémy",
    "08-25": "Louis", "08-26": "Natacha", "08-27": "Monique",
    "08-28": "Augustin", "08-29": "Sabine", "08-30": "Fiacre",
    "08-31": "Aristide", "09-01": "Gilles", "09-02": "Ingrid",
    "09-03": "Grégoire", "09-04": "Rosalie", "09-05": "Raïssa",
    "09-06": "Bertrand", "09-07": "Reine", "09-08": "Nativité de Marie",
    "09-09": "Alain", "09-10": "Inès", "09-11": "Adelphe",
    "09-12": "Apollinaire", "09-13": "Aimé", "09-14": "Croix glorieuse",
    "09-15": "Roland", "09-16": "Édith", "09-17": "Renaud",
    "09-18": "Nadège", "09-19": "Émilie", "09-20": "Davy",
    "09-21": "Matthieu", "09-22": "Maurice", "09-24": "Thècle",
    "09-25": "Hermann", "09-26": "Côme", "09-27": "Vincent de Paul",
    "09-28": "Venceslas", "09-29": "Michel", "09-30": "Jérôme",
    "10-01": "Thérèse de l'Enfant Jésus", "10-02": "Léger", "10-03": "Gérard",
    "10-04": "François d'Assise", "10-05": "Fleur", "10-06": "Bruno",
    "10-07": "Serge", "10-08": "Pélagie", "10-09": "Denis",
    "10-10": "Ghislain", "10-11": "Firmin", "10-12": "Wilfried",
    "10-13": "Géraud", "10-14": "Juste", "10-15": "Thérèse d'Avila",
    "10-16": "Edwige", "10-17": "Baudoin", "10-18": "Luc",
    "10-19": "René", "10-20": "Adeline", "10-21": "Céline",
    "10-22": "Élodie", "10-23": "Jean de Capistran", "10-24": "Florentin",
    "10-25": "Crépin", "10-26": "Dimitri", "10-27": "Émeline",
    "10-28": "Jude", "10-29": "Narcisse", "10-30": "Bienvenue",
    "10-31": "Quentin", "11-01": "Toussaint", "11-02": "Défunts",
    "11-03": "Hubert", "11-04": "Charles", "11-05": "Sylvie",
    "11-06": "Bertille", "11-07": "Carine", "11-08": "Geoffroy",
    "11-09": "Théodore", "11-10": "Léon", "11-11": "Armistice de 1918",
    "11-12": "Christian", "11-13": "Brice", "11-14": "Sidoine",
    "11-15": "Albert", "11-16": "Marguerite", "11-17": "Élisabeth",
    "11-18": "Aude", "11-19": "Tanguy", "11-20": "Edmond",
    "11-21": "Présentation de Marie", "11-22": "Cécile", "11-23": "Clément",
    "11-24": "Flora", "11-25": "Catherine", "11-26": "Delphine",
    "11-27": "Sévrin", "11-28": "Jacques de la Marche", "11-29": "Saturnin",
    "11-30": "André", "12-01": "Florence", "12-02": "Viviane",
    "12-03": "François-Xavier", "12-04": "Barbara", "12-05": "Gérald",
    "12-06": "Nicolas", "12-07": "Ambroise", "12-08": "Immaculée Conception",
    "12-09": "Pierre Fourier", "12-10": "Romaric", "12-11": "Daniel",
    "12-12": "Jeanne-Françoise de Chantal", "12-13": "Lucie", "12-14": "Odile",
    "12-15": "Ninon", "12-16": "Alice", "12-17": "Gaël",
    "12-18": "Gatien", "12-19": "Urbain", "12-20": "Théophile",
    "12-22": "Françoise-Xavière", "12-23": "Armand", "12-24": "Adèle",
    "12-25": "Noël", "12-26": "Étienne", "12-27": "Jean",
    "12-28": "Innocents", "12-29": "David", "12-30": "Roger",
    "12-31": "Sylvestre",
}


def paques(an):
    """Easter Sunday (Gregorian calendar, Meeus/Jones/Butcher algorithm)."""
    a = an % 19
    b, c = divmod(an, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return date(an, mois, jour + 1)


def jours_feries(an):
    p = paques(an)
    feries = {
        date(an, 1, 1): "Jour de l'An",
        p + timedelta(days=1): "Lundi de Pâques",
        date(an, 5, 1): "Fête du Travail",
        date(an, 5, 8): "Victoire 1945",
        p + timedelta(days=39): "Ascension",
        p + timedelta(days=50): "Lundi de Pentecôte",
        date(an, 7, 14): "Fête nationale",
        date(an, 8, 15): "Assomption",
        date(an, 11, 1): "Toussaint",
        date(an, 11, 11): "Armistice 1918",
        date(an, 12, 25): "Noël",
    }
    return feries


def libelles_speciaux(an):
    """Movable markers shown on the calendar without being public holidays."""
    p = paques(an)
    return {p: "Pâques", p - timedelta(days=46): "Mercredi des Cendres"}


def parse_periodes(texte, nom_champ, debut_seul_autorise=False):
    """"DD/MM/YYYY-DD/MM/YYYY; ..." -> [(start, end)]. A single date (summer) runs until August 31."""
    periodes = []
    for morceau in (m.strip() for m in (texte or "").replace("\n", ";").split(";")):
        if not morceau:
            continue
        dates = []
        for jj, mm, aaaa in DATE_RE.findall(morceau):
            try:
                dates.append(date(int(aaaa), int(mm), int(jj)))
            except ValueError:
                raise ValueError(f"{nom_champ} : date invalide « {jj}/{mm}/{aaaa} »")
        if len(dates) == 2:
            if dates[1] <= dates[0]:
                raise ValueError(f"{nom_champ} : la reprise doit suivre le début ({morceau})")
            periodes.append((dates[0], dates[1]))
        elif len(dates) == 1 and debut_seul_autorise:
            periodes.append((dates[0], date(dates[0].year, 9, 1)))
        else:
            raise ValueError(f"{nom_champ} : « {morceau} » — format attendu JJ/MM/AAAA-JJ/MM/AAAA")
    return periodes


def vacances_par_zone(champs):
    """fields: dict toussaint, noel, ete, hiver_a/b/c, printemps_a/b/c -> {"A": [...], "B": [...], "C": [...]}."""
    communes = []
    for cle, nom in (("toussaint", "Toussaint"), ("noel", "Noël"), ("ete", "Été")):
        communes += parse_periodes(champs.get(cle, ""), nom, debut_seul_autorise=(cle == "ete"))
    resultat = {}
    for z in "ABC":
        resultat[z] = (communes
                       + parse_periodes(champs.get(f"hiver_{z.lower()}", ""), f"Hiver zone {z}")
                       + parse_periodes(champs.get(f"printemps_{z.lower()}", ""), f"Printemps zone {z}"))
    return resultat


def jours_vacances(an, zones, vacances, pont):
    """Set of days of year `an` that are on holiday, per zone (+ Ascension bridge, Thu-Sun, if `pont`)."""
    resultat = {}
    for z in zones:
        jours = set()
        for debut, reprise in vacances.get(z, []):
            d = debut
            while d < reprise:
                if d.year == an:
                    jours.add(d)
                d += timedelta(days=1)
        if pont:
            # Ascension bridge: from Ascension Thursday (Easter + 39 days) to the following Sunday (+42 days)
            for k in range(39, 43):
                jours.add(paques(an) + timedelta(days=k))
        resultat[z] = jours
    return resultat


OUVRES_DEFAUT = {0, 1, 2, 3, 4}  # Monday to Friday (0 = Monday … 6 = Sunday)


def parse_jours_ouvres(texte):
    """"12345" (1 = Monday … 7 = Sunday) -> {0, 1, 2, 3, 4}."""
    chiffres = re.sub(r"[\s,;]", "", texte or "")
    if not chiffres or any(c not in "1234567" for c in chiffres):
        raise ValueError(f"jours travaillés « {texte} » : utiliser les chiffres 1 (lundi) à 7 (dimanche), ex. 12345")
    return {int(c) - 1 for c in chiffres}


def feries_etendus(an):
    """Public holidays for the previous year, this year and the next (for dates near a year boundary)."""
    tous = {}
    for a in (an - 1, an, an + 1):
        tous.update(jours_feries(a))
    return tous


def calcul_ponts(an, ouvres):
    """Bridge days: a single working day between a public holiday and a non-working day (or another
    holiday). E.g. the Monday before a Tuesday holiday, the Friday after a Thursday holiday."""
    feries = feries_etendus(an)

    def travaille(d):
        return d.weekday() in ouvres and d not in feries

    ponts = set()
    d = date(an, 1, 1)
    while d.year == an:
        if travaille(d):
            avant, apres = d - timedelta(days=1), d + timedelta(days=1)
            if not travaille(avant) and not travaille(apres) and (avant in feries or apres in feries):
                ponts.add(d)
        d += timedelta(days=1)
    return ponts


def calcul_paye(an, cfg, ouvres):
    """Payday dates falling within year `an`.
    cfg: {"mode": "fin" | "fixe", "n": 5, "jour": 25, "decalage": "avant" | "apres" | "non", "feries_non_ouvres": True}
      - "fin"  ("end"): the Nth-last working day of the month, counting the month's last day
        (N = 1: the last working day)
      - "fixe" ("fixed"): a given day of the month (the month's last day if it does not exist),
        shifted to the previous/next working day
    """
    feries = feries_etendus(an) if cfg.get("feries_non_ouvres", True) else {}

    def ouvre(d):
        return d.weekday() in ouvres and d not in feries

    mois_a_calculer = [(an - 1, 12)] + [(an, m) for m in range(1, 13)] + [(an + 1, 1)]
    resultat = set()
    for annee, mois in mois_a_calculer:
        dernier = date(annee + (mois == 12), mois % 12 + 1, 1) - timedelta(days=1)
        paye = None
        if cfg.get("mode", "fin") == "fin":
            restants, d = max(1, int(cfg.get("n", 5))), dernier
            for _ in range(70):
                if ouvre(d):
                    restants -= 1
                    if restants == 0:
                        paye = d
                        break
                d -= timedelta(days=1)
        else:
            d = date(annee, mois, min(int(cfg.get("jour", 25)), dernier.day))
            decalage = cfg.get("decalage", "avant")
            if decalage == "non" or ouvre(d):
                paye = d
            else:
                pas = -1 if decalage == "avant" else 1
                for _ in range(70):
                    d += timedelta(days=pas)
                    if ouvre(d):
                        paye = d
                        break
        if paye is not None and paye.year == an:
            resultat.add(paye)
    return resultat


def icone_paye(x, y, h, couleur):
    """"Money bag with €" pictogram (20 x 24 box scaled to height h), top-left corner at (x, y)."""
    k = h / 24.0
    return (f'<g transform="translate({x:.2f},{y:.2f}) scale({k:.4f})">'
            f'<path d="M6.3,6.4 C4.6,3.9 6.2,1.4 8.1,2.6 C8.9,1.1 11.1,1.1 11.9,2.6 C13.8,1.4 15.4,3.9 13.7,6.4 Z" fill="{couleur}"/>'
            f'<path d="M6.2,8.2 C2.1,12 0.7,16.6 2.4,20.1 C3.5,22.5 6.6,23.6 10,23.6 C13.4,23.6 16.5,22.5 17.6,20.1 '
            f'C19.3,16.6 17.9,12 13.8,8.2 Z" fill="{couleur}"/>'
            f'<path d="M5.9,7.3 L14.1,7.3" stroke="#ffffff" stroke-width="0.9" fill="none"/>'
            f'<text x="10" y="19.4" font-size="9.5" font-weight="bold" text-anchor="middle" fill="#ffffff" '
            f'font-family="DejaVu Sans, Liberation Sans, Arial, sans-serif">€</text></g>')


def contraste(couleur):
    """White or black text depending on the brightness of the background (#rrggbb)."""
    r, g, b = (int(couleur[k:k + 2], 16) for k in (1, 3, 5))
    return "#ffffff" if (0.299 * r + 0.587 * g + 0.114 * b) < 150 else "#111111"


def charger_evenements(chemin):
    """Events JSON file -> (evenements, categories).

    Full format: { "Category name": { "couleur": "#7b3fa0", "dates": { "2027-03-08": "Text", "03-28": "Yearly text" } }, ... }
    ("couleur" is optional: a color is then assigned automatically; "dates" can also be omitted,
    with the dates then written directly under the category). The simple format { "2027-03-15": "AG" }
    is still accepted.
    Dates: YYYY-MM-DD (once) or MM-DD (every year). Empty text: the line stays blank.

    evenements: {"YYYY-MM-DD" or "MM-DD": [(text, couleur | None, category | None)]}; categories: [(name, couleur)].
    """
    if not chemin:
        return {}, []
    try:
        with open(chemin, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalide (ligne {e.lineno}, colonne {e.colno}) : {e.msg}. "
                         "Vérifier les virgules entre les éléments et les guillemets.")
    if not isinstance(data, dict):
        raise ValueError("le fichier doit contenir un objet JSON : { ... }")
    evenements, categories = {}, []

    def ajouter(cle, texte, couleur, categorie):
        lieu = f" (catégorie « {categorie} »)" if categorie else ""
        if not CLE_DATE_RE.match(str(cle)):
            raise ValueError(f"date « {cle} » invalide{lieu} : format AAAA-MM-JJ ou MM-JJ")
        if not isinstance(texte, str):
            raise ValueError(f"texte de la date « {cle} »{lieu} : une chaîne de caractères est attendue")
        evenements.setdefault(str(cle), []).append((texte, couleur, categorie))

    for nom, valeur in data.items():
        if isinstance(valeur, str):                    # format simple : "date": "texte"
            ajouter(nom, valeur, None, None)
            continue
        couleur, dates = None, []
        for bloc in (valeur if isinstance(valeur, list) else [valeur]):
            if not isinstance(bloc, dict):
                raise ValueError(f"catégorie « {nom} » : un objet {{date: texte}} est attendu")
            for cle, val in bloc.items():
                if cle.lower() in ("couleur", "color"):
                    try:
                        couleur = couleur_type(str(val))
                    except argparse.ArgumentTypeError as e:
                        raise ValueError(f"catégorie « {nom} » : {e}")
                elif cle.lower() == "dates":
                    if not isinstance(val, dict):
                        raise ValueError(f"catégorie « {nom} » : « dates » doit être un objet {{date: texte}}")
                    dates += list(val.items())
                else:
                    dates.append((cle, val))
        if couleur is None:
            couleur = PALETTE_CATEGORIES[len(categories) % len(PALETTE_CATEGORIES)]
        categories.append((nom, couleur))
        for cle, texte in dates:
            ajouter(cle, texte, couleur, nom)
    return evenements, categories


def evenements_du_jour(d, evenements):
    """Events for a given day: exact date first, then yearly date (MM-DD), in file order."""
    trouves = []
    for cle in (d.isoformat(), d.strftime("%m-%d")):
        trouves += evenements.get(cle, [])
    return trouves


def texte_ligne(d, feries, speciaux, evenements, avec_saints, avec_feries):
    cle_courte = d.strftime("%m-%d")
    evs = evenements_du_jour(d, evenements)
    if evs:
        return " · ".join(texte for texte, _, _ in evs if texte)   # tous vides : ligne vierge
    if d in feries:
        return feries[d]
    if d in speciaux:
        return speciaux[d]
    if not avec_feries and cle_courte in FERIES_FIXES:
        return ""
    if avec_saints:
        return SAINTS.get(cle_courte, "")
    return ""


def couper_en_deux(txt):
    """Split text into two balanced lines, at a space (None if there is no space)."""
    if " " not in txt:
        return None
    milieu, meilleur = len(txt) / 2, None
    for i, c in enumerate(txt):
        if c == " " and (meilleur is None or abs(i - milieu) < abs(meilleur - milieu)):
            meilleur = i
    return txt[:meilleur].rstrip(), txt[meilleur + 1:].lstrip()


def taille_texte(txt, fs, dispo, gras=False):
    """Shrink the font (then compress if needed) so the text fits in the cell."""
    k = 0.64 if gras else 0.56
    largeur = k * fs * len(txt)
    if largeur <= dispo:
        return fs, None
    fs2 = max(fs * dispo / largeur, fs * 0.65)
    if k * fs2 * len(txt) <= dispo:
        return fs2, None
    return fs2, dispo


def face(an, semestre, o):
    W, H = o.dimensions
    s = min(W, H) / 210.0                       # scale relative to A4
    marge, h_titre, h_mois, h_pied, gout = 8 * s, 14 * s, 7 * s, 6 * s, 1.5 * s
    ncol = 6
    largeur_col = (W - 2 * marge - (ncol - 1) * gout) / ncol
    y0 = marge + h_titre + h_mois
    hl = (H - marge - h_pied - y0) / 31.0       # hauteur d'une ligne
    fs = min(hl * 0.52, 3.1 * s)
    x_num = 1.3 * s + 2.85 * fs               # right edge of the day number
    x_lib = x_num + 1.6 * s                   # where the label (name day / note) starts
    accent = o.couleur
    c_ferie = o.couleur_feries or accent
    c_texte = o.couleur_texte
    c_we = o.couleur_weekend
    police = (o.police.replace('"', "'") + ", " + POLICE) if o.police else POLICE
    feries = {} if o.sans_feries else jours_feries(an)
    speciaux = {} if o.sans_feries else libelles_speciaux(an)
    ev, _categories_fichier = charger_evenements(o.evenements)
    categories_vues = {}                      # categories actually present on this side
    m_debut = 1 if semestre == 1 else 7
    zones = list(getattr(o, "zones_vacances", None) or [])
    couleurs_zones = dict(ZONE_COULEURS)
    couleurs_zones.update(getattr(o, "couleurs_zones", None) or {})
    jours_zone = jours_vacances(an, zones, getattr(o, "vacances", None) or {}, getattr(o, "pont_ascension", False))
    bw = 1.1 * s                                            # largeur d'une barre de zone
    reserve = (len(zones) * bw + 0.4 * s) if zones else 0.0  # space reserved on the right of each column
    x_barres = None                                          # None : barres contre le bord droit du mois
    if zones and getattr(o, "position_barres", "dates") == "dates":
        # bars right next to the date; the label (name day / note) starts after them
        x_barres = x_num + 0.9 * s
        x_lib = x_barres + len(zones) * bw + 1.0 * s
        reserve = 0.0

    # working days, bridge days, and paydays
    ouvres = set(getattr(o, "jours_ouvres", None) or OUVRES_DEFAUT)
    ponts_actifs = bool(getattr(o, "ponts", False))
    ponts = calcul_ponts(an, ouvres) if ponts_actifs else set()
    c_pont = getattr(o, "couleur_ponts", None) or "#b6e2a1"
    cfg_paye = getattr(o, "paye", None)
    jours_paye = calcul_paye(an, cfg_paye, ouvres) if cfg_paye else set()
    c_paye = getattr(o, "couleur_paye", None) or "#1b7f3b"

    p = []
    a = p.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W:g} {H:g}">')
    a(f'<g font-family="{police}" fill="{c_texte}">')
    titre_sem = f"{MOIS[m_debut-1].capitalize()} – {MOIS[m_debut+4]} {an}"
    a(f'<text x="{marge:g}" y="{marge + h_titre*0.78:.2f}" font-size="{h_titre*0.7:.2f}" font-weight="bold" fill="{accent}">{escape(titre_sem)}</text>')
    if o.titre:
        a(f'<text x="{W-marge:g}" y="{marge + h_titre*0.78:.2f}" font-size="{h_titre*0.42:.2f}" text-anchor="end" fill="#444444">{escape(o.titre)}</text>')

    for c in range(ncol):
        m = m_debut + c
        x = marge + c * (largeur_col + gout)
        nb_jours = (date(an + (m == 12), m % 12 + 1, 1) - date(an, m, 1)).days
        # month header
        a(f'<rect x="{x:.2f}" y="{marge+h_titre:.2f}" width="{largeur_col:.2f}" height="{h_mois:.2f}" fill="{accent}"/>')
        fs_m = min(h_mois * 0.62, largeur_col * 0.9 / (0.78 * len(MOIS[m - 1])))
        a(f'<text x="{x+largeur_col/2:.2f}" y="{marge+h_titre+h_mois*0.5+fs_m*0.35:.2f}" font-size="{fs_m:.2f}" font-weight="bold" '
          f'text-anchor="middle" fill="#ffffff" letter-spacing="{0.2*s:.2f}">{MOIS[m-1].upper()}</text>')
        # fond blanc de la colonne : le fond du document peut changer sans toucher aux mois
        a(f'<rect x="{x:.2f}" y="{y0:.2f}" width="{largeur_col:.2f}" height="{nb_jours*hl:.2f}" fill="#ffffff"/>')
        for j in range(1, nb_jours + 1):
            d = date(an, m, j)
            y = y0 + (j - 1) * hl
            wd = d.weekday()
            ferie = d in feries
            evs = evenements_du_jour(d, ev)
            c_ev = next((c for _, c, _ in evs if c), None)          # color of the day's first category
            c_txt_ev = contraste(c_ev) if c_ev else None
            for texte_ev, _, cat_ev in evs:
                if cat_ev and texte_ev:
                    categories_vues.setdefault(cat_ev, next(c for t2, c, k in evs if k == cat_ev))
            if c_ev:
                a(f'<rect x="{x:.2f}" y="{y:.2f}" width="{largeur_col:.2f}" height="{hl:.2f}" fill="{c_ev}"/>')
            elif ferie:
                a(f'<rect x="{x:.2f}" y="{y:.2f}" width="{largeur_col:.2f}" height="{hl:.2f}" fill="{c_ferie}" fill-opacity="0.16"/>')
            elif d in ponts:
                a(f'<rect x="{x:.2f}" y="{y:.2f}" width="{largeur_col:.2f}" height="{hl:.2f}" fill="{c_pont}"/>')
            elif wd >= 5 and c_we != "aucune":
                a(f'<rect x="{x:.2f}" y="{y:.2f}" width="{largeur_col:.2f}" height="{hl:.2f}" fill="{c_we}"/>')
            # rules: thin one under each day, heavier one before each Monday
            a(f'<line x1="{x:.2f}" y1="{y+hl:.2f}" x2="{x+largeur_col:.2f}" y2="{y+hl:.2f}" stroke="#999999" stroke-width="{0.12*s:.2f}"/>')
            if wd == 0 and j > 1:
                a(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x+largeur_col:.2f}" y2="{y:.2f}" stroke="#222222" stroke-width="{0.35*s:.2f}"/>')
            couleur = c_txt_ev or (c_ferie if (wd == 6 or ferie) else c_texte)
            base_y = y + hl * 0.5 + fs * 0.35
            a(f'<text x="{x+1.3*s:.2f}" y="{base_y:.2f}" font-size="{fs:.2f}" font-weight="bold" fill="{couleur}">{INITIALES[wd]}</text>')
            a(f'<text x="{x+x_num:.2f}" y="{base_y:.2f}" font-size="{fs:.2f}" font-weight="bold" text-anchor="end" fill="{couleur}">{j}</text>')
            txt = texte_ligne(d, feries, speciaux, ev, not o.sans_saints, not o.sans_feries)
            x_txt = x + x_lib
            dispo = largeur_col - x_lib - 1.0 * s - reserve
            x_droite = x + largeur_col - 1.0 * s - reserve        # bord droit disponible sur la ligne
            if o.semaines and wd == 0:
                dispo -= 5.5 * s
                a(f'<text x="{x_droite:.2f}" y="{base_y:.2f}" font-size="{fs*0.72:.2f}" text-anchor="end" fill="#777777">S{d.isocalendar()[1]}</text>')
                x_droite -= 5.5 * s
            if d in jours_paye:
                h_ic = min(hl * 0.88, 6.0 * s)
                dispo -= h_ic * 20 / 24 + 1.0 * s
                a(icone_paye(x_droite - h_ic * 20 / 24, y + (hl - h_ic) / 2, h_ic, c_paye))
            if txt:
                f2, tl = taille_texte(txt, fs, dispo, ferie or bool(c_ev))
                if c_ev:
                    style = f' font-weight="bold" fill="{c_txt_ev}"'
                else:
                    style = f' font-weight="bold" fill="{c_ferie}"' if ferie else ""
                deux = couper_en_deux(txt) if tl else None
                if deux:
                    # label too long for one line: wrap onto two lines within the cell height
                    k_larg = 0.64 if (ferie or c_ev) else 0.56
                    f3 = min(fs * 0.72, hl * 0.36)
                    largeur_max = k_larg * f3 * max(len(deux[0]), len(deux[1]))
                    if largeur_max > dispo:
                        f3 *= dispo / largeur_max
                    haut = y + (hl - 2 * f3 * 1.05) / 2
                    b1 = haut + f3 * 0.85
                    for k, ligne in enumerate(deux):
                        a(f'<text x="{x_txt:.2f}" y="{b1 + k * f3 * 1.08:.2f}" font-size="{f3:.2f}"{style}>{escape(ligne)}</text>')
                else:
                    extra = f' textLength="{tl:.2f}" lengthAdjust="spacingAndGlyphs"' if tl else ""
                    a(f'<text x="{x_txt:.2f}" y="{base_y:.2f}" font-size="{f2:.2f}"{style}{extra}>{escape(txt)}</text>')
        # school holidays: one vertical bar per zone, on the right of the column
        for i, z in enumerate(zones):
            debut_run = None
            for j in range(1, nb_jours + 2):
                actif = j <= nb_jours and date(an, m, j) in jours_zone[z]
                if actif and debut_run is None:
                    debut_run = j
                elif not actif and debut_run is not None:
                    y1, y2 = y0 + (debut_run - 1) * hl, y0 + (j - 1) * hl
                    xb = x + (x_barres if x_barres is not None else largeur_col - reserve)
                    a(f'<rect x="{xb + i * bw:.2f}" y="{y1:.2f}" width="{bw:.2f}" height="{y2 - y1:.2f}" fill="{couleurs_zones[z]}"/>')
                    debut_run = None
        # cadre de la colonne (facultatif)
        if getattr(o, "bordure", True):
            a(f'<rect x="{x:.2f}" y="{marge+h_titre:.2f}" width="{largeur_col:.2f}" height="{h_mois+nb_jours*hl:.2f}" fill="none" stroke="#222222" stroke-width="{0.25*s:.2f}"/>')
    ordre_fichier = {nom: i for i, (nom, _) in enumerate(_categories_fichier)}
    legende_ev = (sorted(categories_vues.items(), key=lambda kv: ordre_fichier.get(kv[0], 0))
                  if getattr(o, "legende_evenements", True) else [])
    if zones or ponts_actifs or jours_paye or legende_ev:
        fs0, ly = 2.6 * s, H - marge * 0.55
        elems = []                                   # (kind, label, color)
        if zones:
            elems.append(("titre", "Vacances scolaires :", None))
            elems += [("carre", f"Zone {z}", couleurs_zones[z]) for z in zones]
        if ponts_actifs:
            elems.append(("carre", "Pont", c_pont))
        if jours_paye:
            elems.append(("icone", "Jour de paye", c_paye))
        elems += [("carre", nom, couleur) for nom, couleur in legende_ev]

        def largeur_elem(el):
            genre, lib, _ = el
            if genre == "titre":
                return 0.62 * fs0 * len(lib) + 1.5 * s
            return (2.4 * s if genre == "carre" else 2.9 * s) + 0.8 * s + 0.6 * fs0 * len(lib) + 3.2 * s

        total = sum(largeur_elem(el) for el in elems)
        f = min(1.0, (W - 2 * marge) / total)        # shrink the legend if it overflows the usable width
        xl = marge
        for el in elems:
            genre, lib, coul = el
            if genre == "titre":
                a(f'<text x="{xl:.2f}" y="{ly:.2f}" font-size="{fs0*f:.2f}" font-weight="bold" fill="#555555">{escape(lib)}</text>')
                xl += largeur_elem(el) * f
                continue
            pw = (2.4 * s if genre == "carre" else 2.9 * s) * f
            if genre == "carre":
                a(f'<rect x="{xl:.2f}" y="{ly - 2.2 * s * f:.2f}" width="{pw:.2f}" height="{2.4 * s * f:.2f}" fill="{coul}" stroke="#888888" stroke-width="{0.15 * s:.2f}"/>')
            else:
                a(icone_paye(xl, ly - 3.0 * s * f, 3.4 * s * f, coul))
            a(f'<text x="{xl + pw + 0.8 * s * f:.2f}" y="{ly:.2f}" font-size="{fs0*f:.2f}" fill="#555555">{escape(lib)}</text>')
            xl += largeur_elem(el) * f
    if o.pied:
        a(f'<text x="{W/2:g}" y="{H-marge*0.55:.2f}" font-size="{2.8*s:.2f}" text-anchor="middle" fill="#555555">{escape(o.pied)}</text>')
    a('</g></svg>')
    return "\n".join(p)


def couleur_type(valeur, autoriser_aucune=False):
    v = valeur.strip().lower()
    if autoriser_aucune and v in ("aucune", "aucun", "none"):
        return "aucune"
    if v in COULEURS_NOMMEES:
        return COULEURS_NOMMEES[v]
    m = re.fullmatch(r"#?([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})", v)
    if not m:
        noms = ", ".join(sorted(COULEURS_NOMMEES))
        raise argparse.ArgumentTypeError(f"couleur « {valeur} » invalide : code hexadécimal (#c8102e) ou nom ({noms})")
    code = m.group(1)
    if len(code) == 3:
        code = "".join(c * 2 for c in code)
    return "#" + code[:6]  # 8 hex digits (#rrggbbaa): transparency is ignored


def couleur_ou_aucune(valeur):
    return couleur_type(valeur, autoriser_aucune=True)


def demander(question, defaut, convertir=str):
    while True:
        rep = input(f"{question} [{defaut}] : ").strip()
        try:
            return convertir(rep) if rep else defaut
        except (ValueError, argparse.ArgumentTypeError) as e:
            print("  ->", e)


def parmi(*valeurs):
    """Converter that only accepts certain values (case-insensitive)."""
    def conv(v):
        for x in valeurs:
            if v.strip().lower() == x.lower():
                return x
        raise ValueError("valeurs possibles : " + ", ".join(valeurs))
    return conv


def demander_oui_non(question, defaut):
    while True:
        rep = input(f"{question} ({'O/n' if defaut else 'o/N'}) : ").strip().lower()
        if not rep:
            return defaut
        if rep in ("o", "oui", "y", "yes"):
            return True
        if rep in ("n", "non", "no"):
            return False
        print("  -> réponds par o (oui) ou n (non)")


def mode_interactif(o, an_defaut):
    print("=== Calendrier semestriel — appuie sur Entrée pour garder la valeur proposée ===")
    noms = ", ".join(sorted(COULEURS_NOMMEES))
    o.annee = demander("Année", an_defaut, int)
    o.format = demander("Format (A3, A4, A5, A6)", "A4", parmi(*sorted(FORMATS)))
    o.orientation = demander("Orientation (paysage / portrait)", "paysage", parmi("paysage", "portrait"))
    o.sans_saints = not demander_oui_non("Afficher les fêtes du jour (saints) ?", True)
    o.sans_feries = not demander_oui_non("Afficher les jours fériés ?", True)
    o.semaines = demander_oui_non("Afficher les numéros de semaine ?", False)
    o.jours_ouvres = demander("Jours travaillés (1 = lundi … 7 = dimanche)", "12345", parse_jours_ouvres)
    o.ponts = demander_oui_non("Matérialiser les ponts (jour travaillé entre un férié et un jour non travaillé) ?", False)
    o.paye = demander("Jours de paye : « fin » (N-ième dernier jour ouvré), « fixe » (date fixe) ; vide = aucun", "", parmi("fin", "fixe"))
    if o.paye == "fin":
        o.paye_n = demander("N (1 = dernier jour ouvré du mois ; 5 = 5e dernier jour ouvré)", 5, int)
    elif o.paye == "fixe":
        o.paye_jour = demander("Jour du mois", 25, int)
        o.paye_decalage = demander("Si ce jour n'est pas ouvré : avant / apres / non", "avant", parmi("avant", "apres", "non"))
    o.sans_bordure = not demander_oui_non("Tracer une bordure autour des colonnes de mois ?", True)
    o.zones = demander("Zones de vacances scolaires à afficher (ex. ABC, AC ; vide = aucune)", "", lambda v: v.upper())
    if o.zones:
        o.sans_pont = not demander_oui_non("Marquer le pont de l'Ascension (du jeudi au dimanche) ?", True)
        o.position_barres = demander("Barres de vacances : à côté des dates ou contre le bord droit du mois", "dates", parmi("dates", "droite"))
    print(f"Couleurs : code hexadécimal (#c8102e) ou nom ({noms})")
    o.couleur = demander("Couleur principale (titre, en-têtes de mois)", o.couleur, couleur_type)
    o.couleur_feries = demander("Couleur des dimanches et jours fériés (vide = idem couleur principale)", "", lambda v: couleur_type(v) if v else None)
    o.couleur_weekend = demander("Fond des samedis/dimanches (couleur ou « aucune »)", o.couleur_weekend, couleur_ou_aucune)
    o.titre = demander("Texte en haut à droite (nom de la structure, vide = aucun)", "", str)
    o.pied = demander("Texte de pied de page (vide = aucun)", "", str)
    o.sortie = demander("Dossier de sortie", ".", str)
    return o


def main():
    an_defaut = date.today().year + (1 if date.today().month >= 9 else 0)
    ap = argparse.ArgumentParser(
        description="Calendrier semestriel « une ligne par jour » en SVG (Inkscape). Sans argument : mode questions/réponses.")
    ap.add_argument("annee", nargs="?", type=int, default=an_defaut, help=f"année (défaut : {an_defaut})")
    ap.add_argument("-i", "--interactif", action="store_true", help="poser les questions une à une")
    ap.add_argument("--format", choices=sorted(FORMATS), default="A4", help="format de papier (défaut : A4)")
    ap.add_argument("--orientation", choices=["paysage", "portrait"], default="paysage")
    ap.add_argument("--sans-saints", "--sans-fetes", dest="sans_saints", action="store_true",
                    help="ne pas afficher les saints (lignes vierges pour notes)")
    ap.add_argument("--sans-feries", action="store_true", help="ne pas afficher ni colorer les jours fériés")
    ap.add_argument("--semaines", action="store_true", help="afficher les numéros de semaine ISO le lundi")
    ap.add_argument("--zones", default="", help="vacances scolaires à afficher : A, B, C ou une combinaison (ex. ABC, AC) ; vide = aucune")
    ap.add_argument("--jours-ouvres", default="12345", help="jours travaillés, 1 = lundi … 7 = dimanche (défaut : 12345)")
    ap.add_argument("--ponts", action="store_true", help="matérialiser les ponts (jour travaillé isolé entre un férié et un jour non travaillé)")
    ap.add_argument("--couleur-ponts", type=couleur_type, default="#b6e2a1", help="couleur des ponts (défaut : #b6e2a1)")
    ap.add_argument("--paye", choices=["fin", "fixe"], default=None,
                    help="jours de paye : « fin » = N-ième dernier jour ouvré du mois, « fixe » = date fixe (absent = aucun)")
    ap.add_argument("--paye-n", type=int, default=5, help="avec --paye fin : N (1 = dernier jour ouvré du mois ; défaut 5)")
    ap.add_argument("--paye-jour", type=int, default=25, help="avec --paye fixe : jour du mois (défaut 25)")
    ap.add_argument("--paye-decalage", choices=["avant", "apres", "non"], default="avant",
                    help="avec --paye fixe : si le jour n'est pas ouvré, jour ouvré précédent (défaut), suivant, ou pas de décalage")
    ap.add_argument("--paye-feries-ouvres", action="store_true", help="considérer les jours fériés comme ouvrés pour la paye")
    ap.add_argument("--couleur-paye", type=couleur_type, default="#1b7f3b", help="couleur du pictogramme de paye (défaut : #1b7f3b)")
    ap.add_argument("--sans-bordure", action="store_true", help="ne pas tracer de cadre autour des colonnes de mois")
    ap.add_argument("--position-barres", choices=["dates", "droite"], default="dates",
                    help="barres de vacances : à côté des dates (défaut) ou contre le bord droit du mois")
    ap.add_argument("--sans-pont", action="store_true", help="ne pas marquer le pont de l'Ascension, du jeudi au dimanche (avec --zones)")
    ap.add_argument("--couleur", type=couleur_type, default="#1f3a5f", help="couleur principale : titre et en-têtes de mois")
    ap.add_argument("--couleur-feries", type=couleur_type, default=None, help="couleur des dimanches et jours fériés (défaut : couleur principale)")
    ap.add_argument("--couleur-weekend", type=couleur_ou_aucune, default="#ececec", help="fond des samedis/dimanches, ou « aucune » (défaut : #ececec)")
    ap.add_argument("--couleur-texte", type=couleur_type, default="#111111", help="couleur du texte (défaut : #111111)")
    ap.add_argument("--police", default="", help="police à utiliser en priorité (ex. « Arial »)")
    ap.add_argument("--titre", default="", help="texte en haut à droite (nom de la structure, etc.)")
    ap.add_argument("--pied", default="", help="texte de pied de page")
    ap.add_argument("--evenements", help="fichier JSON d'événements par catégories colorées (voir l'en-tête du script) ou {\"AAAA-MM-JJ\" ou \"MM-JJ\": \"texte\"}")
    ap.add_argument("--sans-legende-evenements", action="store_true", help="ne pas lister les catégories d'événements dans la légende")
    ap.add_argument("--sortie", default=".", help="dossier de sortie")
    o = ap.parse_args()
    if o.interactif or len(sys.argv) == 1:
        o = mode_interactif(o, an_defaut)
    w, h = FORMATS[o.format]
    o.dimensions = (h, w) if o.orientation == "portrait" else (w, h)
    o.zones_vacances = [z for z in "ABC" if z in (o.zones or "").upper()]
    o.vacances = vacances_par_zone(VACANCES_DEFAUT)
    o.pont_ascension = not o.sans_pont
    o.bordure = not o.sans_bordure
    o.legende_evenements = not o.sans_legende_evenements
    if o.evenements:
        try:
            charger_evenements(o.evenements)
        except (OSError, ValueError) as e:
            ap.error(f"fichier d'événements : {e}")
    try:
        if isinstance(o.jours_ouvres, str):
            o.jours_ouvres = parse_jours_ouvres(o.jours_ouvres)
    except ValueError as e:
        ap.error(str(e))
    if o.paye:
        o.paye = {"mode": o.paye, "n": o.paye_n, "jour": o.paye_jour, "decalage": o.paye_decalage,
                  "feries_non_ouvres": not o.paye_feries_ouvres}
    else:
        o.paye = None
    os.makedirs(o.sortie, exist_ok=True)
    for sem in (1, 2):
        chemin = os.path.join(o.sortie, f"calendrier_{o.annee}_S{sem}.svg")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(face(o.annee, sem, o))
        print("écrit :", chemin)


if __name__ == "__main__":
    main()
