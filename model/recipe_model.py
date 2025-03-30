# model/recipe_model.py
# Verbessertes Modell zum Empfehlen von Rezepten basierend auf vorhandenen Zutaten

import sys
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import pickle
import re
import os
from pymongo import MongoClient
import logging
from dotenv import load_dotenv

load_dotenv()

# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RecipeRecommender:
    def __init__(self, mongo_uri, db_name='recipes', collection_name='tracks'):
        """
        Initialisiert das Rezeptempfehlungsmodell mit einer MongoDB-Verbindung.

         Args:
            mongo_uri (str): MongoDB-Verbindungs-URL. Falls None, wird aus Umgebungsvariablen aufgebaut.
            db_name (str): Name der Datenbank (Standard: 'recipes').
            collection_name (str): Name der Collection (Standard: 'recipes').
        """
        if mongo_uri is None:
            # Baue die URI aus Umgebungsvariablen
            MONGO_USERNAME = os.getenv('MONGO_USERNAME')
            MONGO_PASSWORD = os.getenv('MONGO_PASSWORD')
            MONGO_HOST = os.getenv('MONGO_HOST')
            MONGO_DATABASE = os.getenv('MONGO_DATABASE', 'recipes')
            
            self.mongo_uri = f'mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOST}/{MONGO_DATABASE}?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000'
        else:
            self.mongo_uri = mongo_uri
            
        self.db_name = db_name
        self.collection_name = collection_name
        self.recipes = None
        self.vectorizer = None
        self.ingredients_matrix = None
        self.ingredient_names = set()
        self.client = None
        self.db = None
        self.collection = None
        self.classifier = None
        self.train_recipes = None
        self.test_recipes = None
        self.category_map = {}
        self.reverse_category_map = {}

    def connect(self):
        """Stellt die Verbindung zu MongoDB her."""
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            logger.info("Verbindung zu MongoDB hergestellt")
        except Exception as e:
            logger.error(f"Fehler bei der Verbindung zu MongoDB: {e}")
            raise

    def load_data(self):
        """Lädt die Rezeptdaten aus MongoDB."""
        self.connect()
        # Lade alle Rezepte aus der Collection
        recipes = list(self.collection.find())
        self.client.close()

        if not recipes:
            logger.error("Keine Rezepte in der MongoDB-Collection gefunden.")
            raise ValueError("Keine Rezepte in der MongoDB-Collection gefunden.")

        # Konvertiere die Liste von Rezepten in einen DataFrame
        self.recipes = pd.DataFrame(recipes)

        # Extrahiere alle einzigartigen Zutaten
        for recipe in recipes:
            for ingredient_obj in recipe.get('ingredients', []):
                if isinstance(ingredient_obj, dict) and 'ingredient' in ingredient_obj:
                    ingredient_name = ingredient_obj['ingredient'].lower()
                    # Entferne Kommentare in Klammern für die Zutatenerkennung
                    ingredient_name = re.sub(r'\([^)]*\)', '', ingredient_name).strip()
                    # Entferne Zusatzinformationen nach Komma für Basiszutat
                    base_ingredient = ingredient_name.split(',')[0].strip()
                    self.ingredient_names.add(base_ingredient)

        logger.info(f"Daten geladen: {len(self.recipes)} Rezepte mit {len(self.ingredient_names)} einzigartigen Zutaten")
        return self

    def preprocess_data(self):
        """Bereitet die Daten für die Analyse vor und teilt den Datensatz."""
        if self.recipes is None:
            logger.error("Daten wurden nicht geladen. Rufen Sie zuerst load_data() auf.")
            raise ValueError("Daten wurden nicht geladen. Rufen Sie zuerst load_data() auf.")

        # Prüfe, ob 'ingredients' als Spalte existiert
        if 'ingredients' not in self.recipes.columns:
            logger.error("Spalte 'ingredients' fehlt im DataFrame")
            raise ValueError("Spalte 'ingredients' fehlt im DataFrame")

        # Erstelle einen String mit allen Zutaten pro Rezept
        self.recipes['ingredients_text'] = self.recipes['ingredients'].apply(
            lambda ingredients_list: ' '.join([
                re.sub(r'\([^)]*\)', '', ingredient_obj['ingredient']).split(',')[0].strip().lower()
                for ingredient_obj in ingredients_list
                if isinstance(ingredient_obj, dict) and 'ingredient' in ingredient_obj
            ])
        )

        # Extrahiere Kategorien aus den Rezepten (falls vorhanden) für die Klassifikation
        if 'category' in self.recipes.columns:
            self.recipes['category'] = self.recipes['category'].fillna('Sonstiges')
        else:
            # Wenn keine Kategorie vorhanden ist, erstelle eine einfache basierend auf Zutaten
            def assign_category(ingredients_text):
                if 'mehl' in ingredients_text and ('zucker' in ingredients_text or 'schokolade' in ingredients_text):
                    return 'Gebäck'
                elif 'fleisch' in ingredients_text or 'huhn' in ingredients_text or 'rind' in ingredients_text:
                    return 'Fleischgerichte'
                elif 'fisch' in ingredients_text or 'lachs' in ingredients_text:
                    return 'Fischgerichte'
                elif 'gemüse' in ingredients_text or 'tomate' in ingredients_text or 'salat' in ingredients_text:
                    return 'Gemüsegerichte'
                else:
                    return 'Sonstiges'
            
            self.recipes['category'] = self.recipes['ingredients_text'].apply(assign_category)
        
        # Erzeuge eine Zuordnung von Kategorie zu numerischen Werten
        categories = sorted(self.recipes['category'].unique())
        self.category_map = {cat: idx for idx, cat in enumerate(categories)}
        self.reverse_category_map = {idx: cat for idx, cat in enumerate(categories)}
        self.recipes['category_id'] = self.recipes['category'].map(self.category_map)

        # Teile die Daten in Trainings- und Testdaten
        self.train_recipes, self.test_recipes = train_test_split(
            self.recipes, test_size=0.2, random_state=42
        )
        
        logger.info(f"Daten in Trainings- ({len(self.train_recipes)} Rezepte) und Testdaten ({len(self.test_recipes)} Rezepte) aufgeteilt")

        # Erstelle eine Term-Frequency-Inverse-Document-Frequency-Matrix (TF-IDF)
        # Dies gewichtet wichtigere Zutaten stärker als häufig vorkommende
        self.vectorizer = TfidfVectorizer(min_df=2)  # Ignoriere Zutaten, die nur in einem Rezept vorkommen
        self.train_ingredients_matrix = self.vectorizer.fit_transform(self.train_recipes['ingredients_text'])
        self.test_ingredients_matrix = self.vectorizer.transform(self.test_recipes['ingredients_text'])

        # Trainiere einen RandomForest-Klassifikator zur Kategorisierung von Rezepten
        self.train_classifier()

        logger.info("Daten vorverarbeitet und Modelle erstellt")
        return self
    
    def train_classifier(self):
        """Trainiert einen Klassifikator zur Vorhersage der Rezeptkategorie."""
        if self.train_recipes is None or 'category_id' not in self.train_recipes.columns:
            logger.error("Trainingsdaten nicht vorbereitet. Rufen Sie zuerst preprocess_data() auf.")
            raise ValueError("Trainingsdaten nicht vorbereitet. Rufen Sie zuerst preprocess_data() auf.")
        
        self.classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.classifier.fit(self.train_ingredients_matrix, self.train_recipes['category_id'])
        
        # Evaluiere das Modell mit Testdaten
        y_pred = self.classifier.predict(self.test_ingredients_matrix)
        accuracy = accuracy_score(self.test_recipes['category_id'], y_pred)
        f1 = f1_score(self.test_recipes['category_id'], y_pred, average='weighted')
        
        logger.info(f"Klassifikator trainiert - Genauigkeit: {accuracy:.2f}, F1-Score: {f1:.2f}")
        return self

    def evaluate_model(self):
        """Bewertet die Leistung des Modells mit verschiedenen Metriken."""
        if self.classifier is None or self.test_ingredients_matrix is None:
            logger.error("Modell nicht trainiert. Rufen Sie zuerst preprocess_data() auf.")
            raise ValueError("Modell nicht trainiert. Rufen Sie zuerst preprocess_data() auf.")
        
        y_true = self.test_recipes['category_id']
        y_pred = self.classifier.predict(self.test_ingredients_matrix)
        
        metrics = {
            'accuracy': accuracy_score(y_true, y_pred),
            'precision': precision_score(y_true, y_pred, average='weighted'),
            'recall': recall_score(y_true, y_pred, average='weighted'),
            'f1': f1_score(y_true, y_pred, average='weighted')
        }
        
        # Zeige die Merkmale mit der höchsten Wichtigkeit für die Klassifikation
        feature_importances = self.classifier.feature_importances_
        feature_names = self.vectorizer.get_feature_names_out()
        
        top_features = sorted(zip(feature_names, feature_importances), key=lambda x: x[1], reverse=True)[:10]
        
        logger.info(f"Modellbewertung: {metrics}")
        logger.info("Top-10 wichtigste Zutaten für die Klassifikation:")
        for feature, importance in top_features:
            logger.info(f"  - {feature}: {importance:.4f}")
        
        return metrics

    def recommend(self, user_ingredients, top_n=5, threshold=0.3):
        """
        Empfiehlt Rezepte basierend auf den vom Benutzer angegebenen Zutaten.

        Args:
            user_ingredients (list): Liste der Zutaten, die der Benutzer hat.
            top_n (int): Anzahl der zu empfehlenden Rezepte.
            threshold (float): Mindestwert für die Ähnlichkeit (0-1).

        Returns:
            list: Liste der empfohlenen Rezepte mit Ähnlichkeitswerten.
        """
        # Normalisiere Benutzereingaben
        user_ingredients = [ingredient.lower().strip() for ingredient in user_ingredients]

        # Erstelle einen Vektor aus den Benutzerzutaten
        if not self.vectorizer:
            logger.error("Modell wurde nicht trainiert. Bitte rufen Sie preprocess_data() auf.")
            raise ValueError("Modell wurde nicht trainiert. Bitte rufen Sie preprocess_data() auf.")

        # Erstelle einen String aus den Benutzerzutaten
        user_ingredients_text = ' '.join(user_ingredients)
        user_vector = self.vectorizer.transform([user_ingredients_text])

        # Wenn der Klassifikator trainiert wurde, prognostiziere die wahrscheinlichste Kategorie
        predicted_category = None
        if self.classifier is not None:
            category_id = self.classifier.predict(user_vector)[0]
            predicted_category = self.reverse_category_map.get(category_id)
            logger.info(f"Prognostizierte Kategorie für Zutaten: {predicted_category}")

        # Kombiniere alle Rezepte für die Ähnlichkeitsberechnung
        all_recipes = pd.concat([self.train_recipes, self.test_recipes]).reset_index(drop=True)
        all_matrix = self.vectorizer.transform(all_recipes['ingredients_text'])

        # Berechne die Ähnlichkeit zwischen Benutzerzutaten und allen Rezepten
        similarity_scores = cosine_similarity(user_vector, all_matrix).flatten()

        # Berechne den Prozentsatz der vorhandenen Zutaten und fehlenden Zutaten
        matching_percentages = []
        missing_counts = []
        
        for _, recipe in all_recipes.iterrows():
            recipe_ingredients = set([
                re.sub(r'\([^)]*\)', '', ingredient_obj['ingredient']).split(',')[0].strip().lower()
                for ingredient_obj in recipe['ingredients']
                if isinstance(ingredient_obj, dict) and 'ingredient' in ingredient_obj
            ])
            
            if not recipe_ingredients:
                matching_percentages.append(0)
                missing_counts.append(0)
                continue
                
            user_ingredients_set = set(user_ingredients)
            matching_ingredients = user_ingredients_set.intersection(recipe_ingredients)
            missing_ingredients = recipe_ingredients - user_ingredients_set
            
            # Prozentsatz der übereinstimmenden Zutaten
            match_percentage = len(matching_ingredients) / len(recipe_ingredients) * 100
            matching_percentages.append(match_percentage)
            
            # Anzahl fehlender Zutaten
            missing_counts.append(len(missing_ingredients))

        # Berechne einen gewichteten Score basierend auf:
        # 1. Ähnlichkeitswert (30%)
        # 2. Prozentsatz übereinstimmender Zutaten (40%)
        # 3. Negativ gewichtete Anzahl fehlender Zutaten (30%)
        max_missing = max(missing_counts) if missing_counts else 1
        normalized_missing = [1 - (count / max_missing) for count in missing_counts]
        
        combined_scores = (
            0.3 * similarity_scores + 
            0.4 * (np.array(matching_percentages) / 100) + 
            0.3 * np.array(normalized_missing)
        )

        # Filter nach Kategorie, wenn eine prognostiziert wurde
        if predicted_category:
            # Erhöhe den Score für Rezepte in der prognostizierten Kategorie
            category_boost = np.zeros_like(combined_scores)
            for i, recipe in all_recipes.iterrows():
                if recipe['category'] == predicted_category:
                    category_boost[i] = 0.1  # 10% Bonus für passende Kategorie
            combined_scores += category_boost

        # Filtere nach Mindestähnlichkeit
        valid_indices = np.where(combined_scores >= threshold)[0]
        if len(valid_indices) < top_n:
            # Wenn zu wenige Rezepte über dem Schwellwert liegen, nehme die besten verfügbaren
            valid_indices = np.argsort(combined_scores)[-min(top_n, len(combined_scores)):][::-1]
        else:
            # Sortiere die validen Indizes nach Score
            valid_indices = valid_indices[np.argsort(combined_scores[valid_indices])[::-1][:top_n]]

        # Erstelle Liste der empfohlenen Rezepte
        recommendations = []
        for idx in valid_indices:
            # Prüfe, ob der Score ausreichend ist
            if combined_scores[idx] < threshold:
                continue
                
            missing_ingredients = []
            recipe_ingredients = set([
                re.sub(r'\([^)]*\)', '', ingredient_obj['ingredient']).split(',')[0].strip().lower()
                for ingredient_obj in all_recipes.iloc[idx]['ingredients']
                if isinstance(ingredient_obj, dict) and 'ingredient' in ingredient_obj
            ])
            user_ingredients_set = set(user_ingredients)

            for ingredient in recipe_ingredients:
                if ingredient not in user_ingredients_set:
                    # Finde das Original-Zutatenobjekt für fehlende Zutaten
                    original_ingredients = []
                    for ing_obj in all_recipes.iloc[idx]['ingredients']:
                        if isinstance(ing_obj, dict) and 'ingredient' in ing_obj:
                            base_ing = re.sub(r'\([^)]*\)', '', ing_obj['ingredient']).split(',')[0].strip().lower()
                            if base_ing == ingredient:
                                original_ingredients.append(ing_obj)

                    if original_ingredients:
                        missing_ingredients.extend(original_ingredients)

            # Berechne zusätzliche Metriken
            match_score = matching_percentages[idx]
            missing_ingredient_count = missing_counts[idx]
            
            recommendations.append({
                'id': str(all_recipes.iloc[idx].get('_id', '')),
                'name': all_recipes.iloc[idx]['name'],
                'category': all_recipes.iloc[idx].get('category', 'Keine Kategorie'),
                'similarity': similarity_scores[idx],
                'match_percentage': match_score,
                'missing_ingredient_count': missing_ingredient_count,
                'combined_score': combined_scores[idx],
                'full_recipe': all_recipes.iloc[idx].to_dict(),
                'missing_ingredients': missing_ingredients
            })

        # Sortiere abschließend nach kombiniertem Score
        recommendations.sort(key=lambda x: x['combined_score'], reverse=True)
        
        logger.info(f"{len(recommendations)} Rezepte empfohlen")
        return recommendations

    def suggest_ingredients(self, partial_name, max_suggestions=5):
        """Schlägt Zutaten basierend auf einem Teilnamen vor."""
        if not self.ingredient_names:
            logger.error("Keine Zutatennamen verfügbar. Rufen Sie zuerst load_data() auf.")
            return []
            
        suggestions = []
        partial_name = partial_name.lower()

        for ingredient in sorted(self.ingredient_names):
            if partial_name in ingredient:
                suggestions.append(ingredient)

            if len(suggestions) >= max_suggestions:
                break

        logger.info(f"{len(suggestions)} Zutatenvorschläge für '{partial_name}' gefunden")
        return suggestions

    def save_model(self, filename='RecipeRecommender.pkl'):
        """Speichert das trainierte Modell."""
        # Stelle sicher, dass das Verzeichnis existiert
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        # Temporär die MongoDB-Verbindungsobjekte auf None setzen
        # damit pickle das Objekt serialisieren kann
        client_backup = self.client
        db_backup = self.db
        collection_backup = self.collection
        
        self.client = None
        self.db = None 
        self.collection = None
        
        try:
            with open(filename, 'wb') as f:
                pickle.dump(self, f)
            logger.info(f"Modell gespeichert als {filename}")
        except Exception as e:
            logger.error(f"Fehler beim Speichern des Modells: {e}")
            raise
        finally:
            # MongoDB-Verbindungsobjekte wiederherstellen
            self.client = client_backup
            self.db = db_backup
            self.collection = collection_backup
            
        return self

    @classmethod
    def load_model(cls, filename='RecipeRecommender.pkl'):
        """Lädt ein gespeichertes Modell."""
        try:
            with open(filename, 'rb') as f:
                model = pickle.load(f)
            logger.info(f"Modell geladen aus {filename}")
            
            # Hinweis: MongoDB-Verbindungsobjekte werden beim Laden als None initialisiert
            # Falls du sie benötigst, musst du connect() aufrufen
            if model.mongo_uri and (model.client is None):
                logger.info("MongoDB-Verbindung wird wiederhergestellt...")
                model.connect()
                
            return model
        except FileNotFoundError:
            logger.error(f"Modell-Datei {filename} nicht gefunden")
            raise
        except Exception as e:
            logger.error(f"Fehler beim Laden des Modells: {e}")
            raise


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv

    load_dotenv()
    
   # Kommandozeilenargumente einrichten
    parser = argparse.ArgumentParser(description='Recipe Recommender Model Training')
    parser.add_argument('-u', '--uri', type=str, 
                        help='MongoDB connection URI (optional, uses env vars if not provided)')
    parser.add_argument('-o', '--output', type=str, default='RecipeRecommender.pkl',
                        help='Output file for the trained model (default: RecipeRecommender.pkl)')
    parser.add_argument('--test', action='store_true',
                        help='Run a test recommendation after training')
    parser.add_argument('--ingredients', type=str, default="Mehl,Eier,Milch,Zucker",
                        help='Test ingredients, comma separated (default: "Mehl,Eier,Milch,Zucker")')
    
    args = parser.parse_args()
    
    # Verwende die übergebene URI oder erstelle eine aus Umgebungsvariablen
    if args.uri:
        MONGO_URI = args.uri
    else:
        # Baue die URI aus Umgebungsvariablen
        MONGO_USERNAME = os.getenv('MONGO_USERNAME')
        MONGO_PASSWORD = os.getenv('MONGO_PASSWORD')
        MONGO_HOST = os.getenv('MONGO_HOST')
        MONGO_DATABASE = os.getenv('MONGO_DATABASE', 'recipes')
        
        if not all([MONGO_USERNAME, MONGO_PASSWORD, MONGO_HOST]):
            logger.error("Umgebungsvariablen für MongoDB nicht vollständig. Bitte .env-Datei prüfen oder URI angeben.")
            sys.exit(1)
            
        MONGO_URI = f'mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOST}/{MONGO_DATABASE}?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000'
        logger.info("Verbindungs-URI aus Umgebungsvariablen generiert.")
    
    try:
        # Erstelle und trainiere das Modell
        logger.info("Starte Training des RecipeRecommender-Modells...")
        model = RecipeRecommender(MONGO_URI)
        model.load_data()
        model.preprocess_data()
        
        # Evaluiere das Modell
        logger.info("Evaluiere Modell...")
        metrics = model.evaluate_model()
        
        # Speichere das Modell
        logger.info(f"Speichere Modell in {args.output}...")
        model.save_model(args.output)
        logger.info(f"Modell erfolgreich gespeichert!")
        
        # Optional: Testempfehlung
        if args.test:
            test_ingredients = [ing.strip() for ing in args.ingredients.split(',')]
            logger.info(f"\n*** DEMO MIT ZUTATEN: {', '.join(test_ingredients)} ***")
            
            recommendations = model.recommend(test_ingredients, top_n=3)
            
            print("\nEmpfohlene Rezepte:")
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec['name']} (Übereinstimmung: {rec['match_percentage']:.1f}%, Score: {rec['combined_score']:.3f})")
                print(f"   Kategorie: {rec['category']}")
                if rec['missing_ingredients']:
                    print("   Fehlende Zutaten:")
                    for ing in rec['missing_ingredients']:
                        amount_str = f"{ing.get('amount', '')} {ing.get('unit', '')}" if ing.get('amount') and ing.get('unit') else ""
                        print(f"   - {amount_str} {ing.get('ingredient', '')}")
                print()
                
        logger.info("Fertig!")
        
    except Exception as e:
        logger.error(f"Fehler beim Training des Modells: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)