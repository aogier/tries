# -*- coding: utf-8 -*-
'''
Scrapeports items
'''

import scrapy


class AirportItem(scrapy.Item):
    '''
    Wikipedia airport item
    see tables @ https://en.wikipedia.org/wiki/List_of_airports_by_IATA_code:_A
    '''

    iata = scrapy.Field()
    icao = scrapy.Field()
    name = scrapy.Field()
    location = scrapy.Field()
    time = scrapy.Field()
    dst = scrapy.Field()
