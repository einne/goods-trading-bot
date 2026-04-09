FROM python:3.12-slim

WORKDIR /smartsupport-bot
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY database ./database
COPY scripts ./scripts
COPY config.ini ./config.ini

CMD ["python", "app/chatbot.py"]
