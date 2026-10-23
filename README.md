# Speech to Text

A web app where you speak (Hindi, English, or Hinglish), see the words appear in real time,
save the transcription to a database, and manage the history from a dashboard (create, read,
update, delete).

## Stack

- **Backend:** Python 3, FastAPI, SQLAlchemy 2, Pydantic 2
- **Database:** SQLite by default (zero setup). PostgreSQL via `DATABASE_URL`.
- **Frontend:** one HTML page with vanilla JavaScript (no build step)
- **Speech to text:** the browser's Web Speech API (streams interim and final results)
- **Text to speech (read back):** the browser's `speechSynthesis`

## Project layout

```
speech-to-text/
├── Dockerfile
├── README.md
└── backend/
    ├── app/main.py          # API, models, database
    ├── static/index.html    # recorder + history dashboard
    ├── tests/test_api.py    # API tests (pytest)
    └── requirements.txt
```

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000 in Chrome or Edge, allow microphone access, and start talking.

## Run the tests

```bash
cd backend
pytest -q
```

## Configuration

| Variable       | Default                          | Purpose                                        |
|----------------|----------------------------------|------------------------------------------------|
| `DATABASE_URL` | `sqlite:///backend/transcriptions.db` | e.g. `postgresql://user:pass@host:5432/db` |
| `PORT`         | `8000`                           | Port used by the Docker image                  |

## Deploy (Render, Railway, or any Docker host)

1. Push this repo to GitHub.
2. Create a **Web Service** from the repo, using the Docker runtime (it reads the `Dockerfile`).
3. Optional: add a PostgreSQL database and set `DATABASE_URL` to its internal URL.
   Without it, SQLite data is lost whenever the container restarts or redeploys.
4. Open the deployed URL over **HTTPS**. Browsers only allow microphone access on HTTPS
   (localhost is the exception).

## Notes and limitations

- **Engine:** live transcription runs in the browser. Chrome and Edge send the audio to their
  speech service. Firefox and most iOS browsers do not support this API, so the page says so.
- **Mixed Hindi and English:** the engine recognizes one language per session. Hindi mode
  handles most Hinglish, but English words may come out in Devanagari or be misheard. The
  transcript is editable before saving.
- **Not self-hosted:** the assignment prefers an open-source self-hosted engine. The
  transcription step is isolated in `startRecording()` in `index.html`, so a server-side engine
  (for example faster-whisper, or a Gemini Live session) can replace it. This is not built yet.
- **Auth:** none. Anyone with the URL can read and edit the transcriptions.
