# Ergänzende Textbewertung v0.2

Bewerte zwei verschiedene Verwendungsfragen getrennt:

1. **Gelieferte Fassung:** Wie korrekt, vollständig und unmittelbar brauchbar
   ist der unveränderte Endtext für den ursprünglichen Auftrag?
2. **Redaktionsgrundlage:** Wie gut eignet sich derselbe Text als Ausgangspunkt
   für eine spätere Überarbeitung, und welche konkreten Änderungen braucht er?

Nutze ausschließlich Auftrag, Quellenpaket und sachliche Referenz des Falls.
Ein persönliches Sprachurteil ohne Quellenprüfung bestätigt weder Sachtreue
noch Vollständigkeit. Eine Quellenprüfung bestätigt keine persönliche Präferenz.

## Gelieferte Fassung erhalten

Bei einem bestehenden Urteil übernimm die vollständige v1-Struktur unverändert,
binde ihre Originaldatei per SHA256 und kennzeichne `frozen_v1`. Für neue Urteile
gilt `new_review` ohne behauptete alte Provenienz. Die bestehende v1-Rubrik samt
Gewichten und schwerer-Fehler-Regel bleibt für diesen Bewertungszweig gültig.
Technische Ausfälle bleiben technische Ausfälle ohne erfundenes Qualitätsurteil.

## Lesbarkeit genauer beschreiben

Die vier ergänzenden Merkmale sind ungewichtet und unabhängig voneinander:

- `organization`: sichtbare Gliederung, Absatzfunktion und auffindbare Aussagen.
- `comprehensibility`: verständliche Begriffe, klare Bezüge und Sätze.
- `fluency`: natürlicher Lesefluss, Übergänge, Rhythmus und geringe Umständlichkeit.
- `grammar`: korrektes Deutsch einschließlich Flexion, Wortwahl und Fremdsprachenresten.

Nutze die 0–4-Skala aus v1, aber begründe jedes neue Merkmalsurteil mit mindestens
einer tatsächlichen Antwortstelle. Beispiele für schlecht, brauchbar und sehr
gut stehen in `docs/practical-text-review-v0.2.md`. Unbewertet bleibt `null`;
eine breite alte Sprachpunktzahl wird nicht automatisch in vier neue verteilt.
Eine relative Nutzerpräferenz ist kein absoluter numerischer Merkmalswert.

## Redaktionsgrundlage und Reparaturen

Ohne gesonderte Prüfung gilt `not_assessed`, mit unbekanntem Urteil und leerem
Reparaturplan. Andernfalls begründe `good`, `conditional` oder `poor`. Ein Urteil
als Redaktionsgrundlage ist kein Urteil über eine bereits überarbeitete Fassung.

Jede erforderliche Änderung braucht eine konkrete Antwortstelle oder eine
Referenz-Fakt-ID. Unterscheide Faktenkorrektur, Quellenprüfung, fehlende relevante
Einordnung, Struktur, Verständlichkeit, Lesefluss und Grammatik. Fehlende Inhalte
dürfen an eine Fakt-ID gebunden werden, statt ein nicht vorhandenes Textzitat zu
erfinden. Nicht jede optionale Zahl ist zwingend nachzutragen.

Bei bekannten schweren Sachbefunden kann eine positive Basiseinschätzung nur
`conditional` sein. Der Plan muss alle betroffenen Referenz-Fakten durch konkrete
Faktenkorrekturen oder Quellenprüfungen behandeln; bloß neue Überschriften reichen
nicht. Ein negativer Basisbefund darf stattdessen erläutern, warum eine Neufassung
sinnvoller wäre. Keine Änderung wird durch den Prüfer ausgeführt.

Erwartete Reparierbarkeit ist keine gemessene Arbeitszeit. Deshalb steht
`post_edit_quality` hier immer auf `not_evaluated`. Für eine tatsächliche Redaktion
sind bearbeiteter Text, Änderungen, gegebenenfalls gemessene Zeit und erneute
Sachprüfung separat nachzuweisen. Kein kombinierter Score und kein automatischer
Modellsieger werden aus den beiden Bewertungszweigen berechnet.

Nutzer-Paarurteile bleiben eigene Belege: Gesamtpräferenz, beurteiltes Ziel,
Begründung, vorgesehene Änderungen und ungeprüfte Aspekte. Bedingte Auswahl als
Arbeitsgrundlage darf nicht in ein Freigabeurteil umgedeutet werden. Die vorhandene
Offenlegung von Modellen und Judge-Ergebnissen begründet keine unabhängige Blindheit.
