# Bewerbungs-Agent Quereinstieg

Multi-Agent-System zur automatischen Erstellung von PM-Bewerbungsunterlagen für Quereinsteiger — powered by Claude (Anthropic API).

**URL rein → fertige Bewerbungs-PDF raus.**

---

## Was das System macht

1. Scrapt eine Stellenanzeige per URL
2. Analysiert CV und Stelle auf Übereinstimmungen und Lücken
3. Berechnet einen Fit-Score (0–100) mit Empfehlung
4. Übersetzt übertragbare Skills in PM-Sprache
5. Schreibt ein personalisiertes Anschreiben, optimiert den Lebenslauf, erstellt eine Referenzprojekte-Seite
6. Rendert alles als ein zusammenhängendes PDF

Zwei Modi:
- **`apply`** — vollständige Bewerbungsunterlagen als PDF
- **`score`** — nur Fit-Score berechnen, kein PDF

---

## Voraussetzungen

- Python 3.10+
- Anthropic API Key

```bash
pip install -r requirements.txt
```

`.env` anlegen (oder `.env.example` kopieren):

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Input-Dateien

### Pflicht

| Datei / Parameter | Beschreibung |
|---|---|
| `CV-Input.md` | Lebenslauf als Markdown (Pfad per `--cv`) |
| `.env` | Anthropic API Key |
| `--url` | URL der Stellenanzeige |

### Optional

| Datei | Beschreibung |
|---|---|
| `photo.png` / `photo.jpg` | Bewerbungsfoto im Projektverzeichnis — wird automatisch erkannt und ins PDF eingefügt |
| `writing_samples/*.md` oder `*.txt` | Schreibstilproben — der WriterAgent passt den Anschreiben-Stil daran an |

---

## Verwendung

### `apply` — vollständige Bewerbung generieren

```bash
python main.py apply --url "https://..." --cv CV-Input.md
```

| Flag | Standard | Beschreibung |
|---|---|---|
| `--url` | (Pflicht) | URL der Stellenanzeige |
| `--cv` | (Pflicht) | Pfad zur CV-Markdown-Datei |
| `--output` | `./output` | Ausgabeverzeichnis für das PDF |
| `--lang [de\|en]` | auto | Sprache manuell überschreiben (sonst automatisch erkannt) |
| `--model` | `claude-sonnet-4-6` | Claude-Modell |
| `--verbose` | — | Detailliertes Agent-Reasoning in der Konsole anzeigen |
| `--open` | — | PDF nach Generierung automatisch öffnen |

### `score` — nur Fit-Score (kein PDF)

```bash
python main.py score --url "https://..." --cv CV-Input.md
```

Flags: `--url`, `--cv`, `--lang`, `--model`, `--verbose` (wie oben, ohne `--output` und `--open`)

---

## Output

Das generierte PDF wird gespeichert unter:

```
output/{company-title-slug}_score{FIT_SCORE}_application.pdf
```

Beispiel: `output/check24-produktmanager-ai_score78_application.pdf`

Das PDF enthält:
- Anschreiben (1 Seite, mit Foto falls vorhanden)
- Lebenslauf (optimiert für die Stelle)
- Referenzprojekte (1 Seite)

Nebenbei wird die gescrapte Stellenanzeige als Markdown in `jobs/` gespeichert.

---

## Fit-Score

Der Score basiert auf der Einordnung jeder Anforderung in eine von fünf Kategorien:

| Kategorie | Punkte | Bedeutung |
|---|---|---|
| `direkt` | 3 Pkt. | Anforderung vollständig erfüllt |
| `übersetzbar` | 1,5 Pkt. | Übertragbare Erfahrung vorhanden |
| `lücke` | 0 Pkt. | Nicht abgedeckt, aber keine K.O.-Anforderung |
| `ko_luecke_kompensiert` | 0,5 Pkt. | K.O.-Anforderung, aber kompensierbar |
| `ko_luecke_unkompensierbar` | 0 Pkt. | K.O.-Anforderung ohne Kompensation |

