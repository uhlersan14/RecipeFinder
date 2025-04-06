import json
import argparse
from pymongo import MongoClient, IndexModel, ASCENDING

class MongoImporter:
    def __init__(self, input_file, mongo_uri, collection_name):
        self.input_file = input_file
        self.mongo_uri = mongo_uri
        self.collection_name = collection_name
        self.client = None
        self.db = None
        self.collection = None

    def connect(self):
        """Stellt eine Verbindung zur MongoDB her."""
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client['recipes']  # Explizit die Datenbank angeben
        self.collection = self.db[self.collection_name]
        print(f"Verbunden mit Datenbank 'recipes', Collection '{self.collection_name}'")
        
        # Erstelle einen Index für das 'name'-Feld für schnellere Duplikat-Erkennung
        self.collection.create_index([("name", ASCENDING)])
        print("Index auf 'name'-Feld erstellt")

    def clear_collection(self):
        """Löscht alle vorhandenen Dokumente in der Collection."""
        try:
            result = self.collection.delete_many({})
            print(f"Collection geleert: {result.deleted_count} Dokumente gelöscht")
        except Exception as e:
            print(f"Fehler beim Leeren der Collection: {e}")
            # Versuche alternativ, die Collection zu löschen und neu zu erstellen
            try:
                self.db.drop_collection(self.collection_name)
                self.collection = self.db.create_collection(self.collection_name)
                print(f"Collection '{self.collection_name}' gelöscht und neu erstellt")
                
                # Index nach der Neuerstellung wieder anlegen
                self.collection.create_index([("name", ASCENDING)])
            except Exception as e2:
                print(f"Konnte Collection nicht neu erstellen: {e2}")

    def read_lines(self):
        """Liest die JSON-Lines-Datei und gibt Batches von Datensätzen zurück."""
        batch = []
        line_count = 0
        error_count = 0
        
        with open(self.input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line_count += 1
                if line.strip():  # Ignoriere Leerzeilen
                    try:
                        data = json.loads(line)
                        batch.append(data)
                        if len(batch) >= 100:  # Batch-Größe
                            yield batch
                            batch = []
                    except json.JSONDecodeError as e:
                        error_count += 1
                        print(f"Fehler beim Parsen der Zeile {line_count}: {line[:50]}...")
                        print(f"Fehler: {e}")
                        continue
                        
        if batch:
            yield batch
            
        print(f"Datei gelesen: {line_count} Zeilen, {error_count} Fehler")

    def check_and_filter_duplicates(self, batch):
        """Prüft und filtert Duplikate basierend auf dem 'name'-Feld."""
        filtered_batch = []
        duplicates_count = 0
        
        # Sammle alle Namen im aktuellen Batch
        batch_names = [doc.get('name') for doc in batch if 'name' in doc]
        
        # Finde alle bereits existierenden Dokumente mit diesen Namen
        existing_names = set()
        if batch_names:
            cursor = self.collection.find({"name": {"$in": batch_names}}, {"name": 1})
            existing_names = {doc.get('name') for doc in cursor if 'name' in doc}
        
        # Filtere Duplikate
        for doc in batch:
            if 'name' not in doc:
                # Dokumente ohne Name-Feld behalten wir bei
                filtered_batch.append(doc)
                continue
                
            name = doc.get('name')
            
            # Prüfe, ob Name bereits in der Datenbank existiert
            if name in existing_names:
                duplicates_count += 1
                continue
            
            # Prüfe, ob Name mehrfach im Batch vorkommt
            # Wenn ja, nimm nur das erste Vorkommen
            if name in [d.get('name') for d in filtered_batch]:
                duplicates_count += 1
                continue
                
            # Ansonsten füge das Dokument zum gefilterten Batch hinzu
            filtered_batch.append(doc)
            
            # Füge den Namen zur Liste der existierenden Namen hinzu
            existing_names.add(name)
            
        return filtered_batch, duplicates_count

    def save_to_mongodb(self):
        """Hauptmethode zum Import von Daten in MongoDB."""
        # Verbindung herstellen
        self.connect()
        
        # Collection leeren
        self.clear_collection()
        
        # Daten importieren
        total_inserted = 0
        total_duplicates = 0
        
        for idx, batch in enumerate(self.read_lines()):
            if batch:
                try:
                    # Duplikate filtern
                    filtered_batch, duplicates_count = self.check_and_filter_duplicates(batch)
                    total_duplicates += duplicates_count
                    
                    if filtered_batch:
                        result = self.collection.insert_many(filtered_batch)
                        inserted_count = len(result.inserted_ids)
                        total_inserted += inserted_count
                        print(f"Batch {idx + 1}: {inserted_count} Einträge gespeichert, {duplicates_count} Duplikate übersprungen.")
                    else:
                        print(f"Batch {idx + 1}: Keine neuen Einträge zu speichern, {duplicates_count} Duplikate übersprungen.")
                        
                except Exception as e:
                    print(f"Fehler beim Speichern von Batch {idx + 1}: {e}")
        
        print(f"Import abgeschlossen: {total_inserted} Dokumente importiert, {total_duplicates} Duplikate übersprungen.")
        
        # Verbindung schließen
        self.client.close()
        print("Verbindung geschlossen.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import JSON Lines into MongoDB")
    parser.add_argument("-i", "--input", required=True, help="Input JSON Lines file")
    parser.add_argument("-u", "--uri", required=True, help="MongoDB URI")
    parser.add_argument("-c", "--collection", required=True, help="MongoDB Collection")
    args = parser.parse_args()
    
    importer = MongoImporter(args.input, args.uri, args.collection)
    importer.save_to_mongodb()