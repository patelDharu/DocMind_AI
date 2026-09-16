# 📄 DocMind AI — Trilingual Document Intelligence & Studio

[![Live Demo](https://img.shields.io/badge/Live_Demo-DocMind_AI-4f46e5?style=for-the-badge&logo=render&logoColor=white)](https://docmind-ai-dc2h.onrender.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-ff4b4b?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-2.5_Flash-4285f4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003b57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge)](LICENSE)

> **DocMind AI** is an intelligent AI Document Assistant that transforms complex documents (PDFs, scanned images, contracts, Word docs, Excel sheets) into clear, interactive knowledge.
> 
> It automatically flags upcoming deadlines and action items, answers your questions with page-accurate citations, speaks answers aloud in **English, Hindi, and Gujarati**, and gives every user private, **ChatGPT-style chat history** tied to their email.

---

## 🌐 Live Web Application

Try the live deployed version on Render:
👉 **[https://docmind-ai-dc2h.onrender.com](https://docmind-ai-dc2h.onrender.com)**

* **Free Demo Login**: Click the **⚡ Free Demo Sign In** button to test instantly.
* **Or Register Your Account**: Enter your email to have your own private chat history saved automatically.

---

## 💡 Why DocMind AI? (The Problem & Solution)

| The Common Problem | How DocMind AI Solves It |
| :--- | :--- |
| **Complex Legal & Technical Jargon**: Non-technical people (common citizens, doctors, business owners) struggle to read 20-page legal contracts and tax notices. | DocMind explains everything in plain, easy language with clear bullet points. |
| **Missed Deadlines & Penalties**: Important due dates and penalty clauses get buried in fine print. | **Proactive Action Engine**: Scans documents immediately upon upload and warns you about deadlines, action steps, and penalties without you having to ask. |
| **Scanned Image PDFs with Zero Text**: Traditional tools fail on scanned bills and screenshot PDFs. | **Multimodal Vision OCR**: Powered by Google Gemini Vision to read and transcribe even rasterized images, screenshots, and tables. |
| **Language Barrier**: Many people prefer Hindi or Gujarati over English. | **Trilingual Voice & Text**: Ask questions in English, Hindi (हिन्दी), or Gujarati (ગુજરાતી) — via typing or voice — and listen to spoken answers. |
| **Lost Chat History**: Users lose their past work when refreshing or closing the browser. | **Email-Specific History**: Dedicated SQLite storage keeps conversations organized by email ID in a modern **ChatGPT-style sidebar**. |

---

## 🌟 Key Features

### 1. 🔍 Proactive Action & Deadline Detection
As soon as you upload a document, DocMind AI scans the text in the background and highlights:
- 📌 **Does this need action?** (Yes/No)
- ⏰ **Deadline**: Due dates and timeframes
- ⚠️ **Consequences**: Late fees, penalties, legal risks
- 📋 **Next Steps**: Step-by-step checklist of what to do

### 2. 📚 Universal Multi-Format Document Ingestion
Upload virtually any file type:
- **PDFs**: Digital PDFs, scanned documents, and image-based PDFs
- **Word**: .docx, .doc
- **Spreadsheets**: .xlsx, .xls, .csv, .tsv (automatically formats tables into readable markdown)
- **Presentations**: .pptx, .ppt
- **Text & Code**: .txt, .md, .rtf, .log, .json, .yaml, .xml
- **Images**: .png, .jpg, .jpeg, .webp

### 3. 💬 ChatGPT-Style Workspace & Private Chat History
- **Modern Search Capsule**: Clean input bar with attachment (+) menu, voice recording, and trilingual language toggle.
- **Private History by Email**: Conversations are saved to an isolated SQLite database keyed to your email. User A cannot see User B's chats.
- **Sidebar Management**: One-click switching between previous conversations, active chat indicator (🟢), and instant chat deletion (✕).

### 4. 🎙️ Trilingual Voice Input & Audio Readouts
- Speak your questions naturally in **English**, **हिन्दी (Hindi)**, or **ગુજરાતી (Gujarati)**.
- DocMind transcribes your voice, answers the question, and can **read the answer aloud** using high-quality Text-to-Speech (TTS).

### 5. ✍️ Document Studio (AI Document Editor & Export)
- Edit or append new sections to existing documents using natural language instructions.
- Export modified documents on the fly as professionally styled **.docx** or **.pdf** files.

### 6. ⚖️ Multi-Document Comparison
- Select two or more documents to compare terms, pricing, clauses, and differences side-by-side in structured comparison tables.

### 7. 🛡️ Verifiable Source Citations (No Hallucinations)
- Every answer includes expandable **source cards** showing the exact source document, page number, and text snippet so you can verify the truth yourself.

---

## 🛠️ Architecture & Tech Stack

`
DocMind AI Architecture
┌─────────────────────────────────────────────────────────────┐
│                 STREAMLIT FRONTEND (PORT 7860)              │
│   • ChatGPT-Style Sidebar       • Unified Search Capsule     │
│   • Email-Wise History          • Voice Audio Recording      │
│   • Trilingual Voice Readouts   • Document Studio Interface  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / REST API
┌──────────────────────────────▼──────────────────────────────┐
│                  FASTAPI BACKEND (PORT 8000)                │
│   • /upload: Ingestion Pipeline • /ask: Hybrid RAG Search   │
│   • /ask-voice: Whisper/Gemini  • /document/edit: Studio    │
│   • /summarize & /compare       • /health: Service Monitor  │
└──────┬───────────────────────┬───────────────────────┬──────┘
       │                       │                       │
┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
│  EMBEDDINGS │         │   STORAGE   │         │     LLM     │
│  & RETRIEVAL│         │  & SESSIONS │         │  REASONING  │
│ • Gemini    │         │ • SQLite DB │         │ • Gemini    │
│   Embeddings│         │ • ChromaDB  │         │   2.5 Flash │
│ • BM25 Rank │         │ • Users &   │         │ • Proactive │
│ • Hybrid    │         │   Sessions  │         │   Action    │
│   Reranker  │         │   Storage   │         │   Detector  │
└─────────────┘         └─────────────┘         └─────────────┘
`

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Streamlit + Custom HTML/CSS/JS Components | Modern responsive UI, ChatGPT-style sidebar, chat capsule |
| **Backend API** | FastAPI + Uvicorn | High-performance asynchronous REST endpoints |
| **AI Models** | Google Gemini 2.5 Flash / Flash Lite | Multimodal Vision OCR, RAG question answering, proactive analysis |
| **Vector DB** | ChromaDB + Rank-BM25 | Hybrid dense + sparse retrieval for page-accurate search |
| **Chunking** | Pure Python Recursive Chunker | Ultra-lightweight text chunking (saves ~440 MB RAM) |
| **User Data** | SQLite (users.db) | User authentication (salted PBKDF2 hashes) & private chat history |
| **Speech** | Web Audio API / Gemini / gTTS | Voice transcription & trilingual audio playback |
| **Deployment** | Docker + Linux + Render Web Service | Containerized cloud hosting with dynamic port binding |

---

## 🚀 Quick Start (Run on Your Computer)

### Prerequisites
- Python 3.10 or 3.11 installed
- A free **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/)

---

### Method 1: Windows 1-Click Launch (Easiest)

1. Double-click **
un_docmind.bat** (or right-click **
un_docmind.ps1** and select *Run with PowerShell*).
2. The launcher will automatically:
   - Create the Python virtual environment
   - Install all required libraries
   - Start both the FastAPI backend and Streamlit frontend
   - Open your browser at http://localhost:7860

---

### Method 2: Manual Terminal / VS Code Setup

#### 1. Clone the Repository
`ash
git clone https://github.com/patelDharu/DocMind_AI.git
cd DocMind_AI
`

#### 2. Create and Activate Virtual Environment
`ash
# Windows:
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux:
python3 -m venv venv
source venv/bin/activate
`

#### 3. Install Dependencies
`ash
pip install -r requirements.txt
`

#### 4. Configure Your API Key
Create a .env file in the project root:
`env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-flash-lite-latest
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
`

#### 5. Launch the Application

**Terminal 1 — Start the Backend:**
`ash
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
`

**Terminal 2 — Start the Frontend:**
`ash
streamlit run frontend/streamlit_app.py --server.port=7860
`

Open your browser at **http://localhost:7860**!

---

## 📁 Project Structure

`
DocMind_AI/
├── app/
│   ├── api/
│   │   └── main.py              # FastAPI endpoints (/upload, /ask, /summarize, /edit)
│   ├── core/
│   │   ├── auth.py              # SQLite database (Users & Email-Scoped Chat Sessions)
│   │   ├── chunker.py           # Lightweight pure Python text chunker (0MB overhead)
│   │   ├── doc_editor.py        # Document Studio (modifies & exports DOCX/PDF)
│   │   ├── embedder.py          # Google Gemini vector embeddings with retry cascade
│   │   ├── intelligence.py      # Proactive Action/Deadline scanner & Summarizer
│   │   ├── loader.py            # Universal multi-format loader + Gemini Vision OCR
│   │   ├── rag.py               # Master RAG pipeline with Hybrid BM25 + Vector retrieval
│   │   ├── speech.py            # Voice transcription & audio processing
│   │   ├── tts.py               # Trilingual text-to-speech engine (EN/HI/GU)
│   │   └── vectorstore.py       # ChromaDB persistent vector database
│   └── data/                    # Storage for uploads, audio files, and users.db
├── frontend/
│   ├── streamlit_app.py         # Main web UI with ChatGPT sidebar & auth portal
│   └── components/
│       └── chat_bar/            # Custom floating bottom search capsule component
├── sample_documents/            # Ready-to-test sample PDFs, Word files & Excel sheets
├── Dockerfile                   # Docker container specification
├── start.sh                     # Linux container startup script for Render
├── run_docmind.bat              # 1-Click Windows Batch launcher
├── run_docmind.ps1              # 1-Click Windows PowerShell launcher
├── requirements.txt             # Python package dependencies
└── README.md                    # Project documentation
`

---

## 🤝 Contributing

Contributions, feedback, and feature requests are welcome!
1. Fork the repository
2. Create your feature branch (git checkout -b feature/AmazingFeature)
3. Commit your changes (git commit -m 'Add some AmazingFeature')
4. Push to the branch (git push origin feature/AmazingFeature)
5. Open a Pull Request

---

## 📜 License

This project is licensed under the **Apache 2.0 License** — see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

**Dharu Patel**
- GitHub: [@patelDharu](https://github.com/patelDharu)
- Project: [DocMind_AI](https://github.com/patelDharu/DocMind_AI)
- Live Deployment: [DocMind AI on Render](https://docmind-ai-dc2h.onrender.com)
