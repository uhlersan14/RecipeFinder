import json
import argparse
from pymongo import MongoClient

class MongoImporter:
    def __init__(self, input_file, mongo_uri, collection_name):
        self.input_file = input_file
        self.mongo_uri = mongo_uri
        self.collection_name = collection_name
        self.client = None
        self.db = None
        self.collection = None

    def connect(self):
        self.client = MongoClient(self.mongo_uri)
        # Verwende den Datenbanknamen aus der URI, oder 'recipes' als Fallback
        db_name = self.mongo_uri.split('/')[-1].split('?')[0] or 'recipes'
        self.db = self.client[db_name]
        self.collection = self.db[self.collection_name]
        print(f"Verbunden mit Datenbank '{db_name}', Collection '{self.collection_name}'")

    def clear_collection(self):
        """Löscht alle Dokumente in der Collection."""
        result = self.collection.delete_many({})
        print(f"Gelöschte Dokumente: {result.deleted_count}")

    def read_lines(self):
        batch = []
        line_count = 0
        with open(self.input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line_count += 1
                if line.strip():  # Ignoriere Leerzeilen
                    try:
                        data = json.loads(line)
                        # Prüfe, ob prep_time_minutes vorhanden ist
                        if 'prep_time_minutes' in data:
                            print(f"Zeile {line_count}: prep_time_minutes = {data['prep_time_minutes']}")
                        else:
                            print(f"Zeile {line_count}: KEINE prep_time_minutes gefunden!")
                        
                        batch.append(data)
                        if len(batch) >= 100:  # Batch-Größe
                            yield batch
                            batch = []
                    except json.JSONDecodeError as e:
                        print(f"Fehler beim Parsen der Zeile {line_count}: {line[:50]}...")
                        print(f"Fehler: {e}")
                        continue
        if batch:
            yield batch

    def save_to_mongodb(self):
        self.connect()
        # Lösche zuerst alle vorhandenen Dokumente
        self.clear_collection()
        
        total_docs = 0
        for idx, batch in enumerate(self.read_lines()):
            if batch:
                self.collection.insert_many(batch)
                total_docs += len(batch)
                print(f"Batch {idx + 1} mit {len(batch)} Einträgen gespeichert.")
        
        print(f"Import abgeschlossen: {total_docs} Dokumente importiert.")
        
        # Überprüfe, ob Dokumente mit prep_time_minutes existieren
        count = self.collection.count_documents({"prep_time_minutes": {"$exists": True}})
        print(f"Dokumente mit Zeitinformation: {count} von {total_docs}")
        
        self.client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import JSON Lines into MongoDB")
    parser.add_argument("-i", "--input", required=True, help="Input JSON Lines file")
    parser.add_argument("-u", "--uri", required=True, help="MongoDB URI")
    parser.add_argument("-c", "--collection", required=True, help="MongoDB Collection")
    args = parser.parse_args()

    importer = MongoImporter(args.input, args.uri, args.collection)
    importer.save_to_mongodb()