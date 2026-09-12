# 📄 DocMind AI — Trilingual Document Intelligence & Studio

DocMind AI is an enterprise-grade Document Intelligence and Studio system powered by **Google Gemini** models. It transforms unstructured documents (PDFs, Word docs, Excel sheets, presentations, scanned notices, contracts) into interactive, grounded knowledge with proactive deadline tracking, voice capabilities, and multi-format document augmentation.

---

## 🌟 Key Features

- **Proactive Action & Deadline Detection**: Automatically scans uploaded documents without waiting for a prompt, identifying critical deadlines, urgent action items, and consequences of inaction.
- **Universal Multi-Format Ingestion**: Ingests and parses **PDF** (digital & scanned OCR), **DOCX**, **XLSX**, **CSV**, **PPTX**, **TXT**, and images with automated fallback handling.
- **ChatGPT-Style Modern Workspace**: Floating fixed bottom search capsule with plus `(+)` attachment menu, voice input transcription, and full-screen conversation view.
- **Trilingual English, हिन्दी (Hindi), & ગુજરાતી (Gujarati)**: Native cross-lingual document comprehension, automated language detection, and audio voice readouts.
- **Document Studio**: Prompt-driven document augmentation with real-time export to professionally formatted `.docx` and `.pdf` files.
- **Cross-Document Comparison**: Side-by-side comparative analysis of contracts, quarterly reports, and policy updates.
- **Grounded Verification**: Transparent chunk-level evidence cards with relevance scoring and page references.

---

## 🛠️ Architecture

- **Backend**: FastAPI (port `8000`), Uvicorn, LangChain chunkers, Rank-BM25 hybrid retrieval, ChromaDB vector store.
- **Frontend**: Streamlit (port `8501`) with custom HTML/JS search capsule component.
- **LLM & Embeddings**: Google Gemini Flash / Pro cascade (`gemini-flash-lite-latest`, `gemini-embedding-001`).

---

## 🚀 Quick Start (Local Setup)

### 1. Clone the Repository
```bash
git clone https://github.com/patelDharu/DocMind_AI.git
cd DocMind_AI
```

### 2. Create and Activate Virtual Environment
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-flash-lite-latest
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
```

### 5. Launch the Application
**Terminal 1 — Backend:**
```bash
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```bash
python -m streamlit run frontend/streamlit_app.py
```

Open your browser at `http://localhost:8501`.

---

## 📄 License
This project is licensed under the Apache 2.0 License.
