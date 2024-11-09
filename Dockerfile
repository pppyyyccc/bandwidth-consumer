FROM python:3.9-slim

RUN apt-get update && apt-get install -y speedtest-cli

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY speedtest_script.py .

CMD ["python", "speedtest_script.py"]
