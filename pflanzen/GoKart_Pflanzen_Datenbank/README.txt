GoKart Pflanzen-Datenbank (BfN-Skript 519, Excel-Stand 2019)

SQLite: GoKart_Pflanzen.sqlite
Tabellen: taxon, namen, eigene_synonyme, flaechen_arten.
Ansicht: suchnamen.
Die Excel-Quelldaten enthalten KEINE deutschen Pflanzennamen. deutscher_name ist daher noch leer.
Die Datenbank enthaelt wissenschaftliche Namen und deren Synonymstatus (1=akzeptiert, x=Synonym, b=Basionym).
fl aechen_arten: flaeche_id muss mit einer Polygon-ID im QGIS-Projekt uebereinstimmen.
Suche mit SQL: SELECT taxon_id,suchname,typ FROM suchnamen WHERE suchname LIKE ? LIMIT 5;
Die Fuzzy-Suche und Spracheingabe werden erst im Plugin implementiert.
Quelle: Butler, May & Metzing (2018), BfN-Skripten 519; Excel-Datei 2019.
