# -*- coding: utf-8 -*-
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapeports.items import AirportItem


class IataSpider(CrawlSpider):
    '''
    Crawl wikipedia collecting airport data.
    '''
    name = 'iata'
    allowed_domains = ['wikipedia.org']
    start_urls = ['https://en.wikipedia.org/wiki/IATA_airport_code']

    rules = (Rule(
        LinkExtractor(
            restrict_xpaths=['//div[@class="mw-parser-output"]'
                             '//a[contains(@href, "/wiki/List_of_airports_by_IATA")]']),
        callback='get_airport'),)

    def get_airport(self, response):  # pylint: disable=no-self-use, missing-docstring

        for record in response.xpath('//table[contains(@class, "sortable")]//tr[td]'):
            _x = record.xpath
            airport = {}
            airport['iata'] = _x('.//td[1]/text()').extract_first()
            airport['icao'] = _x('.//td[2]/text()').extract_first()
            airport['name'] = _x('.//td[3]/text()').extract_first()
            airport['location'] = ''.join(_x('.//td[4]//text()').extract())
            airport['time'] = _x('.//td[5]//text()').extract_first()
            airport['dst'] = _x('.//td[6]//text()').extract_first()

            # getting rid of empty or '\n' strings
            yield AirportItem(**{k: v.strip() if v and v.strip() else None
                                 for k, v
                                 in airport.items()})
