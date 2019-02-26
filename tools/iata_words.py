#!/usr/bin/env python
'''
Created on 25 feb 2019

@author: Alessandro Ogier <alessandro.ogier@gmail.com>
'''

from collections import namedtuple
import sys
from urllib.parse import urlparse

import click
import marisa_trie


IATA_CODE_LENGTH = 3


def find(iata_codes, tries, min_size=0, max_size=float('inf')):
    '''
    Return a 3-letter tuples generator of words consisting of
    IATA codes.

    :param iata_codes: a IATA codes iterable
    :param tries: a MARISA trie file
    :param min_size: word minimum size
    :param max_size: word maximum size
    '''

    if not isinstance(iata_codes, set):
        iata_codes = set(iata_codes)

    trie = marisa_trie.Trie().load(tries)

    words = (word
             for word
             in trie.keys()
             if len(word) % 3 == 0
             and min_size <= len(word) <= max_size)

    for word in words:
        splitted = tuple(word[i:i + IATA_CODE_LENGTH]
                         for i
                         in range(0, len(word), IATA_CODE_LENGTH))
        if iata_codes.issuperset(splitted):
            yield splitted


def _iata_codes_callback(ctx, param, value):  # pylint: disable=unused-argument

    iata_url = urlparse(value)

    if iata_url.scheme == 'file':
        iata_codes = set(x.strip()
                         for x
                         in open(iata_url.path).readlines())
    elif iata_url.scheme.startswith('couchdb'):
        try:
            import cloudant
        except ImportError:
            print('Error: you must install cloudant module '
                  'for couchdb urls to work')
            sys.exit(1)

        ConnInfo = namedtuple('ConnInfo', ('db', 'dd', 'vn'))

        if iata_url.scheme.endswith('s'):
            scheme = 'https'
            port = iata_url.port if iata_url.port else 6984
        else:
            scheme = 'http'
            port = iata_url.port if iata_url.port else 5984

        client = cloudant.CouchDB(iata_url.username, iata_url.password,
                                  url=f'{scheme}://{iata_url.hostname}:{port}',
                                  connect=True)
        conn_info = ConnInfo(*[x
                               for x
                               in iata_url.path.split("/")
                               if x
                               and not x.startswith('_')])

        database = client[conn_info.db]
        ddoc = cloudant.design_document.DesignDocument(database, conn_info.dd)
        view = cloudant.view.View(ddoc, conn_info.vn)

        with view.custom_result(page_size=10000) as result:
            iata_codes = set(x['key'] for x in result)
            print(f'eia {len(iata_codes)}')

    return iata_codes


def _min_size_callback(ctx, param, value):  # pylint: disable=unused-argument
    if value % 3 != 0:
        value = value + 3 - value % 3
        print(f'effective min_size will be {value}')

    return value


def _max_size_callback(ctx, param, value):  # pylint: disable=unused-argument
    if value % 3 != 0:
        value = value - value % 3
        print(f'effective max_size will be {value}')

    return value


@click.command()
@click.option('--iata-codes',
              help=''
              'IATA codes list URL. Either file:// or couchdb(s):// ATM.',
              required=True, metavar='<url>',
              callback=_iata_codes_callback)
@click.option('--tries',
              help='wordlist tries path. Must be a serialized MARISA trie',
              required=True, metavar='<path>')
@click.option('--min-size',
              help='minimum word size',
              default=0, show_default=True,
              type=click.INT, metavar='<int>',
              callback=_min_size_callback)
@click.option('--max-size',
              help='maximum word size',
              default=float('inf'), show_default=True,
              type=click.FLOAT, metavar='<int>',
              callback=_max_size_callback)
@click.option('--format', '_format',
              help="prints one word per line, either in plain or space-separated format",
              type=click.Choice(['plain', 'spaced']),
              default='plain', show_default=True)
def main(iata_codes, tries, min_size, max_size, _format):
    '''
    Find a set of words consisting of IATA codes.
    '''

    for word in find(iata_codes, tries, min_size, max_size):
        if _format == 'plain':
            print(f'{"".join(word)}')
        elif _format == 'spaced':
            print(f'{" ".join(word)}')


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
