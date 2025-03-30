# backend/app.py
import sys
import os
import logging
import json
from dotenv import load_dotenv

load_dotenv()

# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Füge das Root-Verzeichnis (eine Ebene höher) zum Python-Pfad hinzu
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, render_template, request, jsonify
from model.recipe_model import RecipeRecommender

app = Flask(__name__)

# MongoDB-Verbindungs-URL aus Umgebungsvariablen zusammenbauen
MONGO_USERNAME = os.getenv('MONGO_USERNAME')
MONGO_PASSWORD = os.getenv('MONGO_PASSWORD')
MONGO_HOST = os.getenv('MONGO_HOST')
MONGO_DATABASE = os.getenv('MONGO_DATABASE')

# Erstelle die Mongo URI aus den Umgebungsvariablen
MONGO_URI = f'mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOST}/{MONGO_DATABASE}?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000'

# Modellpfad
MODEL_PATH = '../RecipeRecommender.pkl'

# Lade oder erstelle das Modell
try:
    # Versuche, ein vorhandenes Modell zu laden
    logger.info(f"Versuche, Modell aus {MODEL_PATH} zu laden...")
    model = RecipeRecommender.load_model(MODEL_PATH)
    
    # Stelle sicher, dass das Modell alle notwendigen Attribute hat
    # Wenn classifier nicht vorhanden ist, führe preprocess_data aus
    if not hasattr(model, 'classifier') or model.classifier is None:
        logger.info("Modell geladen, aber Klassifikator fehlt. Führe preprocess_data aus...")
        model.load_data()  # Stelle sicher, dass Daten geladen sind
        model.preprocess_data()
        # Modell nach der Aktualisierung speichern
        model.save_model(MODEL_PATH)
        logger.info("Modell aktualisiert und gespeichert.")
    
except FileNotFoundError:
    # Wenn kein Modell existiert, erstelle ein neues und speichere es
    logger.info("Kein vorhandenes Modell gefunden. Erstelle ein neues Modell...")
    model = RecipeRecommender(MONGO_URI)
    model.load_data()
    model.preprocess_data()
    # Evaluiere das Modell
    metrics = model.evaluate_model()
    logger.info(f"Modellmetriken: {metrics}")
    model.save_model(MODEL_PATH)
except Exception as e:
    logger.error(f"Fehler beim Laden des Modells: {e}")
    # Fallback ohne Verbindung zur Datenbank
    model = None

@app.route('/', methods=['GET', 'POST'])
def index():
    """Hauptseite für die Rezeptempfehlungen."""
    recommendations = []
    user_ingredients = []
    suggestions = []
    error_message = None

    if model is None:
        error_message = "Das Rezeptempfehlungsmodell konnte nicht geladen werden. Bitte versuchen Sie es später erneut."
        return render_template('index.html', error_message=error_message)

    if request.method == 'POST':
        try:
            # Hole die eingegebenen Zutaten aus dem Formular
            ingredients_input = request.form.get('ingredients', '')
            user_ingredients = [ing.strip() for ing in ingredients_input.split(',') if ing.strip()]

            if user_ingredients:
                # Empfehle Rezepte basierend auf den eingegebenen Zutaten
                recommendations = model.recommend(user_ingredients, top_n=5)
                logger.info(f"{len(recommendations)} Rezepte für {user_ingredients} empfohlen")
            else:
                logger.warning("Keine Zutaten eingegeben")

            # Hole Zutaten-Vorschläge, falls ein Suchbegriff eingegeben wurde
            search_term = request.form.get('search_ingredient', '')
            if search_term:
                suggestions = model.suggest_ingredients(search_term, max_suggestions=5)
                logger.info(f"{len(suggestions)} Vorschläge für '{search_term}' gefunden")
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung der Anfrage: {e}")
            error_message = f"Bei der Verarbeitung Ihrer Anfrage ist ein Fehler aufgetreten: {str(e)}"

    return render_template('index.html', 
                          recommendations=recommendations, 
                          user_ingredients=user_ingredients, 
                          suggestions=suggestions,
                          error_message=error_message)

@app.route('/api/suggestions', methods=['GET'])
def get_suggestions():
    """API-Endpunkt für Zutatvorschläge (für AJAX-Anfragen)."""
    if model is None:
        return jsonify({"error": "Modell nicht verfügbar"}), 500
        
    search_term = request.args.get('term', '')
    if not search_term or len(search_term) < 2:
        return jsonify([])
        
    try:
        suggestions = model.suggest_ingredients(search_term, max_suggestions=8)
        return jsonify(suggestions)
    except Exception as e:
        logger.error(f"Fehler bei der Suche nach Zutatenvorschlägen: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/recommend', methods=['POST'])
def recommend_recipes():
    """API-Endpunkt für Rezeptempfehlungen (für AJAX-Anfragen)."""
    if model is None:
        return jsonify({"error": "Modell nicht verfügbar"}), 500
        
    try:
        data = request.get_json()
        if not data or 'ingredients' not in data:
            return jsonify({"error": "Keine Zutaten übermittelt"}), 400
            
        ingredients = data['ingredients']
        limit = data.get('limit', 5)
        
        if not ingredients:
            return jsonify({"error": "Leere Zutatenliste"}), 400
            
        recommendations = model.recommend(ingredients, top_n=limit)
        
        # Konvertiere MongoDB ObjectIds für JSON-Serialisierung
        for rec in recommendations:
            if '_id' in rec['full_recipe']:
                rec['full_recipe']['_id'] = str(rec['full_recipe']['_id'])
                
        return jsonify({"recommendations": recommendations})
    except Exception as e:
        logger.error(f"Fehler bei der Rezeptempfehlung: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Einfacher Health-Check-Endpunkt für die Anwendung."""
    if model is None:
        return jsonify({"status": "error", "message": "Modell nicht verfügbar"}), 500
    return jsonify({"status": "ok", "message": "Anwendung läuft"}), 200

if __name__ == "__main__":
    # Für Entwicklungszwecke
    app.run(debug=True)