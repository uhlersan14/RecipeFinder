# Usage
# docker build -t mosazhaw/hikeplanner .
# docker run --name hikeplanner -e AZURE_STORAGE_CONNECTION_STRING='***' -p 9001:80 -d mosazhaw/hikeplanner

FROM python:3.13.0

# Copy Files
WORKDIR /usr/src/app
COPY backend/app.py /usr/src/app/app.py
COPY backend/static /usr/src/app/static
COPY backend/templates /usr/src/app/templates
COPY model/RecipeRecommender.pkl /usr/src/app/RecipeRecommender.pkl

# Wichtig: Kopiere das komplette model-Modul
COPY model /usr/src/app/model

# Install
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Docker Run Command
EXPOSE 80
ENV FLASK_APP=/usr/src/app/backend/app.py
CMD [ "python", "-m" , "flask", "run", "--host=0.0.0.0", "--port=80"]