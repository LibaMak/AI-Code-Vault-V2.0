# Public deployment guide

This app is ready for public deployment on Streamlit Community Cloud.

## Deploy on Streamlit Community Cloud

1. Make sure this GitHub repository is public.
2. Go to <https://share.streamlit.io/> and choose **New app**.
3. Select this repository and branch `main`.
4. Set the main file path to:

```text
streamlit_app.py
```

5. Add secrets in Streamlit Cloud app settings:

```toml
GROQ_API_KEY="your_groq_api_key_here"
GROQ_MODEL="llama-3.3-70b-versatile"
GROQ_FAST_MODEL="llama-3.1-8b-instant"
```

6. Click **Deploy**.

## Local run

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Notes

- Do not commit `.env` or real API keys.
- The PatchDiffGenerator generates patches for the indexed vault copy only. Download generated patches to apply them to a real source checkout.
