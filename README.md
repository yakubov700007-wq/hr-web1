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
- Set password with env var `HR_APP_PASSWORD` (default: `1234`).
  ```powershell
  setx HR_APP_PASSWORD "your_password_here"
  ```

Deploy (Streamlit Cloud):
- Push this folder to GitHub.
- Create a new Streamlit app from the repo, set `HR_APP_PASSWORD` in app secrets.
- App will read/write under `data/` (persistent if using repo storage or connected volume).
