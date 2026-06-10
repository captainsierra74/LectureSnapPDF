# 📸 LectureSnapPDF

**Turn YouTube lectures into AI-ready study material — PDF, Anki, NotebookLM, Gemini, Ollama**

*Stop rewatching lectures. Start studying.*

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green) ![13 Formats](https://img.shields.io/badge/exports-13%20formats-orange) ![Hindi + 9 Indic Scripts](https://img.shields.io/badge/indic_scripts-10-brightgreen) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## What is LectureSnapPDF?

A desktop app that converts YouTube lecture videos into **structured PDF study material + AI-ready exports** by combining video screenshots with transcript context.

> You watch a 3-hour Physics lecture. A month later, exam revision time comes. Do you rewatch the whole thing? Or open a PDF with screenshots, transcript context, keywords, and AI-generated flashcards?

LectureSnapPDF is built for **students preparing for competitive exams** — JEE, NEET, UPSC, SSC CGL, SBI PO, IBPS PO, and others. It handles Hindi/English mixed lectures, 4-hour+ marathon sessions, and runs on 8GB RAM systems.

---

## Why AI loves this app

### Multimodal AI — Visual Transcript PDF

The **Visual Transcript PDF** puts **transcript text at the top** and **screenshot below it** on each page:

```
⏱ 05:30 to 05:45
"So here the BODMAS rule applies when you have multiple operations..."

[FORMULA] [IMPORTANT]

┌─────────────────────────────┐
│                             │
│   screenshot of the board   │
│   showing the BODMAS        │
│   worked example            │
│                             │
└─────────────────────────────┘
```

When you upload this PDF to **Claude, ChatGPT, or Gemini** (multimodal models), the AI reads the **spoken context FIRST**, then sees the **visual content**. This is critical for:

- **Numerical problems**: The board shows the written solution; the transcript captures the teacher's verbal reasoning ("apply conservation of momentum here"). The AI understands both.
- **Formulas & diagrams**: The AI sees the equation AND reads the explanation.
- **Mixed Hindi/English**: Works seamlessly with both scripts.

### NotebookLM — Upload sources, ask questions

Export creates a `notebooklm_sources/` folder. Zip it → upload to [NotebookLM](https://notebooklm.google.com) → ask:

> *"Based on these sources, create a formula sheet grouped by topic"*
> *"Explain the trick at time 5:12 in simple terms"*
> *"Generate 10 practice questions covering all FORMULA-tagged screenshots"*

### Gemini — Paste the optimized text

The Gemini-optimized `.txt` export is formatted for direct pasting:

> *"Here's a screenshot of a physics numerical on projectile motion. The teacher said 'resolve into x and y components.' Read the image, identify given values, and solve step by step."*

### Ollama — Run locally

The Ollama chunks export splits content into context-window-friendly chunks for local LLMs — no data leaves your machine.

---

## How it works

```
Load Video + Paste Transcript  →  Click "Run Capture"  →  Export 13 formats
                                                ↓
                                     (runs in background,
                                      you don't need to play the video)
```

**No video player interaction needed.** The frame engine reads the video file directly in a background thread.

### Step 1: Load + Paste
- Click **Load Video** → select your `.mp4`/`.mkv`/`.avi`
- Click **Paste Transcript** → paste YouTube copy-paste, SRT, VTT, or bracket timestamps
- Or **Load Transcript** from a file

### Step 2: Run Capture
- Select **Speed**: Fast (~1 min per hour of video), Normal (~2 min), Thorough (~5 min)
- Select **Mode**: Smart Auto (recommended — 8 scoring rules), Change Detection, Manual, Hybrid
- Click **▶ Run Capture**
- Progress bar updates — you can walk away

### Step 3: Export
- Click **Export PDF** → choose formats → click **Quick Export** (5 files) or **Export All** (13 formats)
- Files go to `exports/` folder

---

## Numerical Problem Solving (with AI)

This is where LectureSnapPDF shines over generic screenshot tools.

### The problem
A teacher solves a numerical on a whiteboard. The **board** shows:
```
Given: m = 2kg, u = 3m/s, v = 7m/s
Find: F if t = 2s
Solution:
a = (v-u)/t = (7-3)/2 = 2 m/s²
F = ma = 2 × 2 = 4N
```

The **transcript** captures what the teacher says:
> "So here we have mass 2 kilograms, initial velocity 3 meters per second, final velocity 7. First find acceleration using v minus u over t, that gives 2 meters per second squared. Then multiply by mass to get 4 Newtons."

### What LectureSnapPDF captures
- **Screenshot** of the board at the key moment
- **Transcript text** matching that timestamp
- **Visual Transcript PDF** pairing both → AI sees the numbers AND the reasoning

### What you can ask AI
- *"Solve this problem using a different method"*
- *"Give me 5 similar problems with varying difficulty"*
- *"Which formula is being used here? Explain when to use it."*
- *"Create a step-by-step solution guide for problems like this"*

---

## The 13 export formats

| Format | File | Best for |
|--------|------|----------|
| **Full PDF** | `*_full.pdf` | Printing, sharing, manual study |
| **Visual Transcript PDF** ⭐ | `*_visual_transcript.pdf` | **Multimodal AI** — text top, image below |
| Compressed PDF | `*_compressed.pdf` | Email, quick sharing (JPEG quality 60) |
| Split PDFs | `*_part1.pdf` etc. | Chapter-wise / topic-wise study |
| **AI Context .txt** | `*_AI_context.txt` | ChatGPT, Claude, any LLM |
| **Gemini .txt** | `*_gemini.txt` | Google Gemini |
| **Ollama Chunks** | `ollama_chunks/` | Local LLMs (context-window-friendly) |
| **NotebookLM Sources** | `notebooklm_sources/` | **Google NotebookLM** |
| Markdown | `*_study_notes.md` | Obsidian, Notion, GitHub |
| JSON | `*_data.json` | Programmatic / API use |
| CSV Index | `*_index.csv` | Spreadsheets, filtering by tags |
| Clean Transcript | `*_transcript_clean.txt` | Pure text without timestamps |
| **Anki Flashcards** | `*_anki.apkg` | Spaced repetition practice |

---

## Capture modes

| Mode | How it works | Best for |
|------|-------------|----------|
| **Smart Auto** | 8 scoring rules: blank rejection, SSIM dedup, speech delay, keyword scoring, math symbol detection, adaptive gap, forced minimum | Most lectures — best quality automatically |
| **Change Detection** | Samples every 6s, captures on visual change (no transcript needed) | No transcript available |
| **Manual** | Press **C** or click Capture button | Full manual control |
| **Hybrid** | Smart Auto + manual captures | Best of both worlds |

### Speed settings

| Speed | Samples per entry | SSIM dedup | Est. time (1hr) |
|-------|------------------|-----------|-----------------|
| **Fast** | 1 (at 0s) | Skipped | ~30–60 sec |
| **Normal** | 4 (at 0, +4, +8, +12s) | Enabled | ~1–3 min |
| **Thorough** | 7 (every 2s) | Strict | ~3–6 min |

### The 8 Smart Auto rules
1. **Blank rejection** — skips black/white frames and blur
2. **SSIM dedup** — skips near-identical frames
3. **Speech delay compensation** — prefers frames just after new transcript text
4. **Minimum gap** — at least 10s between captures (adapts to 18s for 4h+)
5. **Content scoring** — text density, keyword hits, math symbols
6. **Context window** — attaches surrounding transcript to each capture
7. **Adaptive threshold** — adjusts sensitivity based on burst patterns
8. **Zero-capture floor** — force-captures best frames if <3 captured

---

## Captions & Tags

Each screenshot can have:
- **Caption** — appears under the image in PDF. Pre-populated from transcript.
- **Tags** — QUESTION, FORMULA, TRICK, IMPORTANT, EXAMPLE, DIAGRAM + custom tags
- Tags are exported to CSV and can be used for filtering

---

## Quick Start

### Install

**Windows:**
```cmd
install.bat
```

**Mac/Linux:**
```bash
chmod +x install.sh && ./install.sh
```

**Or manually:**
```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Get a YouTube video + transcript

```bash
pip install yt-dlp

# Download video + auto-generated subtitles
yt-dlp --write-auto-subs --sub-lang en --sub-format srt -o "lecture.%(ext)s" "YOUTUBE_URL"

# Or just the video
yt-dlp -o "lecture.%(ext)s" "YOUTUBE_URL"
```

To paste transcript manually: YouTube → "..." → Show transcript → Copy all → Paste into app.

### First run
1. Open app → **Load Video** → select `.mp4` file
2. **Paste Transcript** or **Load Transcript** from file
3. Select **Smart Auto** + **Normal** speed → **▶ Run Capture**
4. Wait for progress → **Export PDF** → **Quick Export**

---

## Example AI prompts

### For NotebookLM (upload sources folder)

> *"Based on these sources, create a formula sheet grouped by topic. Include the timestamp of each formula."*
>
> *"Create a 30-minute revision plan covering all screenshots tagged IMPORTANT."*
>
> *"Generate 10 multiple-choice questions from the FORMULA-tagged screenshots with answer key."*

### For Gemini / ChatGPT / Claude (upload Visual Transcript PDF)

> *"Screenshot at 5:12 shows a numerical problem. The teacher explains the approach in the transcript text. Solve it step by step and give me 5 similar practice problems."*
>
> *"Extract all formulas from this PDF and create a cheat sheet."*
>
> *"Which concepts are most important for the JEE exam? Rank them by how often they appear in the screenshots."*

### For any AI (paste AI Context .txt)

> *"Summarize this lecture in 5 bullet points."*
>
> *"Create an Anki-style Q&A deck from these screenshots. For each one, write a question (what's shown) and answer (explanation)."*

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `C` | Manual capture |
| `Space` | Play / Pause video |
| `Ctrl+O` | Open video file |
| `Ctrl+S` | Save project |
| `Ctrl+E` | Export PDF |

---

## Settings

| Setting | Description |
|---------|-------------|
| **Sync Offset** | Adjust transcript timing (±60s) |
| **Auto-sync** | Automatically find best offset |
| **Subject** | Subject name (appears on PDF cover) |
| **Min Gap** | Minimum seconds between captures |
| **Score Threshold** | Minimum quality score for capture |
| **Start / End Time** | Limit capture to a time range |

Autosave every 2 minutes with crash recovery on restart.

---

## Project File Format (`.lsnp`)

Save/load entire sessions:
- Video path (with relocation prompt if moved)
- Full transcript data
- All captured screenshots (references, not copies)
- Captions, tags, content scores
- Sync offset, subject, settings

---

## File Structure

```
LectureSnapPDF/
├── main.py                    # Entry point
├── ui_main.py                 # Main window (PyQt5)
├── ui_export_dialog.py        # Export dialog
├── transcript_parser.py       # 5-format transcript parser
├── frame_engine.py            # Frame capture engine (QThread)
├── pdf_builder.py             # 13 export format generators
├── project_manager.py         # Save/load/autosave/recovery
├── font_manager.py            # Noto font download + management
├── ocr_extractor.py           # Optional Tesseract OCR
├── utils.py                   # Shared utilities
├── requirements.txt           # Dependencies
├── install.bat                # Windows installer
├── install.sh                 # Mac/Linux installer
└── tests/                     # 73 tests (all passing)
```

---

## Requirements

- **Python**: 3.10 or later
- **OS**: Windows 10+, macOS 11+, Linux (X11/Wayland)
- **RAM**: 8GB recommended (<800 MB peak usage on 4-hour 4K videos)
- **Disk**: 500MB for app + fonts; additional space for exports
- **Optional**: Tesseract OCR (for automatic captioning from board text)

### Dependencies

```
PyQt5>=5.15.0       # UI framework
opencv-python-headless  # Video processing
numpy>=1.24.0       # Array operations
Pillow>=10.0.0      # Image processing
scikit-image>=0.21.0  # SSIM comparison
reportlab>=4.0.0    # PDF generation
langdetect>=1.0.9   # Language detection
pytesseract>=0.3.10 # OCR (optional)
genanki>=0.13.0     # Anki export
```

---

## Troubleshooting

**"Hindi text shows as boxes in PDF"**
→ Font download may have failed. Re-run: `python -c "from font_manager import FontManager; FontManager().download_fonts()"`
→ The app also falls back to system fonts (Nirmala UI on Windows).

**"QMediaPlayer error: Format not supported"**
→ The video codec isn't supported by Qt. The app falls back to OpenCV frame extraction with static preview. Install K-Lite Codec Pack (Windows) or additional GStreamer plugins (Linux).

**"OpenCV failed to open video"**
→ Ensure the video path has no special characters. Try: `pip install opencv-python-headless` instead of the opencv-python package.

**"Capture only got 1 screenshot"**
→ Make sure the transcript was pasted/loaded correctly. Try **Normal** or **Thorough** speed. Check the status bar for rejection reasons.

**Transcript timestamps don't match video**
→ Settings → Sync Offset → adjust by ±60 seconds or click **Auto-sync**.

---

## License

MIT License. Free for personal and educational use.

## Credits

Built for students preparing for competitive exams in India. Noto Fonts by Google — licensed under SIL Open Font License.
