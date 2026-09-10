# Aufgabe: Rollout-Bereitschaft aus drei Dokumentformaten beurteilen

Du berätst das Steering Committee bei einer regionalen Produkteinführung. Im
Arbeitsverzeichnis liegen drei schreibgeschützte Artefakte: eine Word-Richtlinie,
ein PDF mit der Reliability-Prüfung und eine Excel-Arbeitsmappe mit Kapazitäten
und einem Management-Dashboard.

Untersuche die Dokumente gezielt und entscheide auf Basis des im Dossier
genannten Stichtags:

- ob ein vollständiger, phasenweiser oder kein Rollout zulässig ist;
- welche Regionen starten dürfen;
- welcher entscheidende Gate-Verstoß jede blockierte Region stoppt;
- wie widersprüchliche oder überholte Darstellungen aufzulösen sind;
- welche Maßnahmen und Unsicherheiten für das Steering Committee wichtig sind.

Verwende ausschließlich Evidenz aus den bereitgestellten Artefakten. Ein
Dashboard-Status ist keine Autorität, wenn die Richtlinie eine andere
Entscheidungslogik verlangt. Neuere oder ausdrücklich finale Evidenz kann
vorläufige Werte ersetzen. Rechne erforderliche Kennzahlen nach und prüfe dabei
Werte und Formeln.

## Sichtbare Codes

`decision.code`:

`full_go`, `phased_go`, `no_go`, `insufficient_evidence`

Regionen:

`north`, `central`, `west`, `east`

`blocker_code`:

`completion_below_threshold`, `open_sev1`, `sev2_above_limit`,
`capacity_below_threshold`, `missing_evidence`

`conflicts[].code`:

`preliminary_validation_superseded`,
`aggregate_dashboard_overstates_readiness`

`recommended_actions[].code`:

`launch_north_only`, `hold_blocked_regions`, `correct_dashboard_logic`,
`reassess_after_new_evidence`, `request_exception`

`uncertainties[].code`:

`remediation_completion_dates_unknown`, `post_cutoff_changes_unknown`,
`support_roster_quality_unknown`

## Ausgabeformat

Antworte ausschließlich mit einem JSON-Objekt nach diesem Aufbau. Freitextwerte
müssen auf Deutsch sein. Nutze die exakten `source_ref`-Werte, die das jeweilige
Lesewerkzeug für die belegte Stelle zurückgibt.

```json
{
  "schema_version": "1.0.0",
  "executive_summary": "...",
  "decision": {
    "code": "phased_go",
    "approved_regions": ["north"],
    "blocked_regions": [
      {
        "region": "central",
        "blocker_code": "sev2_above_limit",
        "explanation": "..."
      }
    ]
  },
  "evidence": [
    {
      "fact_code": "...",
      "source_ref": "...",
      "supports": "..."
    }
  ],
  "conflicts": [
    {
      "code": "...",
      "source_refs": ["...", "..."],
      "resolution": "..."
    }
  ],
  "recommended_actions": [
    {"code": "...", "rationale": "..."}
  ],
  "uncertainties": [
    {"code": "...", "reason": "..."}
  ]
}
```

## Prüfkriterien

- [REPORT_SCHEMA] Das JSON entspricht exakt dem vorgegebenen Schema.
- [DECISION] Die Gesamtentscheidung folgt Richtlinie und finaler Evidenz.
- [APPROVED_REGIONS] Die freigegebenen Regionen entsprechen allen Gates.
- [REGION_BLOCKERS] Für jede blockierte Region ist der entscheidende Verstoß korrekt.
- [CITATION_INTEGRITY] Jeder Fakten-Code verweist auf seinen exakten Artefakt-Anker.
- [REQUIRED_EVIDENCE] Alle entscheidungsrelevanten Fakten sind belegt.
- [CROSS_FORMAT_COVERAGE] Word, PDF und Excel tragen jeweils notwendige Evidenz bei.
- [CONFLICT_RESOLUTION] Vorläufige und aggregierte Darstellungen werden korrekt eingeordnet.
- [ACTION_PLAN] Die Mindestmaßnahmen folgen aus Entscheidung und Konflikten.
- [UNCERTAINTY] Nicht belegte zukünftige Entwicklungen bleiben ausdrücklich offen.
- [CONTROLLED_VALUES] Kontrollierte Ergebniswerte stammen ausschließlich aus der sichtbaren Codeliste.

Die deterministische Prüfung bewertet kontrollierte Werte, Beleganker und
Vollständigkeit. Behauptungsrichtung, sprachliche Genauigkeit und Nutzen des
Freitexts werden separat geprüft.
