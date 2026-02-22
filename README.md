# Google Drive File Copy

A Streamlit web app to copy selected files from one Google Drive folder to another. Use the full folder structure to pick source and destination, browse and select files (or type names), then run the copy. Source files are unchanged; the app creates new copies in the destination folder.

---

## Features

- **Full folder structure** – Select source and destination by full path (e.g. `My Drive (root) / card2 / subfolder`). The dropdown shows the complete hierarchy so you always pick the right folder.
- **Browse and select files** – Load the list of files in the source folder and select which to copy from a searchable list. No need to type exact names.
- **Filter by name** – Narrow the file list by typing part of a filename (e.g. `7B1A` or `.JPG`). Case-insensitive.
- **Refresh file list** – Reload files from the source folder so newly added files appear.
- **Type names (optional)** – You can still enter comma-separated file names. Matching is case-insensitive; base-name matching is supported (e.g. `7B1A0431` matches `7B1A0431.JPG`).
- **My Drive root** – You can select “My Drive (root)” to copy files that live in the root of My Drive (not inside any folder).
- **Duplicate names** – Folders or files with the same name are shown with a (2), (3) suffix so each selection maps to the correct item.
- **TLS 1.2+ and SSL fixes** – The app forces TLS 1.2+ and uses a requests-based transport to avoid `[SSL: WRONG_VERSION_NUMBER]` on some networks or with proxies/antivirus.
- **Pagination** – All folders and all files in a folder are loaded (Drive API allows 1000 per page; the app fetches every page).

---

## Prerequisites

- **Python 3.7+** (3.8+ recommended)
- A **Google Cloud project** with the **Google Drive API** enabled and **OAuth 2.0 Desktop application** credentials

---

## Google Cloud setup

