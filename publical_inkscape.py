#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publical — Inkscape 1.x extension: Extensions > Render > Publical - Calendrier semestriel (FR).
Generates a French semester desk calendar (the kind traditionally handed out as
promotional material), one text line per day, six months per side.
The front and back sides can be placed on two pages (Inkscape 1.2+) or on two layers.

Files to copy together into the Inkscape user extensions folder:
  publical.inx, publical_inkscape.py, publical.py
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inkex
from lxml import etree

import publical as cal

NS_INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"
ECART_PAGES = 20  # mm, gap between the two pages


def hex_couleur(valeur, defaut):
    """Convert an Inkscape color-picker value (RGBA integer) or a text value into #rrggbb."""
    if valeur is None or str(valeur).strip() == "":
        return defaut
    s = str(valeur).strip()
    if re.fullmatch(r"-?\d+", s):
        n = int(s) & 0xFFFFFFFF
        return "#%02x%02x%02x" % ((n >> 24) & 255, (n >> 16) & 255, (n >> 8) & 255)
    if re.fullmatch(r"#[0-9a-fA-F]{8}", s):
        return s[:7].lower()
    try:
        return cal.couleur_type(s)
    except argparse.ArgumentTypeError:
        return defaut


class Publical(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="general")
        pars.add_argument("--annee", type=int, default=2027)
        pars.add_argument("--semestre", default="1")
        pars.add_argument("--format", default="A4")
        pars.add_argument("--orientation", default="paysage")
        pars.add_argument("--disposition", default="pages")
        pars.add_argument("--saints", type=inkex.Boolean, default=True)
        pars.add_argument("--feries", type=inkex.Boolean, default=True)
        pars.add_argument("--semaines", type=inkex.Boolean, default=False)
        pars.add_argument("--titre", default="")
        pars.add_argument("--pied", default="")
        pars.add_argument("--evenements", default="")
        pars.add_argument("--legende_evenements", type=inkex.Boolean, default=True)
        pars.add_argument("--couleur", default="")
        pars.add_argument("--feries_meme_couleur", type=inkex.Boolean, default=True)
        pars.add_argument("--couleur_feries", default="")
        pars.add_argument("--fond_weekend", type=inkex.Boolean, default=True)
        pars.add_argument("--couleur_weekend", default="")
        pars.add_argument("--couleur_texte", default="")
        pars.add_argument("--police", default="")
        pars.add_argument("--vacances", type=inkex.Boolean, default=True)
        pars.add_argument("--pont", type=inkex.Boolean, default=True)
        pars.add_argument("--position_barres", default="dates")
        pars.add_argument("--jours_ouvres", default="12345")
        pars.add_argument("--ponts_entreprise", type=inkex.Boolean, default=False)
        pars.add_argument("--couleur_ponts", default="")
        pars.add_argument("--paye", type=inkex.Boolean, default=False)
        pars.add_argument("--paye_mode", default="fin")
        pars.add_argument("--paye_n", type=int, default=5)
        pars.add_argument("--paye_jour", type=int, default=25)
        pars.add_argument("--paye_decalage", default="avant")
        pars.add_argument("--paye_feries_non_ouvres", type=inkex.Boolean, default=True)
        pars.add_argument("--couleur_paye", default="")
        pars.add_argument("--bordure", type=inkex.Boolean, default=True)
        for z in "abc":
            pars.add_argument(f"--zone_{z}", type=inkex.Boolean, default=True)
            pars.add_argument(f"--couleur_zone_{z}", default="")
        for cle in ("toussaint", "noel", "ete", "hiver_a", "hiver_b", "hiver_c",
                    "printemps_a", "printemps_b", "printemps_c"):
            pars.add_argument(f"--vac_{cle}", default=cal.VACANCES_DEFAUT[cle])

    def effect(self):
        p = self.options
        w, h = cal.FORMATS.get(p.format, cal.FORMATS["A4"])
        if p.orientation == "portrait":
            w, h = h, w

        chemin = (p.evenements or "").strip()
        if chemin:
            try:
                cal.charger_evenements(chemin)
            except (OSError, ValueError) as e:
                raise inkex.AbortExtension(f"Fichier d'événements illisible : {chemin}\n{e}")

        zones = [z for z in "ABC" if p.vacances and getattr(p, f"zone_{z.lower()}")]
        try:
            vacances = cal.vacances_par_zone({cle: getattr(p, f"vac_{cle}") for cle in cal.VACANCES_DEFAUT}) if zones else {}
        except ValueError as e:
            raise inkex.AbortExtension(f"Dates de vacances scolaires : {e}")
        try:
            ouvres = cal.parse_jours_ouvres(p.jours_ouvres)
        except ValueError as e:
            raise inkex.AbortExtension(str(e))
        cfg_paye = None
        if p.paye:
            cfg_paye = {"mode": p.paye_mode, "n": p.paye_n, "jour": p.paye_jour, "decalage": p.paye_decalage,
                        "feries_non_ouvres": p.paye_feries_non_ouvres}
        couleurs_zones = {z: hex_couleur(getattr(p, f"couleur_zone_{z.lower()}"), cal.ZONE_COULEURS[z]) for z in "ABC"}

        o = argparse.Namespace(
            zones_vacances=zones, vacances=vacances, couleurs_zones=couleurs_zones, pont_ascension=p.pont,
            position_barres=p.position_barres, bordure=p.bordure,
            jours_ouvres=ouvres, ponts=p.ponts_entreprise, couleur_ponts=hex_couleur(p.couleur_ponts, "#b6e2a1"),
            paye=cfg_paye, couleur_paye=hex_couleur(p.couleur_paye, "#1b7f3b"),
            dimensions=(w, h),
            couleur=hex_couleur(p.couleur, "#1f3a5f"),
            couleur_feries=None if p.feries_meme_couleur else hex_couleur(p.couleur_feries, "#c8102e"),
            couleur_weekend=hex_couleur(p.couleur_weekend, "#ececec") if p.fond_weekend else "aucune",
            couleur_texte=hex_couleur(p.couleur_texte, "#111111"),
            police=(p.police or "").strip(),
            sans_saints=not p.saints,
            sans_feries=not p.feries,
            semaines=p.semaines,
            titre=p.titre or "",
            pied=p.pied or "",
            evenements=chemin or None,
            legende_evenements=p.legende_evenements,
        )

        # The document takes the paper size (user unit = 1 mm)
        self.svg.set("width", f"{w}mm")
        self.svg.set("height", f"{h}mm")
        self.svg.set("viewBox", f"0 0 {w} {h}")
        try:
            self.svg.namedview.set("inkscape:document-units", "mm")
        except Exception:
            pass

        faces = [1, 2] if p.semestre == "both" else [int(p.semestre)]
        en_pages = len(faces) == 2 and p.disposition == "pages"
        decalage = w + ECART_PAGES

        # Inkscape pages (1.2+): start from a clean document, one page per side
        nv = self.svg.namedview
        for ancienne in list(nv.iterchildren("{%s}page" % NS_INKSCAPE)):
            nv.remove(ancienne)
        if en_pages:
            for k, (nom_page, x_page) in enumerate((("Recto", 0), ("Verso", decalage)), 1):
                page = etree.SubElement(nv, "{%s}page" % NS_INKSCAPE)
                page.set("id", f"calendrier-page-{k}")
                page.set("x", f"{x_page:g}")
                page.set("y", "0")
                page.set("width", f"{w:g}")
                page.set("height", f"{h:g}")
                page.set("{%s}label" % NS_INKSCAPE, f"{nom_page} — {cal.MOIS[0 if k == 1 else 6]} à {cal.MOIS[5 if k == 1 else 11]}")

        for sem in faces:
            racine = etree.fromstring(cal.face(p.annee, sem, o).encode("utf-8"))
            debut, fin = (0, 5) if sem == 1 else (6, 11)
            nom = ("Recto" if sem == 1 else "Verso") + f" — {cal.MOIS[debut]} à {cal.MOIS[fin]} {p.annee}"
            couche = inkex.Layer.new(nom)
            for enfant in list(racine):
                couche.append(enfant)
            if len(faces) == 2 and sem == 2:
                if en_pages:
                    couche.set("transform", f"translate({decalage:g},0)")  # back side on the 2nd page
                else:
                    couche.style["display"] = "none"  # back side hidden: show/export it separately
            self.svg.append(couche)


if __name__ == "__main__":
    Publical().run()
