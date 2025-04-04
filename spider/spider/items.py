# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class SpiderItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    name = scrapy.Field()
    ingredients = scrapy.Field()
    # Nur das neue benötigte Feld
    prep_time_minutes = scrapy.Field()  # Zubereitungszeit in Minuten
    pass
