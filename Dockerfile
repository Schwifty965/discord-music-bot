FROM python:3.11-slim

# ติดตั้ง FFmpeg ในระบบ Linux
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ติดตั้ง Python Packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกไฟล์ทั้งหมด
COPY . .

# สั่งรันบอต
CMD ["python", "bot.py"]
