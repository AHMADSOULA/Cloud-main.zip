FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ✅ زيادة الذاكرة المشتركة (shm) لحل مشكل Page crashed
# (في Railway، استعمل إعدادات shm_size في dashboard إن أمكن، أو استعمل هذا الحل الاحتياطي)
RUN echo "none /dev/shm tmpfs defaults,size=512m 0 0" >> /etc/fstab || true

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
