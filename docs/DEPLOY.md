# Deploying TigerFish for free

The hosted app shows the saved results in `results/`, `review/` and `docs/` (all committed). It
never reads `cache/`, `data/eias/`, `logs/` or `feedback/`, so nothing gitignored is needed.

- **No key in secrets:** replay only. The app says so on the page, and it makes no model calls.
- **`NEBIUS_API_KEY` in secrets:** a "Live mode" toggle appears. Uploads always get the free
  checks (number pairs, plus species against GBIF if a site is given). Model checks are capped
  (see `tigerfish/hosted.py`): 30 pages per upload, 3 uploads and 3 "Ask the report" questions
  per session, $0.50 per upload, and **$1.00 a day in total** on your key. Visitors can paste
  their own Nebius key. It stays in their browser session only, is never saved or logged, and
  their calls don't count toward your daily $1.00.
- Visitors' reviews (cards and the review queue) stay in their session, and they can download
  them. The committed review decisions are shown read-only and are never changed.

Python: **3.12** (`.python-version`, `runtime.txt`). Dependencies are declared in
`pyproject.toml` and locked in `uv.lock`; `requirements.txt` is a generated runtime-only
export for pip-based hosts. Regenerate it after dependency changes:

```sh
uv export --locked --no-dev --no-hashes --no-emit-project --output-file requirements.txt
```

Theme:
`.streamlit/config.toml` (no secrets in it; secrets go only in the hosting dashboard).

---

## Option A: Streamlit Community Cloud (share.streamlit.io)

Before you start, push `main` to GitHub. The repo must be public, or you must grant Streamlit
access to it.

1. Go to **https://share.streamlit.io** and click **Continue with GitHub**. Authorize
   Streamlit if asked.
2. Top right: click **Create app**.
3. Choose **Deploy a public app from GitHub** (also labelled "Yup, I have an app").
4. Fill in the form:
   - **Repository:** `manya-singh7/tigerfish`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL** (optional): e.g. `tigerfish` → `tigerfish.streamlit.app`
5. Click **Advanced settings**:
   - **Python version:** choose **3.12**. You can only set this here. To change it later
     you have to delete the app and deploy it again.
   - **Secrets:** paste (TOML; leave the box empty for a replay-only demo):
     ```toml
     NEBIUS_API_KEY = "your-nebius-token-factory-key"
     ```
     Optional: `TIGERFISH_HOSTED = "1"`. Hosted mode is also detected automatically on
     Streamlit Cloud.
   - Click **Save**.
6. Click **Deploy**. The first build installs `requirements.txt` and takes a few minutes.
   Follow it under **Manage app** (bottom right of the app) → logs.
7. Check the pages in the top menu (Home, Library, Upload, How it works, Limitations). Open
   Great Nicobar from the library and check its sections: Overview (hero card, top flags),
   Contradictions (badges, highlighted page images), Species & nature (map), Public record
   (key facts vs the official record), Ask & investigate (memo), Quality (review queue),
   Cost & models (scanned pages), and Take action: the letter / RTI downloads after you mark
   a finding **Confirm**.

To change secrets later: open the app's **⋮** menu (or **Manage app**) → **Settings** →
**Secrets**, then save. The app restarts. To update the code, push to `main`; the app
redeploys automatically.

The free tier puts the app to sleep after a few days with no visitors. Anyone who opens it
can click "Yes, get this app back up!" to wake it. The daily spend counter is kept in the
container's temp folder, so a full restart resets it (at most one extra $1.00 that day).

---

## Option B (backup): Hugging Face Spaces

Spaces now runs Streamlit through the Docker SDK.

1. Go to **https://huggingface.co/new-space**. Owner: you. Space name: `tigerfish`.
   License: MIT.
2. **Select the Space SDK:** **Docker**, then template **Streamlit**. Hardware: **CPU basic
   (free)**. Visibility: Public. Click **Create Space**.
3. Push the repo to the Space (replace `<user>`):
   ```bash
   git remote add space https://huggingface.co/spaces/<user>/tigerfish
   git push space main
   ```
   (Use a Hugging Face access token with write permission as the password.) Files over 10 MB
   need Git LFS. None of `results/` is over 2 MB today.
4. The Space needs a `Dockerfile` and a README header. Add them **on the Space only** (for
   example, through the Space's **Files** tab → **Add file**) so the GitHub repo stays as it is:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   ENV TIGERFISH_HOSTED=1
   EXPOSE 8501
   CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
   ```
   At the top of the Space's `README.md`:
   ```yaml
   ---
   title: TigerFish
   sdk: docker
   app_port: 8501
   license: mit
   ---
   ```
5. Optional key: Space **Settings** → **Variables and secrets** → **New secret**: name
   `NEBIUS_API_KEY`, value your key. The Space restarts. Hosted mode is also detected from
   `SPACE_ID`.

---

## Check a clean copy locally (as the host will run it)

```bash
git clone https://github.com/manya-singh7/tigerfish.git tf-clean
cd tf-clean
uv sync --locked --no-dev
TIGERFISH_HOSTED=1 uv run --locked --no-dev streamlit run app.py --server.headless true
```
With no `.env`, the app must open in replay mode with no errors. The commands above use
a POSIX shell; on PowerShell set `$env:TIGERFISH_HOSTED = "1"` before `uv run` instead.
For the browser check, install the dev group and Chromium, then run against the server:
```bash
uv sync --locked
uv run --locked playwright install chromium
uv run --locked python scripts/check_hosted_ui.py http://localhost:8501 shots/
```
