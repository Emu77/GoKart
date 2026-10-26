# Biotoptypen-Kataloge (Bund / Länder)

Eine CSV je Schlüssel, Dateiname = Kürzel (`SH.csv`, `NI.csv`, `BUND.csv` …).
Kopfzeilen `# feld: wert` (schluessel, name, land, stand, quelle, url, vollstaendig, hinweis),
danach `code;name;nr;obercode;ebene;bund_code;ffh_lrt` (UTF-8, Semikolon).
`obercode`/`ebene` dürfen leer sein – sie werden aus `nr` (1.7.1 → 1.7) bzw. aus dem Code (WMy → WM → W) abgeleitet.

`zuordnung_bund.csv` (`schluessel;code;bund_code`) ordnet Landes-Codes dem BfN-Code zu. Wird beim Einspielen
in `biotoptypen.bund_code` übernommen und bei jeder Erfassung mitgespeichert.

## Stand

| Schlüssel | Quelle | Stand | Im Katalog |
|---|---|---|---|
| SH | LfU Schleswig-Holstein: Kartieranleitung und Biotoptypenschlüssel (Standardliste) | V 2.2.1, Aug. 2024 | 545 Einträge, **ohne** Gruppen nach SB (Hauptgruppe S) |
| NI | NLWKN, v. Drachenfels: Kartierschlüssel für Biotoptypen in Niedersachsen | 03/2021, Korr. 03/2023 | **nur Obergruppe 1 (Wälder)**, 123 Einträge |
| HH | BUKEA Hamburg: Kartieranleitung und Biotoptypenschlüssel | 5. Aufl., April 2023 | – (importieren) |
| HB | Bremen: Kartierschlüssel für Biotoptypen in Bremen (Hellberg & Nagler) | 2013 | – (importieren) |
| MV | LUNG M-V: Anleitung für die Kartierung von Biotoptypen und FFH-LRT | 2013 | – (importieren) |
| BUND | BfN: Rote Liste der gefährdeten Biotoptypen Deutschlands (Finck et al., NaBiV 156) | 2017 | – (Buch, nicht frei als Datei) |

**Historische Schlüssel** (für Altdaten, z. B. ältere Kartierungen/Shapes – Codes passen nicht zu den aktuellen Fassungen):

| Schlüssel | Quelle | Stand | Im Katalog |
|---|---|---|---|
| SH_2003 | LANU S-H: Standardliste der Biotoptypen, 2. Fassung | Mai 2003 | 396, vollständig; `bund_code` = „RL BfN“ der Synopse (BfN 1994), `ffh_lrt` aus der Liste |
| HH_1999 | Naturschutzamt Hamburg: Biotoptypenschlüssel (tabellarische Übersicht) | Schlüssel 1999 / Anleitung 07/2002 | 514, vollständig |
| BE_2002 | Senatsverwaltung Berlin: Biotoptypenliste Berlins (Köstler/Fietz) | 2002 | 945; Buchstaben-Code in `[…]` hinter dem Namen (auch suchbar) |
| BB_2002 | Liste der Biotoptypen Brandenburgs (Zimmermann, LUA), aus der Gegenüberstellung Berlin–Brandenburg | 2002 | 950, evtl. unvollständig |
| SN_2003 | LfUG Sachsen: Biotopkartierung in Sachsen, Liste der Biotoptypen | 10/2003 | 98 – nur selektive Kartierung (geschützte/wertvolle Biotope) |

Besonderheiten aus den Originalen: SH_2003 vergibt `FGk` doppelt (Kalkreicher Graben und Kanal) – ein Eintrag mit beiden
Namen; `AOo` bei der Beerenstrauch-Plantage ist ein Tippfehler der Liste (Teil II und Synopse: `AOb`). Groß-/Kleinschreibung
der SH-Codes vereinheitlicht (2 Groß-, dann Kleinbuchstaben, z. B. `Ffa` → `FFa`).
Nicht übernommen: Hamburger LRT-Kartieranleitung (Entwurf 2003, nur Teil-Liste), Berlin nach Auhagen 1994, FFH-Gebiete Sachsen.

Die Listen wurden aus den veröffentlichten PDFs übernommen. Vor Weitergabe des Repos prüfen, ob die
Herausgeber einer Weiterverbreitung zustimmen (SH gibt die Liste auf Anfrage als Excel heraus).

## Ergänzen

PDFs herunterladen, Seiten der Übersicht/des Inhaltsverzeichnisses heraussuchen, dann (Vorschau ohne `--aus`):

```bash
cd qfield/werkzeuge
K=../../qgis_plugin/gokart_desktop/biotope_kataloge

# Niedersachsen – Übersicht "II. Übersicht über die Biotoptypen" (Seitenzahlen anpassen)
python3 biotope_katalog_import.py --pdf Kartierschluessel_NI.pdf --muster klammer --seiten 5-20
python3 biotope_katalog_import.py --pdf Kartierschluessel_NI.pdf --muster klammer --seiten 5-20 \
    --aus $K/NI.csv --zusammenfuehren --vollstaendig ja

# Hamburg / Bremen (Codes ebenfalls in Klammern, sonst --muster code-zuerst probieren)
python3 biotope_katalog_import.py --pdf hamburg.pdf --muster klammer --seiten … --aus $K/HH.csv \
    --schluessel HH --land Hamburg --name "Kartieranleitung und Biotoptypenschlüssel Hamburg" --stand "04/2023"

# Schleswig-Holstein aus der Excel-Fassung des LfU (Spalten anpassen)
python3 biotope_katalog_import.py --tabelle Standardliste_SH.xlsx --code-spalte A --name-spalte B \
    --aus $K/SH.csv --zusammenfuehren --vollstaendig ja

# Bund (BfN, Codes 34.07.01.01 …)
python3 biotope_katalog_import.py --pdf rote_liste_biotoptypen.pdf --muster bund --seiten … --aus $K/BUND.csv \
    --schluessel BUND --land Deutschland --name "Rote Liste der gefährdeten Biotoptypen Deutschlands" --stand 2017
```

`--zusammenfuehren` behält Einträge und `bund_code`/`ffh_lrt`, die schon im Katalog stehen, und meldet geänderte Namen.

Danach ins Projekt: `python3 biotope_einspielen.py <Projekt> --schluessel NI` (oder in QGIS: GoKart → Einrichten… →
„Kataloge einspielen“ – dafür den Plugin-Ordner neu ins QGIS-Profil kopieren). Fürs Tablet `abgleich.py`.

## Quellen

- SH: <https://www.schleswig-holstein.de/mm/downloads/LFU/Kartieranleitung/20240819_Kartieranleitung_Standardliste_SH_V2.2.1_2024_korr.pdf>
- NI: <https://www.nlwkn.niedersachsen.de/download/111210/Aktuelle_Version_des_Kartierschluessels_mit_Korrekturen_Aenderungen_Stand_01._Maerz_2023_.pdf>
- HH: <https://epub.sub.uni-hamburg.de/epub/volltexte/2024/168666/pdf/download_kartieranleitung_biotoptypenschluessel.pdf>
- MV: <https://umweltportal.mv-regierung.de/lung/files/bibo/biotopkartieranleitung2013.pdf>
- HB: Biotopkartierung Bremen, Senator für Umwelt (Kartierschlüssel 2013, Biotopwertliste 2014) – <https://umwelt.bremen.de>
- BUND: Finck, P. et al. (2017): Rote Liste der gefährdeten Biotoptypen Deutschlands. Naturschutz und Biologische Vielfalt 156
