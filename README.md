# FIle-Butler

# Desktop File Butler
A local AI-powered file management agent for macOS that watches your Downloads and Desktop folders, classifies new files, summarizes PDFs, and flags duplicates — all through a browser-based dashboard. Nothing leaves your machine.


# What It Does
File Butler runs quietly in the background and does the tedious work of keeping your folders clean:

- Real-time file watching — Detects new files the moment they hit your Downloads or Desktop folder
- Smart classification — Automatically categorizes files as screenshots, archives, installers, documents, PDFs, and more
- AI-powered PDF summaries — Uses Llama 3 (via Ollama) to read and summarize PDF documents locally
- Duplicate detection — Flags files that already exist so you don't end up with OperaSetup (1).zip situations
- Approve/reject workflow — Nothing gets moved without your permission. You stay in control
- Bulk actions — Approve all or reject all pending suggestions with one click
- Category filters — Filter your event feed by type: suggestions, PDF summaries, duplicates, old files, and more

# How It Works
1. You run python3 butler.py in your terminal
2. File Butler starts a Flask server on localhost:5765 and begins watching your Downloads and Desktop folders
3. When a new file appears, it classifies it and suggests where to move it
4. PDFs get sent to Llama 3 for summarization
5. Open dashboard.html in your browser to see all events and approve/reject suggestions
6. Approved files get moved to their suggested folders. Rejected ones stay put

# Tech Stack
- Python: Core agent logic and file watching
- Flask + Flask-CORS: Local API server handling events and actions from the browser dashboard
- Ollama + Llama 3: Local LLM for PDF analysis and summarization
- watchdog: File system event monitoring
- PyPDF2: PDF text extraction
- Pillow: Image processing and file type detection
- HTML/CSS/JavaScript: Browser-based dashboard UI

# Prerequisites
- macOS (built and tested on Apple Silicon)
- Python 3.10+
- Ollama installed and running
- Llama 3 model pulled (ollama pull llama3)

# Setup
> Clone the repo
- git clone https://github.com/m1l0u/Project_1_File-Butler.git
- cd Project_1_File-Butler

> Install dependencies
- pip install -r requirements.txt

> lMake sure Ollama is running and has Llama 3
- ollama serve
- ollama pull llama3

> Run the agent
- python3 butler.py

# Screenshots
> Browser Dashboard:
The dashboard shows all detected files, their suggested destinations, and lets you approve or reject each action.
<img width="1608" height="1041" alt="Screenshot 2026-04-17 at 2 02 26 PM" src="https://github.com/user-attachments/assets/63c9dbf5-807f-4af1-9490-ac1948212f92" />

>   

> Terminal Backend:
The Python backend connects to Llama 3 via Ollama and starts watching your folders through a Flask server.
<img width="972" height="611" alt="Screenshot 2026-04-17 at 2 01 36 PM" src="https://github.com/user-attachments/assets/e575a1a7-76a4-4c0b-b2df-e77e8c2befae" />



# Why I Built This
My Downloads folder was a disaster. Hundreds of files piling up — screenshots, installers, random PDFs, duplicates of duplicates. I wanted something that would just handle it without me having to think about it, but I also didn't want to give a cloud service access to all my files.
So I built File Butler to run entirely on my machine. No API keys, no cloud, no data leaving my laptop.

# Status
This is a working personal tool that I use daily. It's not packaged for distribution yet, but the code is functional and the dashboard works as shown in the screenshots.

# License
MIT
