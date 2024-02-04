FROM python:3.9

WORKDIR /app

ADD . .

USER root
RUN apt update
RUN apt install -y streamlink
RUN pip install -r requirements.txt

ENTRYPOINT ["python3", "/app/main.py"]