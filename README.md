# RecipeFinder

inspired by https://www.swissmilk.ch/de/rezepte-kochideen/

## Spider

* Scrape regularly for new / additional data
* Output output.jl (json list)
* Load data into MongoDB
* Save model to model/RecipeRecommender.pkl

## Azure Blob Storage

* Save model to Azure Blob Storage
* Always save new version of model
* Zugriff: Speicherkonto > Zugriffsschlüssel
    * Als Umgebungsvariable für Docker
    * Als Secret für GitHub

## GitHub Action

* Scrape
* Load data to MongoDB (Azure Cosmos DB)
* Update model and save to Azure Blob Storage

## App
* Backend: Python Flask (backend/app.py)
* Frontend: html, css and JS (build still manually)

## Deployment with Docker

* Dockerfile
* Install dependencies with pip
* Copy Frontend (prebuilt, TODO Build)
* Azure Blob Storage: Zugriffsschlüssel als Umgebungsvariable

## Update Requirements

* Delete requirements.txt
* Create .venv
* pip install -r dev-requirements.in
* pip-compile requirements.in
* pip install -r requirements.txt

## Ideas

* Personalized Model
    * For a specific Recipes
rs 
