FROM python:3.6-alpine

LABEL description="ubirch ttn connector"

WORKDIR /connect/

RUN apk update
RUN apk add build-base libffi-dev openssl-dev

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY ttn_connector.py .
COPY ttn_device.py .
COPY mqtt_connection.py .
COPY mprotocol.py .

COPY start.sh .
RUN chmod +x ./start.sh

ENV LOGLEVEL="DEBUG"

CMD ["./start.sh"]
