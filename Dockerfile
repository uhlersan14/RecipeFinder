FROM python:3.13.0

# Arbeitsverzeichnis setzen
WORKDIR /app

# Kopiere das gesamte Projekt
COPY . .

# Installiere Abhängigkeiten
RUN pip install -r requirements.txt

# Setze PYTHONPATH für korrekte Modulimporte
ENV PYTHONPATH=/app

# Setze die Flask-App 
ENV FLASK_APP=backend.app

# Port und Startbefehl
EXPOSE 80
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=80"]