Der Score wird auf 100 normalisiert. Schwellenwerte:

| Score | Empfehlung |
|---|---|
| ≥ 70 | `bewerben` — direkt bewerben |
| 45–69 | `bewerben_mit_hinweis` — Lücken im Anschreiben adressieren |
| < 45 oder unkompensierbare K.O.-Lücke | `nicht_empfohlen` |

---

## Agent-Pipeline

Das System läuft in 6 Schritten:

1. **ScraperAgent** (`claude-haiku-4-5`) — Scrapt die Stellenanzeige per URL und extrahiert Titel, Unternehmen, Anforderungen als strukturiertes Markdown
2. **AnalyzerAgent** (`claude-sonnet-4-6`) — Analysiert CV und Stelle: erkennt Sprache, mappt Skills, identifiziert Key Selling Points
3. **GapAssessmentAgent** (`claude-sonnet-4-6`) — Berechnet Fit-Score, recherchiert optional die Unternehmenswebsite, erstellt Kompensationsformulierungen für Lücken
4. **SkillTranslationAgent** (`claude-sonnet-4-6`) — Übersetzt übertragbare Skills aus dem Lebenslauf in konkrete PM-Formulierungen
5. **WriterAgent** + **CvAgent** + **ReferenzAgent** (parallel) — Schreibt Anschreiben (Sonnet), optimiert CV-Daten (Haiku), erstellt Referenzprojekte-Seite (Haiku)
6. **PDF-Rendering** — Jinja2-Templates + WeasyPrint → kombiniertes PDF

---

## CV-Format

Die Datei `CV-Input.md` muss als Markdown vorliegen. Der Parser erwartet Abschnitte mit Markdown-Überschriften.

Empfohlene Sektionen:

```markdown
# Vorname Nachname

## Profil
Kurze Zusammenfassung (2–4 Sätze)

## Berufserfahrung

### Jobtitel | Unternehmen | Zeitraum
- Bullet-Point 1
- Bullet-Point 2

## Ausbildung

### Abschluss | Institution | Zeitraum

## Skills
- Kategorie: Skill1, Skill2

## Sprachen
## Zertifikate
## Publikationen
```

Berufserfahrung sollte als Bullet-Points pro Stelle formatiert sein — der Analyzer extrahiert diese als konkrete Belege für Skill-Übersetzungen.

---

## Projektstruktur

```
.
├── main.py                    # CLI-Einstiegspunkt (click)
├── requirements.txt
├── .env                       # API Key (nicht einchecken)
├── CV-Input.md                # Dein Lebenslauf (selbst anlegen)
├── photo.png / photo.jpg      # Bewerbungsfoto (optional)
│
├── agents/
│   ├── orchestrator.py        # Koordiniert die volle Pipeline (apply)
│   ├── score_orchestrator.py  # Nur Score-Pipeline (score)
│   ├── scraper_agent.py       # Stellt Webseiten als Markdown bereit
│   ├── analyzer_agent.py      # CV + Stelle → strukturierte Analyse
│   ├── gap_assessment_agent.py # Fit-Score + Empfehlung
│   ├── skill_translation_agent.py # Skill-Übersetzungen
│   ├── writer_agent.py        # Anschreiben
│   ├── cv_agent.py            # Lebenslauf-Daten
│   └── referenz_agent.py      # Referenzprojekte
│
├── models/
│   └── document.py            # Pydantic-Datenmodelle
│
├── pdf/
│   ├── renderer.py            # WeasyPrint-Rendering
│   └── templates/             # Jinja2-HTML + CSS pro Dokument
│
├── tools/                     # Wiederverwendbare Tool-Funktionen (Scraping, Analyse)
├── utils/                     # Config, Markdown-Parser
│
├── writing_samples/           # Schreibstilproben (optional, .md oder .txt)
├── jobs/                      # Gescrapte Stellenanzeigen (auto-generiert)
└── output/                    # Fertige PDFs (auto-generiert)
```
