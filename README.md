<p align="center">
  <img src="logo%20small.png" alt="SchattenBlase Logo">
</p>


SchattenBlase ist eine lokale Desktop-Anwendung zur 2D- und 3D-Schattensimulation auf Basis von Karten- und Geometriedaten. Das Programm richtet sich an frühe Planungs-, Analyse- und Visualisierungsaufgaben, bei denen Gebäude, einfache Körper, Vegetation und Grundflächen im Zusammenhang mit Sonnenstand und Schattenwurf untersucht werden sollen.

Die Anwendung ist in Python mit PySide6 umgesetzt. Kartenkacheln und Gebäudedaten werden bei Bedarf aus OpenStreetMap-nahen Quellen geladen. Für die 3D-Gebäudeerkennung wird primär die Streets-GL-Vektorkachelquelle verwendet; der klassische OSM-/Overpass-Import dient als bewusst bestätigter Fallback.

## Funktionsumfang

- Interaktive 2D-Karte mit Ortssuche, Zoom, Pan und lokalem Kachelcache
- 3D-Ansicht für Gebäude, Grundflächen und manuell angelegte Objekte
- Import von 3D-Gebäuden aus Streets-GL-Vektorkacheln
- Optionaler OSM-/Overpass-Fallback, wenn Streets-GL keine verwertbaren Objekte liefert
- Manuelles Erstellen und Bearbeiten von Objekten wie Quader, Zylinder, Kugel, Kegel, Pyramide, Wandflächen, Bäume und Büsche
- Grundflächenanalyse mit belegter Fläche, Schattenfläche und wirksamer Verschattung
- Sonnenstandsberechnung nach Datum, Uhrzeit, Jahreszeit und Standort
- Zeitraffer für den Schattenverlauf über einen Zeitraum
- Projektdateien für Speichern und Laden von Karte, Objekten, Grundfläche und Simulationszustand
- Mehrsprachige UI-Struktur über Sprachdateien in `lang/`

## Projektstatus

Das Projekt befindet sich in aktiver Entwicklung. Die Simulation ist für lokale Analyse und Visualisierung vorgesehen, nicht für rechtsverbindliche Gutachten oder baurechtliche Nachweise. Die Genauigkeit hängt von den verfügbaren Kartendaten, Gebäudetags, Höhenangaben und der jeweiligen Darstellungsvereinfachung ab.

## Voraussetzungen

Empfohlen wird Python 3.11 oder neuer.

Laufzeitabhängigkeiten:

```text
PySide6>=6.7
shapely>=2.0
```

## Installation aus dem Quellcode

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Unter Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Bedienung

Die Anwendung startet mit einer Kartenansicht und einer 3D-Ansicht. Über die Ortssuche kann ein Standort geladen werden. Der aktuelle Kartenausschnitt wird über die Koordinatenfelder und den Zoom definiert.

Gebäude können über den Button `Streets-GL-3D laden` aus dem sichtbaren Kartenausschnitt importiert werden. Falls daraus keine 3D-Objekte entstehen oder der Import fehlschlägt, fragt die Anwendung gesondert nach, ob der ältere OSM-/Overpass-Import als Fallback verwendet werden soll.

Manuelle Objekte und Grundflächen werden in den jeweiligen Reitern erstellt und bearbeitet. Schattenwerte werden auf Basis des eingestellten Datums, der Uhrzeit und der Objektgeometrie berechnet. Die Zeitrafferfunktion erlaubt eine schnelle Vorschau des Schattenverlaufs.

## Datenquellen und Netzwerkzugriffe

SchattenBlase nutzt externe Dienste nur für Karten-, Such- und Gebäudedaten. Dazu gehören insbesondere OpenStreetMap-Kartenkacheln, Nominatim für die Ortssuche, Overpass für den Fallback-Gebäudeimport und Streets-GL-Vektorkacheln für die primäre 3D-Gebäudequelle.

Bei Offline-Nutzung können bereits gespeicherte Kartenkacheln verwendet werden. Nicht lokal vorhandene Daten können dann nicht automatisch ergänzt werden.

## Lokale Daten

Standardmäßig legt die Anwendung neben dem Programmordner einen Ordner `Schattenblase-Daten/` an. Dort werden Konfiguration, Kartenkacheln, Projekte und Exporte gespeichert. Dieser Ordner ist bewusst in `.gitignore` ausgeschlossen.

## Build mit PyInstaller

Die mitgelieferte Datei `SchattenBlase.spec` erstellt eine ausführbare Desktop-Anwendung ohne Konsolenfenster.

Vorbereitung:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

Das Ergebnis liegt danach in `dist/`. Wenn eine Datei `assets/icon.ico` vorhanden ist, wird sie automatisch als Programmsymbol verwendet. Ohne diese Datei wird das Programm ohne eigenes Icon gebaut.

## Hinweise zur Genauigkeit

Gebäudehöhen werden nur so genau übernommen, wie sie in den importierten Daten vorhanden sind. Fehlen Höhenangaben, verwendet die Anwendung plausible Standardwerte. Aus Performancegründen können Footprints vereinfacht und sehr große Importmengen begrenzt werden. Das verbessert die Bedienbarkeit, kann aber Details einzelner Gebäude reduzieren.

## Lizenz

MIT-Lizenz
