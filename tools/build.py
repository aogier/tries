#!/usr/bin/env python
'''
Created on 26 feb 2019

@author: Alessandro Ogier <alessandro.ogier@gmail.com>
'''
import atexit
from glob import glob
import logging
import multiprocessing
import os
import re
import shutil
import sys
import tempfile
import unicodedata

import click
import marisa_trie
from setproctitle import setproctitle  # pylint: disable=no-name-in-module


__ME__ = 'build'
STOP = 'KTHXBYE'
FNULL = open(os.devnull, 'w')
CLEANED_RECORD = re.compile(br'^([A-Z]*\n?)+$')
DELIMITERS = re.compile(br"[\.\-']")

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s')

logger = logging.getLogger(__ME__)  # pylint: disable=invalid-name
logger.setLevel(logging.DEBUG)


def _exit_handler(workdir):
    print(f'Cleaning temp dir {workdir}')
    shutil.rmtree(workdir)


def _mktemp(prefix, mode='w'):
    _, temporary_file = tempfile.mkstemp(prefix=prefix)
    return open(temporary_file, mode)


def _dedup(in_queue):

    setproctitle(f'{__ME__} - deduplicator')

    logger.debug('dedup start!')

    for item in iter(in_queue.get, STOP):

        entries = set()
        with open(item, encoding='utf-8') as datafile:
            entries.update((line for line in datafile))

        dedup_log_from = f'{os.path.basename(item)} ({os.stat(item).st_size})'
        os.remove(item)
        with _mktemp('3-dedup-') as output:
            for entry in entries:
                output.write(entry)
        output.close()
        logger.debug('dedup: %s -> %s (%s)',
                     dedup_log_from,
                     os.path.basename(output.name),
                     os.stat(output.name).st_size)

    logger.debug('dedup exit!')


def _process(in_queue, out_queue):

    setproctitle(f'{__ME__} - processor')

    logger.debug('processor started!')

    for item in iter(in_queue.get, STOP):

        with open(item, encoding='utf-8') as work:
            wordlist = _mktemp('1-clean-', 'wb')
            for line in work:

                line = line.strip()
                line = unicodedata.normalize(
                    'NFKD', line).encode('ascii', 'ignore')
                line = line.upper()
                line = DELIMITERS.split(line)
                ret = b'\n'.join(line)
                if CLEANED_RECORD.match(ret):
                    wordlist.write(ret + b'\n')
                else:
                    #                     logger.warning('Dropping %s', line)
                    pass
                if wordlist.tell() > 10000000:
                    wordlist.close()
                    logger.debug('rotating output')
                    out_queue.put(wordlist.name)

                    wordlist = _mktemp('1-clean-', 'wb')

            if wordlist.tell() > 0:
                wordlist.close()
                logger.debug('send last piece')
                out_queue.put(wordlist.name)

        os.remove(item)

    logger.debug('processor end!')


def _generate(workdir):
    for file in glob(f'{workdir}/3-dedup-*'):
        with open(file, encoding='utf-8') as datafile:
            try:
                for line in datafile:
                    yield line.strip()
            except Exception as err:
                logger.critical('OH NO, %s', err)
                raise


@click.command()
@click.option('--pool-size',
              help='processor pool size',
              type=click.INT, default=3)
@click.option('--keep',
              help='keep workdir',
              is_flag=True)
@click.option('--output',
              help='output file name',
              required=True)
def main(pool_size, keep, output):

    setproctitle(f'{__ME__} - main process')

    workdir = tempfile.mkdtemp(suffix='-wordlist-build')
    logger.debug('workdir: %s', {workdir})
    os.environ['TMPDIR'] = workdir
    tempfile.tempdir = workdir

    if not keep:
        atexit.register(_exit_handler, workdir)

    _, filename = tempfile.mkstemp(prefix='0-input-')
    input_file = open(filename, 'w')

    process_queue = multiprocessing.Queue()
    dedup_queue = multiprocessing.Queue(20)

    dedup_pool = []
    process_pool = []

    for _ in range(pool_size):
        process = multiprocessing.Process(target=_process,
                                          args=(process_queue, dedup_queue))
        dedup_process = multiprocessing.Process(target=_dedup,
                                                args=(dedup_queue, ))
        process.start()
        dedup_process.start()

        process_pool.append(process)
        dedup_pool.append(dedup_process)

    for count, line in enumerate(sys.stdin, 1):
        input_file.write(line)
        if count % 2500000 == 0:
            input_file.close()
            logger.debug('rotating input file at %s bytes',
                         os.stat(input_file.name).st_size)

            process_queue.put(input_file.name)

            _, filename = tempfile.mkstemp(prefix='0-input-')
            input_file = open(filename, 'w')

    if input_file.tell() > 0:
        logger.debug('sending last input file at %s bytes',
                     os.stat(input_file.name).st_size)
        input_file.close()
        process_queue.put(input_file.name)

    for _ in range(pool_size):
        process_queue.put(STOP)

    for process in process_pool:
        process.join()

    for _ in range(pool_size):
        dedup_queue.put(STOP)

    for process in dedup_pool:
        process.join()

    logger.info('done')

    logger.debug('making trie')
    trie = marisa_trie.Trie(_generate(workdir))

    logger.debug('saving trie')
    trie.save(output)
    logger.debug('done')


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
