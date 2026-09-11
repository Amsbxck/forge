# Serienlogos (optional)

Die Rennkarte zeigt standardmäßig einen Schriftzug im Stil der App —
`IRONMAN 70.3`, `CHALLENGE FAMILY`, `HYROX`. Dafür ist hier nichts nötig.

Liegt in diesem Ordner eine Datei mit dem passenden Namen, wird sie
stattdessen angezeigt:

```
ironman703.svg
ironman.svg
challenge.svg
hyrox.svg
spartan.svg
xterra.svg
t100.svg
majors.svg
```

SVG bevorzugt, PNG geht auch (dann in `SeriesBadge.jsx` die Endung anpassen).
Höhe wird auf 20 px skaliert, Breite auf maximal 110 px begrenzt — eine
horizontale Wortmarke passt besser als ein quadratisches Emblem. Auf dunklem
Grund (#111318) muss das Logo hell sein.

Fehlt eine Datei, greift automatisch der Schriftzug. Ein kaputter Pfad bricht
nichts.

## Warum nichts mitgeliefert wird

Ironman, Challenge Family und Hyrox sind eingetragene Marken. In der eigenen
Installation ist die Verwendung unkritisch; in einem öffentlich verteilten
Repository oder einer Installation für fremde Athleten wäre es fremdes
Material ohne Lizenz. Deshalb bleibt die Entscheidung bei dir.
