#!/usr/bin/env python
'''
Created on 23 feb 2019

@author: oggei
'''

import atexit
from distutils.spawn import find_executable  # pylint: disable=import-error, no-name-in-module
from glob import glob
import logging
from multiprocessing import Process, Queue
import os
import re
from shutil import copyfile
import shutil
import subprocess
import tempfile
import unicodedata

import click
import marisa_trie  # pylint: disable=import-error


STOP = 'KTHXBYE'
FNULL = open(os.devnull, 'w')
CLEANED_RECORD = re.compile(br'^([A-Z]*\n?)+$')
DELIMITERS = re.compile(br"[\.\-']")

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s')

logger = logging.getLogger('builder')  # pylint: disable=invalid-name
logger.setLevel(logging.DEBUG)


def _validate_aspell(ctx, param, value):  # pylint: disable=unused-argument
    if value:
        if not find_executable('aspell'):
            raise click.BadParameter(
                'required aspell command not found in path')
        click.echo(
            click.style(
                f'Aspell installed and ready for {value}',
                fg='green'))

    return value


def _validate_hunspell(ctx, param, value):  # pylint: disable=unused-argument
    if value:
        if not find_executable('unmunch'):
            raise click.BadParameter(
                'required unmunch command not found in path')
        click.echo(
            click.style(
                f'Hunspell installed, {value} found',
                fg='green'))

    return value


def _validate_plainfile(ctx, param, value):  # pylint: disable=unused-argument
    if value:
        click.echo(
            click.style(
                f'Plain wordlist {value} found',
                fg='green'))
    return value


def _exit_handler(workdir):
    print(f'Cleaning temp dir {workdir}')
    shutil.rmtree(workdir)


def _cleanup(line):
    line = line.strip()
    line = unicodedata.normalize(
        "NFKD", line).encode("ascii", "ignore")
    line = line.upper()
    line = DELIMITERS.split(line)
    ret = b'\n'.join(line)
    if not CLEANED_RECORD.match(ret):
        #         logger.warning('Dropping %s', line)
        return b''
    return ret + b'\n'


def _dedup(in_queue):

    logger.debug('dedup start!')

    for item in iter(in_queue.get, STOP):

        entries = set()
        with open(item, encoding='utf-8') as datafile:
            for line in datafile:
                entries.add(line)

        dedup_log_from = f'{os.path.basename(item)} ({os.stat(item).st_size})'
        os.remove(item)
        _, temporary_file = tempfile.mkstemp(prefix='dedup-')
        with open(temporary_file, 'w') as output:
            for entry in entries:
                output.write(entry)
        output.close()
        del entries
        logger.debug('dedup: %s -> %s (%s)',
                     dedup_log_from,
                     os.path.basename(output.name),
                     os.stat(output.name).st_size)

    logger.debug('dedup exit!')


def _process(in_queue, out_queue):

    logger.debug('processor started!')

    for item in iter(in_queue.get, STOP):

        _, wordlist_path = tempfile.mkstemp(prefix='clean-')

        with open(item, encoding='utf-8') as work:
            wordlist = open(wordlist_path, 'wb')
            for line in work:
                    # wordlist.write(f'{_cleanup(line)}\n'.encode('utf-8'))
                wordlist.write(_cleanup(line))
                if wordlist.tell() > 10000000:
                    wordlist.close()
                    logger.debug('rotating output')
                    out_queue.put(wordlist.name)
                    _, wordlist_path = tempfile.mkstemp(prefix='clean-')
                    wordlist = open(wordlist_path, 'wb')

            wordlist.close()
            logger.debug('send last piece')
            out_queue.put(wordlist.name)

        os.remove(item)

    logger.debug('processor end!')


def _raw_data(out_queue, pipeline=None, source=None):

    chunk_size = '50M'

    _, temporary_file = tempfile.mkstemp(prefix='input-')

    if pipeline:
        subprocess.check_call(f'{pipeline} | split - {temporary_file} -b {chunk_size}',
                              shell=True, stderr=FNULL)
    else:
        copyfile(source, temporary_file)

    for file in glob(f'{temporary_file}*'):
        out_queue.put(file)


def _process_plainfile(wordlist, out_queue):
    logger.debug('start plainfile')

    _raw_data(out_queue, source=wordlist)

    logger.debug('done plainfile')


def _process_aspell(aspell_language, out_queue):
    logger.debug('start aspell')

    pipeline = (f"aspell -d {aspell_language} dump master |"
                f"aspell -l {aspell_language} expand |"
                fr"sed 's/ /\n/g'")

    _raw_data(out_queue, pipeline)

    logger.debug('aspell done')


def _process_hunspell(hunspell_language, out_queue):
    logger.debug('start hunspell')

    pipeline = (f'unmunch /usr/share/hunspell/{hunspell_language}.dic '
                f'/usr/share/hunspell/{hunspell_language}.aff'
                '| iconv -f iso-8859-15 -t utf-8 -')

    _raw_data(out_queue, pipeline)

    logger.debug('hunspell done')


def _generate(workdir):
    for file in glob(f'{workdir}/dedup-*'):
        with open(file, encoding='utf-8') as datafile:
            try:
                for line in datafile:
                    yield line.strip()
            except Exception as err:
                logger.critical('OH NO, %s', err)
                raise


@click.command()
@click.option(
    '--wordlist',
    callback=_validate_plainfile,
    help='plaintext wordlist path eg. /usr/share/dict/italian'
)
@click.option(
    '--aspell', 'aspell_language',
    callback=_validate_aspell,
    help='aspell language eg. it'
)
@click.option(
    '--hunspell', 'hunspell_language',
    callback=_validate_hunspell,
    help='hunspell language eg. it_IT'
)
@click.option(
    '--pool-size', default=3, help='pool size', show_default=True
)
@click.option(
    '--output', help='output file name'
)
def main(wordlist: str, aspell_language, hunspell_language, pool_size, output) -> None:
    '''
    Main command.

    :param wlist:
    :param aspell:
    :param hunspell:
    '''

    workdir = tempfile.mkdtemp(suffix='-wordlist-build')
    os.environ['TMPDIR'] = workdir
    tempfile.tempdir = workdir

    atexit.register(_exit_handler, workdir)

    dedup_queue: Queue = Queue(20)
    process_queue: Queue = Queue(20)

    dedup_process = Process(target=_dedup, args=(dedup_queue, ))
    dedup_process.start()

    process_pool = []
    for _ in range(pool_size):
        process = Process(target=_process, args=(process_queue, dedup_queue))
        process_pool.append(process)
        process.start()

    pool = []

    if wordlist:

        process = Process(target=_process_plainfile,
                          args=(wordlist, process_queue))

        pool.append(process)
        process.start()

    if aspell_language:

        process = Process(target=_process_aspell,
                          args=(aspell_language, process_queue))

        pool.append(process)
        process.start()

    if hunspell_language:

        process = Process(target=_process_hunspell,
                          args=(hunspell_language, process_queue))

        pool.append(process)
        process.start()

    for process in pool:
        process.join()

    for _ in range(pool_size):
        process_queue.put(STOP)

    for process in process_pool:
        process.join()

    dedup_queue.put(STOP)

    dedup_process.join()

    logger.debug('making trie')
    trie = marisa_trie.Trie(_generate(workdir))

    logger.debug('saving trie')
    trie.save(output)
    logger.debug('done')


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
