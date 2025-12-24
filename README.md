# HR Web (Streamlit)

Local paths:
- Database: `data/employees.db`
- Photos: `data/photos/`
- PDFs: `data/pdfs/`

Run locally:
1. Install Python 3.9+
2. Install deps:
   ```powershell
   pip install -r requirements.txt
   ```
3. Start app:
   ```powershell
   streamlit run streamlit_app.py
   ```
4. Open http://localhost:8501

Auth:
- Set admin password with env var `HR_APP_PASSWORD` (default: `917150564pArvinA`).
  ```powershell
  setx HR_APP_PASSWORD "917150564pArvinA"
  ```
- Set viewer password with env var `HR_VIEWER_PASSWORD` (default: `917150564`).
  ```powershell
  setx HR_VIEWER_PASSWORD "917150564"
  ```

- You can also change passwords **in-app** (admin only): open the sidebar while logged in as admin → "Изменить пароль". Note: if an env var is set for a role, it overrides in-app changes.

Deploy (Streamlit Cloud):
- Push this folder to GitHub.
- Create a new Streamlit app from the repo, set `HR_APP_PASSWORD` in app secrets.
- App will read/write under `data/` (persistent if using repo storage or connected volume).
