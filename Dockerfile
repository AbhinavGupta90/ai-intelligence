FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the feedback bot
# Override with: docker run ... python -m src.main --mode daily
CMD ["python", "run_bot.py"]
