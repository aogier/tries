#!/usr/bin/env python
'''
Created on 25 feb 2019

@author: Alessandro Ogier <alessandro.ogier@gmail.com>
'''

import click
import marisa_trie


IATA_CODE_LENGTH = 3


def find(iata_codes, tries, min_size=0, max_size=float('inf')):
    '''
    Return a 3-letter tuples generator of words consisting of
    IATA codes.

    :param iata_codes: a IATA codes file, one code per line
    :param tries: a MARISA trie file
    :param min_size: word minimum size
    :param max_size: word maximum size
    '''

    iata = set(x.strip()
               for x
               in open(iata_codes).readlines())

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
        if iata.issuperset(splitted):
            yield splitted


@click.command()
@click.option('--iata-codes',
              help='IATA codes list path. File is one record per line',
              required=True, metavar='<path>')
@click.option('--tries',
              help='wordlist tries path. Must be a serialized MARISA trie',
              required=True, metavar='<path>')
@click.option('--min-size',
              help='minimum word size',
              default=0, show_default=True,
              type=click.INT, metavar='<int>')
@click.option('--max-size',
              help='maximum word size',
              default=float('inf'), show_default=True,
              type=click.FLOAT, metavar='<int>')
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
