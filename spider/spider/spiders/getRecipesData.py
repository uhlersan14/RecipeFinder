import scrapy
import re
from ..items import SpiderItem

class RecipeSpider(scrapy.Spider):
    name = "recipe_spider"
    allowed_domains = ["swissmilk.ch"]
    start_urls = [
        "https://www.swissmilk.ch/de/rezepte-kochideen/grundrezepte/",
        "https://www.swissmilk.ch/de/rezepte-kochideen/low-carb/",
    ]

    def parse(self, response):
        # Extrahieren Sie alle Rezept-Links von der Kategorie-Seite
        recipe_links = response.css('a[href*="/rezepte-kochideen/rezepte/"]::attr(href)').getall()
        for link in recipe_links:
            if link.startswith('/'):
                link = response.urljoin(link)
            yield response.follow(link, self.parse_recipe)
        
        # Überprüfen Sie auf Pagination, falls vorhanden
        next_page = response.css('a.next::attr(href)').get()
        if next_page is not None:
            yield response.follow(next_page, self.parse)
    
    def parse_recipe(self, response):
        # Erstelle ein neues RecipeItem
        item = SpiderItem()
        
        # Extrahiere den Rezeptnamen
        item['name'] = response.css('h1.DetailPageHeader--title::text').get().strip() or 'No name found'
        
        # Extrahiere die Zubereitungszeit
        prep_time_div = response.css('div.QuickFacts--item--inner')
        prep_time = None
        for div in prep_time_div:
            title = div.css('span.QuickFacts--item--title::text').get()
            if title and "Auf dem Tisch in" in title:
                time_value = div.css('span.QuickFacts--item--value::text').get()
                if time_value:
                    # Extrahiere die Zeit in Minuten
                    time_match = re.search(r'(\d+)\s*min', time_value)
                    if time_match:
                        prep_time = int(time_match.group(1))
                    else:
                        # Behandlung von Stunden und Minuten (z.B. "1h 30min")
                        hours_match = re.search(r'(\d+)\s*h', time_value)
                        minutes_match = re.search(r'(\d+)\s*min', time_value)
                        
                        hours = int(hours_match.group(1)) if hours_match else 0
                        minutes = int(minutes_match.group(1)) if minutes_match else 0
                        
                        if hours > 0 or minutes > 0:
                            prep_time = hours * 60 + minutes
        
        item['prep_time_minutes'] = prep_time
        
        # Extrahiere Zutaten und Mengen mit strukturiertem Format
        ingredients = []
        for row in response.css('tbody.IngredientsCalculator--group tr.Ingredient'):
            amount_spans = row.css('td.Ingredient--amount .IngredientValue *::text').getall()
            amount_text = ' '.join(filter(None, amount_spans)).strip() if amount_spans else ''
            ingredient_text = row.css('th.Ingredient--text::text').get().strip() or ''
            
            if amount_text and ingredient_text:
                # Parse amount and unit from amount_text
                parsed_ingredient = self.parse_ingredient(amount_text, ingredient_text)
                ingredients.append(parsed_ingredient)
        
        item['ingredients'] = ingredients if ingredients else []
        
        yield item
    
    def parse_ingredient(self, amount_text, ingredient_text):
        """
        Parse amount and unit from amount_text and separate them.
        Example: "200 g" -> {"amount": 200, "unit": "g", "ingredient": "Mehl"}
        """
        # Regulärer Ausdruck, um Menge und Einheit zu trennen
        # Sucht nach Zahlen (auch mit Komma/Punkt) und optionalen Brüchen (½, ¼, etc.)
        # gefolgt von einer optionalen Einheit
        pattern = r'((?:\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)?|\d*[¼½¾](?:\s*-\s*\d*[¼½¾])?))\s*([a-zA-ZäöüÄÖÜß]+\.?)?'
        match = re.match(pattern, amount_text)
        
        if match:
            amount_str, unit = match.groups()
            amount_str = amount_str.strip() if amount_str else ""
            unit = unit.strip() if unit else ""
            
            # Konvertiere Bruchzahlen in Dezimalzahlen
            amount = None
            try:
                # Versuche, direkt als Zahl zu parsen
                amount = float(amount_str.replace(',', '.'))
            except ValueError:
                # Spezielle Behandlung für Brüche
                if '¼' in amount_str:
                    amount_str = amount_str.replace('¼', '.25')
                if '½' in amount_str:
                    amount_str = amount_str.replace('½', '.5')
                if '¾' in amount_str:
                    amount_str = amount_str.replace('¾', '.75')
                
                # Bereich wie "1-2" -> Nehme den Mittelwert
                if '-' in amount_str:
                    parts = amount_str.split('-')
                    if len(parts) == 2:
                        try:
                            min_val = float(parts[0].strip().replace(',', '.'))
                            max_val = float(parts[1].strip().replace(',', '.'))
                            amount = (min_val + max_val) / 2
                        except ValueError:
                            pass
                
                # Falls immer noch kein Wert, versuche erneut zu parsen
                if amount is None:
                    try:
                        amount = float(amount_str.replace(',', '.'))
                    except ValueError:
                        # Wenn alles fehlschlägt, behalte den ursprünglichen String
                        amount = amount_str
        else:
            # Wenn keine Übereinstimmung gefunden wird, behalte den ursprünglichen Text
            amount = amount_text
            unit = ""
        
        return {
            "amount": amount,
            "unit": unit,
            "ingredient": ingredient_text
        }