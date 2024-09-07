FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && rm -rf /requirements.txt /tmp/* /var/tmp/*


COPY . /app
WORKDIR /app
VOLUME /config

ENTRYPOINT ["python", "./qbit_helper.py"]
