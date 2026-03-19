# Bewerbungs-Agent Quereinstieg

Multi-Agent-System zur automatischen Erstellung von PM-Bewerbungsunterlagen für Quereinsteiger — powered by Claude (Anthropic API).

**URL rein → fertige Bewerbungs-Markdown raus.**

---

## Was das System macht

1. Scrapt eine Stellenanzeige per URL
2. Analysiert CV und Stelle auf Übereinstimmungen und Lücken
3. Berechnet einen Fit-Score (0–100) mit Empfehlung
4. Übersetzt übertragbare Skills in PM-Sprache
5. Schreibt ein personalisiertes Anschreiben, optimiert den Lebenslauf, erstellt eine Referenzprojekte-Seite
6. Rendert alles als eine zusammenhängende **Markdown**-Datei

Drei Modi:
- **`apply`** — vollständige Bewerbungsunterlagen als **Markdown-Datei**
- **`score`** — nur Fit-Score berechnen, keine Datei
- **`feedback`** — Outcome einer vergangenen Bewerbung nachtragen (sent / interview / rejected / withdrawn)

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
| `writing_samples/*.md` oder `*.txt` | Schreibstilproben — der WriterAgent passt den Anschreiben-Stil daran an |
| `learning/applications.jsonl` | Lernhistorie — wird automatisch angelegt und mit jeder Bewerbung erweitert |

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
| `--output` | `./output` | Ausgabeverzeichnis für die **Markdown-Datei** |
| `--lang [de\|en]` | auto | Sprache manuell überschreiben (sonst automatisch erkannt) |
| `--model` | `claude-sonnet-4-6` | Claude-Modell |
| `--verbose` | — | Detailliertes Agent-Reasoning in der Konsole anzeigen |
| `--open` | — | **Datei** nach Generierung automatisch öffnen |

### `score` — nur Fit-Score (kein Dokument)

```bash
python main.py score --url "https://..." --cv CV-Input.md
```

Flags: `--url`, `--cv`, `--lang`, `--model`, `--verbose` (wie oben, ohne `--output` und `--open`)

### `feedback` — Outcome nachtragen

```bash
# Tabelle der letzten 10 Bewerbungen anzeigen:
python main.py feedback --outcome sent

# Outcome für eine konkrete Bewerbung setzen:
python main.py feedback --id "2026-03-19T14:32:01_acme-product-manager" --outcome interview
```

| Outcome | Bedeutung |
|---|---|
| `sent` | Bewerbung abgeschickt |
| `interview` | Zum Gespräch eingeladen |
| `rejected` | Absage erhalten |
| `withdrawn` | Selbst zurückgezogen |

---

## Output

Die generierte Markdown-Datei wird gespeichert unter:

```
output/{company-title-slug}_score{FIT_SCORE}_application.md
```

Beispiel: `output/webid-solutions-head-of-product_score86_application.md`

Die Datei enthält:
- Anschreiben (1 Seite)
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

Das System läuft in 4 Stufen:

1. **Python Pre-Processing** (kein LLM) — Scraping via `fetch_url` + `extract_text_from_html`, Sprache automatisch erkennen
2. **MegaAnalysisAgent** (1× Sonnet) — Vollständige Analyse, Fit-Score, Skill-Übersetzungen in einem einzigen Call. Erhält ab der 2. Bewerbung automatisch einen kompakten Lernhistorie-Block aus vergangenen Runs
3. **Parallel: WriterAgent** (1× Sonnet) **+ CvReferenzAgent** (1× Haiku) — Anschreiben und CV+Referenzprojekte gleichzeitig generiert. WriterAgent erhält ebenfalls die Lernhistorie
4. **Markdown-Rendering + Persistierung** (kein LLM) — `render_markdown.py` → einzelne `.md`-Datei, danach Analyse in `learning/applications.jsonl` gespeichert

> **4 LLM-Calls pro Bewerbung · ~$0.085/Bewerbung (−66 % vs. vorheriger Architektur)**

---

## Self-Learning Loop

Mit jeder Bewerbung lernt das System dazu. Nach dem ersten Run wird `learning/applications.jsonl` angelegt. Ab dem zweiten Run injiziert das System automatisch einen `## LERNHISTORIE`-Block in MegaAnalysis und WriterAgent — ohne extra LLM-Call, pure Python-Aggregation:

- **Erprobte Übersetzungen** — Skill-Mappings, die bereits als `stark` bewertet wurden (≥ 2× aufgetreten), werden priorisiert wiederverwendet
- **Wiederkehrende Lücken** — Lücken, die in > 25 % der Runs auftauchen, werden proaktiv adressiert
- **K.O.-Kompensationen** — Bewährte Formulierungen werden dedupliziert weitergegeben
- **PM-Archetyp-Häufigkeit** — Zeigt, welche Unternehmenstypen bisher analysiert wurden

Die Lernhistorie bleibt unter 600 Token und ist rein additiv — kein Modell wird fine-getuned, kein Prompt überschrieben.

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
├── main.py                    # CLI-Einstiegspunkt (click): apply / score / feedback
├── requirements.txt
├── .env                       # API Key (nicht einchecken)
├── CV-Input.md                # Dein Lebenslauf (selbst anlegen)
│
├── agents/
│   ├── orchestrator.py        # Koordiniert die volle Pipeline (apply)
│   ├── score_orchestrator.py  # Nur Score-Pipeline (score)
│   ├── mega_analysis_agent.py # Analyse + Fit-Score + Skill-Übersetzungen (1× Sonnet)
│   ├── writer_agent.py        # Anschreiben (1× Sonnet)
│   └── cv_referenz_agent.py   # CV + Referenzprojekte (1× Haiku)
│
├── learning/
│   ├── __init__.py
│   └── application_log.py     # Persistenz + Aggregation für den Self-Learning Loop
│
├── models/
│   └── document.py            # Pydantic-Datenmodelle
│
├── tools/                     # Wiederverwendbare Tool-Funktionen (Scraping, Analyse)
├── utils/
│   ├── config.py              # Konfiguration + Verzeichnis-Konstanten
│   └── render_markdown.py     # Markdown-Rendering → .md-Ausgabedatei
│
├── writing_samples/           # Schreibstilproben (optional, .md oder .txt)
├── jobs/                      # Gescrapte Stellenanzeigen (auto-generiert)
├── learning/applications.jsonl # Lernhistorie (auto-generiert)
└── output/                    # Fertige Markdown-Dateien (auto-generiert)
```
