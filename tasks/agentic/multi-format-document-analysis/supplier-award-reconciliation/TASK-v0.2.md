# Aufgabe: Lieferantenzuschlag aus drei Dokumentformaten beurteilen

Du berätst das Sourcing Committee bei der Vergabe eines geschäftskritischen
Servicevertrags. Im Arbeitsverzeichnis liegen drei schreibgeschützte Artefakte:
eine Word-Richtlinie, ein PDF mit der Assurance-Prüfung und eine
Excel-Arbeitsmappe mit Angeboten, Kapazitäten und einem kommerziellen Dashboard.

Untersuche die Dokumente gezielt und entscheide auf Basis des im Dossier
genannten Stichtags:

- ob eine Vergabe mit Reserve, nur eine Einzelvergabe oder keine Vergabe
  zulässig ist;
- welcher zulässige Lieferant den Primärzuschlag erhält;
- welcher zulässige Lieferant als Reserve vorgesehen wird;
- welcher entscheidende Gate-Verstoß jeden ausgeschlossenen Lieferanten stoppt;
- wie widersprüchliche, vorläufige oder unvollständige Empfehlungen aufzulösen
  sind;
- welche Maßnahmen und Unsicherheiten für das Sourcing Committee wichtig sind.

Verwende ausschließlich Evidenz aus den bereitgestellten Artefakten. Wende die
Reihenfolge der Richtlinie exakt an: zuerst die Zulässigkeit prüfen, danach nur
die zulässigen Lieferanten anhand der maßgeblichen Kostenkennzahl ordnen. Ein
kommerzielles Ranking darf Assurance- oder Kapazitäts-Gates nicht ersetzen.
Neuere und ausdrücklich unterzeichnete Evidenz kann einen Entwurf ersetzen.
Rechne erforderliche Kennzahlen nach und prüfe dabei Werte und Formeln.

## Sichtbare Codes

`decision.code`:

`award_with_reserve`, `single_award`, `no_award`, `insufficient_evidence`

Lieferanten:

`atlas`, `boreal`, `cedar`, `delta`, `none`

`blocker_code`:

`assurance_rating_below_threshold`, `unresolved_critical_finding`,
`capacity_headroom_below_threshold`, `cost_above_ceiling`, `missing_evidence`

`conflicts[].code`:

`draft_assurance_superseded`,
`commercial_dashboard_ignores_assurance`

`recommended_actions[].code`:

`award_atlas`, `designate_boreal_reserve`, `exclude_ineligible_suppliers`,
`correct_dashboard_scope`, `reassess_after_new_evidence`, `negotiate_fees`

`uncertainties[].code`:

`post_cutoff_assurance_changes_unknown`,
`capacity_forecast_variance_unknown`, `contract_execution_status_unknown`

## Ausgabeformat

Antworte ausschließlich mit einem JSON-Objekt nach diesem Aufbau. Freitextwerte
müssen auf Deutsch sein. Nutze die exakten `source_ref`-Werte, die das jeweilige
Lesewerkzeug für die belegte Stelle zurückgibt.

```json
{
  "schema_version": "2.0.0",
  "executive_summary": "...",
  "decision": {
    "code": "award_with_reserve",
    "primary_supplier": "atlas",
    "reserve_supplier": "boreal",
    "rejected_suppliers": [
      {
        "supplier": "cedar",
        "blocker_code": "unresolved_critical_finding",
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
- [DECISION] Die Vergabeart folgt Richtlinie und finaler Evidenz.
- [PRIMARY_SUPPLIER] Der Primärlieferant ist der günstigste zulässige Kandidat.
- [RESERVE_SUPPLIER] Die Reserve ist der nächstgünstigste zulässige Kandidat.
- [SUPPLIER_BLOCKERS] Jeder Ausschluss trägt den entscheidenden Gate-Verstoß.
- [CITATION_INTEGRITY] Jeder Fakten-Code verweist auf seinen exakten Artefakt-Anker.
- [REQUIRED_EVIDENCE] Zulässigkeit, Rangfolge und Konflikte sind vollständig belegt.
- [CROSS_FORMAT_COVERAGE] Word, PDF und Excel tragen jeweils notwendige Evidenz bei.
- [CONFLICT_RESOLUTION] Entwurf und kommerziell unvollständige Empfehlung werden korrekt eingeordnet.
- [ACTION_PLAN] Die Mindestmaßnahmen folgen aus Auswahl und Konflikten.
- [UNCERTAINTY] Nicht belegte zukünftige Entwicklungen bleiben ausdrücklich offen.
- [CONTROLLED_VALUES] Kontrollierte Ergebniswerte stammen ausschließlich aus der sichtbaren Codeliste.

Die deterministische Prüfung bewertet kontrollierte Werte, Beleganker und
Vollständigkeit. Behauptungsrichtung, sprachliche Genauigkeit und Nutzen des
Freitexts werden separat geprüft.
