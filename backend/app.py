import os
import pickle
from pathlib import Path
import pandas as pd
from azure.storage.blob import BlobServiceClient
from flask import Flask, jsonify, request, send_file, render_template
from flask_cors import CORS
import logging
import sys

# Nach den imports hinzufügen
import pickle
import sys
from model.recipe_model import RecipeRecommender

# Eigene Unpickler-Klasse definieren
class CustomUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if name == 'RecipeRecommender':
            return RecipeRecommender
        return super().find_class(module, name)

# Modifiziere die Funktionen, die das Modell laden
def load_model_safely(file_path):
    with open(file_path, 'rb') as f:
        return CustomUnpickler(f).load()

# Ersetze diesen Block:
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.recipe_model import RecipeRecommender

# Mit diesem:
from pathlib import Path

# Füge das Stammverzeichnis zum Python-Pfad hinzu, falls nötig
root_dir = Path(__file__).parent.parent.absolute()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Dann importiere die RecipeRecommender-Klasse
from model.recipe_model import RecipeRecommender


# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model laden
print("*** Init and load model ***")
model = None

if 'AZURE_STORAGE_CONNECTION_STRING' in os.environ:
    azureStorageConnectionString = os.environ['AZURE_STORAGE_CONNECTION_STRING']
    try:
        blob_service_client = BlobServiceClient.from_connection_string(azureStorageConnectionString)
        print("Fetching blob containers...")
        containers = list(blob_service_client.list_containers(include_metadata=True))
        
        # Filtern nach recipe-model-Containern
        model_containers = [container for container in containers if container.name.startswith("recipe-model")]
        
        if model_containers:
            # Höchste Versionsnummer finden
            suffix = max(int(container.name.split("-")[-1]) for container in model_containers)
            model_folder = f"recipe-model-{suffix}"
            print(f"Using model {model_folder}")
            
            container_client = blob_service_client.get_container_client(model_folder)
            blob_list = list(container_client.list_blobs())
            
            if blob_list:
                blob_name = next(blob.name for blob in blob_list)
                # Download the blob to a local file
                os.makedirs("model", exist_ok=True)
                download_file_path = os.path.join("model", "RecipeRecommender.pkl")
                print(f"Downloading blob to {download_file_path}")
                
                with open(file=download_file_path, mode="wb") as download_file:
                    download_file.write(container_client.download_blob(blob_name).readall())
                    
                # Modell aus Datei laden
                    model = load_model_safely(download_file_path)
                    print("Modell erfolgreich aus Azure Blob Storage geladen")
            else:
                print("Keine Blobs im Container gefunden")
        else:
            print("Keine recipe-model-Container gefunden")
    except Exception as e:
        print(f"Fehler beim Laden aus Azure: {e}")
else:
    print("CANNOT ACCESS AZURE BLOB STORAGE - Please set AZURE_STORAGE_CONNECTION_STRING. Current env: ")
    print(os.environ)

# Stelle sicher, dass wir ein Modell haben
if model is None:
    print("FEHLER: Konnte kein Modell laden!")
    raise Exception("Konnte kein Modell laden. Bitte stelle sicher, dass das Modell in Azure Blob Storage oder lokal verfügbar ist.")

# Initialisiere Flask-App
app = Flask(__name__)
CORS(app)

# Diese Funktion in app.py ersetzen:
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
                
                # Sortiere nach Übereinstimmung (absteigend)
                recommendations = sorted(recommendations, key=lambda x: x['match_percentage'], reverse=True)
                
                # Verarbeite die Zutaten für jedes Rezept
                for rec in recommendations:
                    # Liste für vorhandene Zutaten erstellen
                    available_ingredients = []
                    
                    # Gehe alle Zutaten durch und prüfe, ob sie im Rezept vorkommen
                    user_ingredients_lower = [ing.lower() for ing in user_ingredients]
                    
                    # Für jede Rezeptzutat
                    for ingredient_obj in rec['full_recipe'].get('ingredients', []):
                        if not isinstance(ingredient_obj, dict) or 'ingredient' not in ingredient_obj:
                            continue
                            
                        ingredient_name = ingredient_obj['ingredient'].lower()
                        
                        # Prüfe, ob die Zutat in einer der Benutzerzutaten enthalten ist
                        is_available = False
                        for user_ing in user_ingredients_lower:
                            if user_ing in ingredient_name:
                                is_available = True
                                break
                                
                        if is_available:
                            available_ingredients.append(ingredient_obj)
                    
                    # Füge die Liste der vorhandenen Zutaten zum Rezept hinzu
                    rec['available_ingredients'] = available_ingredients
                
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