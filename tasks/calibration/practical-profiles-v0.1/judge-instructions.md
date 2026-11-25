# Bewertungsablauf v1

Alle Quellen sind ausdrücklich fiktives, kontrolliertes Kalibrierungsmaterial.
Bewerte die jeweilige Aufgabe ausschließlich gegen ihr Quellenpaket, ihren
Auftrag, ihre Referenz und die gemeinsame Rubrik. Externes Wissen darf die
Quellen nicht überschreiben. Die Referenz ist eine Menge sachlicher Grenzen;
sie ist kein Mustertext und schreibt keine einzige richtige Empfehlung vor.

## Rollen und Reihenfolge

1. Der Controller prüft Antwortstatus, Abbruchgrund, Integrität und Wortzahl.
   Er inventarisiert Quellenverweise. Diese strukturellen Prüfungen beweisen
   keine semantische Richtigkeit. EOF, Timeout, Trunkierung und fehlende
   Endantwort bleiben technische Ergebnisse, auch wenn ein Teiltext existiert.
2. Das Frontier-Modell bewertet alle auswertbaren Endtexte mit der eingefrorenen
   Rubrik. Es prüft zuerst Sachbehauptungen und Bezugsgruppen, dann Synthese,
   Nutzen und Sprache. Eine schöne Formulierung gleicht keine falsche
   Schlüsselaussage aus. Es hält strukturierte Einzelurteile fest.
3. Für den Nutzer werden drei bereits vor den Antworten festgelegte Paare mit
   insgesamt sechs Texten bereitgestellt. Pro Paar sind Auftrag und Quellen
   gleich. Die Seitenfolge wird vorab permutiert. Modellnamen, Profil, Laufzeit,
   Denktexte und Frontier-Bewertungen fehlen in dieser Ansicht. Ein fehlender
   oder unvollständiger Text bleibt als solcher sichtbar; kein Austausch gegen
   einen gelungenen Wiederholungsversuch.
4. Der Nutzer beurteilt zunächst unabhängig die praktische Brauchbarkeit.
   Erst danach zeigen wir die vorher festgehaltene Frontier-Bewertung und
   untersuchen Übereinstimmungen und Abweichungen. Zustimmung ist kein Ziel
   an sich: zusätzliche Kriterien und unterschiedliche Gewichtungen werden
   ausdrücklich erfasst.
5. V1-Urteile bleiben erhalten. Gelernte Vorlieben führen zu einer begründeten
   Rubrik v2 oder einer separat ausgewiesenen Sensitivitätsauswertung aller
   betroffenen Antworten. Eine neue Rubrik gilt vor einer späteren Evaluation;
   keine nachträgliche Anpassung nur zugunsten einzelner Modelle.

## Sachprüfung

Trenne falsche Aussagen, fehlende wichtige Einordnung und optionale Details.
Nicht jede ausgelassene Zahl ist ein Fehler. Eine korrekte qualitative
Einordnung kann eine optionale Rechnung ersetzen. Runde sachgerecht und
akzeptiere gleichwertige deutsche Schreibweisen. Eine Quelle in einem Satz
garantiert nicht, dass sie die Aussage trägt: prüfe ihren tatsächlichen Inhalt.

Jeder behauptete schwere Fehler braucht eine wörtliche Stelle der Antwort,
eine Referenz-Fakt-ID, die zugrunde liegenden Quellen-IDs und eine Erklärung
der wesentlichen Auswirkung. Wenn die Textstelle oder Evidenz die Diagnose
nicht trägt, markiere den Befund als unklar und behaupte ihn nicht als
festgestellten schweren Fehler. Quellen- und Antwortzitate sind überprüfbar.

Bewerte jede der fünf Dimensionen von 0 bis 4 mit kurzer Begründung. Gesamtpunkte
werden aus den Gewichten berechnet. Halte zusätzlich fest, ob das Ergebnis
ohne wesentliche Nacharbeit brauchbar ist. Ein belegter schwerer Fehler macht
es in der vorliegenden Form unbrauchbar; der Punktwert bleibt zur Diagnose
sichtbar. Keine automatische harte Sperre allein wegen eines Zielwortwerts.

## Form des strukturierten Frontier-Urteils

`schema_version: practical-calibration-judgment-v1`, `case_id`, eine opaque
`candidate_id`, `answer_sha256`, `dimension_ratings`, `critical_findings`,
`usable_as_delivered` und `overall_reason` werden verlangt. Jede Dimension
enthält `rating` und `rationale`; optionale `evidence_quotes` müssen wörtlich
in der Antwort stehen. Ein schwerer Befund enthält `fact_id`, `source_ids`,
`answer_quote` und `explanation`. Die Quellen-IDs müssen zur Referenz passen.
Technische Ausfälle erhalten keinen erfundenen Qualitätswert.

## Menschlicher Vergleich

Für jedes Paar reichen zunächst diese Antworten:

- Würdest du A, B, beide oder keinen der Texte mit vertretbarer Nacharbeit nutzen?
- Welcher hilft dir mehr: A, B, gleichwertig oder unsicher? Warum?
- Welche Stelle müsstest du zuerst ändern, und wie schwer wiegt das für dich?
- Fehlt etwas, das unsere Kriterien noch nicht angemessen erfassen?

Der Nutzer kann die Einstufung auch als Freitext geben; wir strukturieren sie
anschließend ohne seine Aussage in eine erzwungene Präferenz umzudeuten.

## Grenzen

Diese Sitzung kennt Aufgaben, Kandidaten und frühere Befunde. Opaque IDs
und fehlende Metadaten verringern Zuordnungsreize, schaffen aber keine
nachgewiesene unabhängige kognitive Verblindung. Kein zusätzlicher kostenpflichtiger
Judge-Aufruf ist Teil des Entwurfs. Die Frontier-Bewertung findet hier statt;
die strukturierte Prüfschnittstelle erlaubt spätere Automatisierung. Zwei
Aufgaben und zwei Wiederholungen sind keine belastbare Fehlerquotenstudie.
