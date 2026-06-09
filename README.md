# Rasm PDF Bot

Telegram bot for converting images and text to PDF, upscaling images, merging PDFs, compressing PDFs, and smart document scanning.

## Features

| Feature | Description |
|---------|-------------|
| 📝 Text to PDF | Convert any text message to a PDF file |
| 🖼 Image to PDF | Convert single or multiple images to PDF |
| ✨ Image Upscale | Enhance image quality (AI or LANCZOS 2x) |
| 📎 PDF Merge | Combine multiple PDFs into one |
| 🗜 PDF Compress | Reduce PDF file size |
| 📄 Smart Scan | Document scanning with perspective correction |
| 📢 Broadcast | Admin can send messages to all users |
| 🛠 Admin Panel | Statistics, charts, top users |

## Tech Stack

- **Python 3.11+**
- **Aiogram 3.x** — Telegram Bot API framework
- **SQLite** — User and usage data storage
- **Pillow** — Image processing
- **ReportLab** — PDF generation
- **PyPDF2** — PDF merging
- **PyMuPDF (fitz)** — PDF compression
- **OpenCV** — Smart scan, image processing
- **Real-ESRGAN** (optional) — AI image upscaling

## Project Structure

```
rasm_pdf/
├── bot/
│   ├── __init__.py
│   ├── config.py          # Environment configuration
│   ├── database.py        # SQLite operations
│   ├── keyboards.py       # Inline keyboards
│   ├── states.py          # User state management
│   ├── main.py            # Entry point
│   ├── handlers/
│   │   ├── __init__.py    # Router registry
│   │   ├── start.py       # /start command
│   │   ├── text_pdf.py    # Text → PDF
│   │   ├── img_pdf.py     # Image → PDF
│   │   ├── upscale.py     # Image upscale
│   │   ├── merge_pdf.py   # PDF merge
│   │   ├── compress.py    # PDF compression
│   │   ├── smart_scan.py  # Smart scan
│   │   ├── admin.py       # Admin & broadcast
│   │   └── menu.py        # Menu navigation
│   └── utils/
│       ├── __init__.py
│       ├── pdf.py          # PDF utilities
│       ├── image.py        # Image processing
│       ├── chart.py        # Admin charts
│       ├── cleanup.py      # File cleanup worker
│       └── helpers.py      # Common helpers
├── .env.example            # Environment template
├── .gitignore
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Setup

### Prerequisites

- Python 3.11 or higher
- pip

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ZiyodullaOtabaev/rasm_pdf.git
   cd rasm_pdf
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # or
   .venv\Scripts\activate     # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your bot token and settings
   ```

5. **Run the bot:**
   ```bash
   python -m bot.main
   ```

### Docker Setup

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop
docker-compose down
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token from @BotFather | *required* |
| `CHANNEL_USER` | Channel for subscription check | `@xonziyy` |
| `FREE_USES_BEFORE_SUB` | Free uses before requiring subscription | `15` |
| `ADMIN_IDS` | Comma-separated admin Telegram IDs | `""` |
| `MAX_FILE_SIZE` | Maximum file size in bytes | `20971520` (20MB) |
| `DB_PATH` | SQLite database file path | `bot.db` |
| `DOWNLOAD_DIR` | Temporary file directory | `downloads` |
| `ENABLE_REAL_AI` | Enable Real-ESRGAN upscale | `1` |
| `BROADCAST_RATE` | Messages per second for broadcast | `25` |

## Admin Commands

- `/admin` — Admin dashboard with statistics
- `/top` — Top 30 users by usage
- `/broadcast` — Send message to all users

## License

MIT