1. **Create a project** (or use an existing one) in [Google Cloud Console](https://console.cloud.google.com/).

2. **Enable the Google Drive API**
   - Go to **APIs & Services** → **Library**.
   - Search for **Google Drive API** and enable it.

3. **Create OAuth 2.0 credentials**
   - Go to **APIs & Services** → **Credentials**.
   - Click **Create Credentials** → **OAuth client ID**.
   - If prompted, configure the **OAuth consent screen** (e.g. External, add your email as a test user).
   - Choose **Desktop application** as the application type (required for this app).
   - Click **Create** and download the JSON key.

4. **Save the credentials file**
   - Rename the downloaded file to `credentials.json`.
   - Place it in the project root (same folder as `app.py`).
   - **Do not commit** this file; add it to `.gitignore` if you use git.

---

## Run without virtual environment

Use this when you want to run the app with your system Python and do not want to create or activate a venv.

1. **Open a terminal** in the project folder (where `app.py` and `requirements.txt` are).

2. **Install dependencies** (system-wide):
   ```bash
   pip install -r requirements.txt
   ```
   On some systems you may need:
   ```bash
   pip3 install -r requirements.txt
   ```
   Or, if you prefer to install only for your user:
   ```bash
   pip install --user -r requirements.txt
   ```

3. **Run the app**:
   ```bash
   streamlit run app.py
   ```
   Or:
   ```bash
   python -m streamlit run app.py
   ```
   If you have both Python 2 and 3, use:
   ```bash
   python3 -m streamlit run app.py
   ```

4. **First run**
   - The app opens in your browser (often `http://localhost:8501`).
   - If you are not signed in, click **Connect Google Drive** and complete sign-in and consent in the browser.
   - After authorizing, `token.json` is created in the project root; you won’t need to sign in again until it expires.

5. **Stop the app**  
   Press **Ctrl+C** in the terminal. Streamlit may take a few seconds to shut down.

---

## Run with virtual environment (recommended)

Using a venv keeps project dependencies separate from the rest of your system.

1. **Create a virtual environment** in the project folder:
   ```bash
   python -m venv venv
   ```
   On some systems:
   ```bash
   python3 -m venv venv
   ```

2. **Activate it**
   - **Windows (Command Prompt):** `venv\Scripts\activate`
   - **Windows (PowerShell):** `venv\Scripts\Activate.ps1`
   - **macOS/Linux:** `source venv/bin/activate`
   You should see `(venv)` in the prompt.

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**:
   ```bash
   streamlit run app.py
   ```
   Or use the launcher (if `run_app.py` exists) for quicker shutdown on Ctrl+C:
   ```bash
   python run_app.py
   ```

5. **Deactivate when done** (optional): `deactivate`

---

## Usage

1. **Source folder** – In the dropdown, select the folder that contains the files you want to copy. The list shows the full path (e.g. `My Drive (root) / card2`). Use **Refresh file list** after changing the folder if the file list was already loaded.

2. **Choose files**
   - **Browse and select (recommended):** With “Browse and select from folder” checked, the app lists files in the source folder. Use **Filter by name** to narrow the list, then select one or more files. Click **Refresh file list** if you don’t see all files or added new ones.
   - **Or type names:** Uncheck “Browse and select” and enter file names in the text area, comma-separated (e.g. `report.pdf, 7B1A0431.JPG`). Matching is case-insensitive; you can use the base name (e.g. `7B1A0431` for `7B1A0431.JPG`).

3. **Destination folder** – Select the folder where copies should be created (same path-style dropdown).

4. Click **Copy files**. The app copies the selected or matched files to the destination and shows progress. Source files are not modified.

---

## Project structure

| File / folder        | Purpose |
|----------------------|--------|
| `app.py`             | Streamlit UI: folder selection, file browse/select, filter, copy flow. |
| `drive_service.py`   | Drive API: auth, folder tree, list files, copy, name resolution. TLS/SSL and requests-based HTTP. |
| `run_app.py`         | Optional launcher; stops quickly on Ctrl+C. |
| `requirements.txt`   | Python dependencies (Streamlit, Google API client, auth libs). |
| `credentials.json`   | Your OAuth Desktop client JSON (you add this; do not commit). |
| `token.json`         | Created after first sign-in; used for subsequent runs (do not commit). |

---

## Troubleshooting

**“No files matched” / “Not found: filename”**
- Ensure the **source folder** is the one that actually contains the file (use the full-path dropdown).
- If using “Browse and select”, click **Refresh file list** so the list matches the current folder.
- If typing names, try the base name (e.g. `7B1A0431` for `7B1A0431.JPG`) or check spelling and commas.

**List doesn’t match files in the folder**
- If you have several folders with the same name, pick the correct path in the dropdown (e.g. `… / card2` vs `… / card2  (2)`).
- Click **Refresh file list** after changing the source folder.

**[SSL: WRONG_VERSION_NUMBER] / “Failed to list folders”**
- The app is built to use TLS 1.2+ and a requests-based transport. If the error persists:
  - Try running with no proxy: e.g. `set NO_PROXY=*` (Windows) then `streamlit run app.py`.
  - Temporarily disable “HTTPS scanning” or “Web protection” in antivirus/security software.
  - Try another network (e.g. mobile hotspot) to rule out corporate proxy/firewall.

**Error 401: invalid_client**
- The app needs **Desktop application** OAuth credentials, not Web application.
- In Google Cloud Console: **APIs & Services** → **Credentials** → Create **OAuth client ID** → choose **Desktop application** → download the JSON.
- Replace `credentials.json` with that file (it must contain an `"installed"` section, not only `"web"`).

**Python not found / wrong version**
- Install Python 3.7+ from [python.org](https://www.python.org/downloads/) or your package manager.
- Use `python --version` or `python3 --version` to confirm. On Windows, you may need to use `py -3` or add Python to PATH.

---

## Security

- Keep `credentials.json` and `token.json` private. Do not commit them or share them.
- Use a Desktop OAuth client only for local use. For a public or hosted app, use a Web application client and proper redirect URIs.
