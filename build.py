#!/usr/bin/env -S python -u
'''
Created on 23 feb 2019

@author: oggei
'''

import atexit
from distutils.spawn import find_executable  # pylint: disable=import-error, no-name-in-module
from glob import glob
import itertools
from multiprocessing import Process
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata

import click
import marisa_trie


FNULL = open(os.devnull, 'w')


def _validate_aspell(ctx, param, value):  # pylint: disable=unused-argument
    '''
    Validate aspell option.

    :param ctx:
    :param param:
    :param value:
    '''
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
                f'Plain wordlist {value.name} found',
                fg='green'))
    return value


def cleanup(workdir):
    print(f'Cleaning temp dir {workdir}')
    shutil.rmtree(workdir)


BASIC_LINE = re.compile(br'^[A-Z]*$')


def _cleanup(line):
    line = line.strip()
    line = unicodedata.normalize(
        "NFKD", line).encode("ascii", "ignore")
    line = line.upper()
    if b"'" in line:
        parts = line.split(b"'")
        line = parts[-1]
    if not BASIC_LINE.match(line):
        print(f'aiuto {line}')
    return line


def _process(pipeline, encoding):

    _, temporary_file = tempfile.mkstemp()

    subprocess.check_call(f'{pipeline} > {temporary_file}',
                          shell=True, stderr=FNULL)

    wordlist = tempfile.NamedTemporaryFile(delete=False)

    with open(temporary_file, encoding=encoding) as work:
        for line in work:
            wordlist.write(f'{_cleanup(line)}\n'.encode('utf-8'))

    os.remove(temporary_file)


def _process_aspell(aspell_language):
    print('start aspell')

    pipeline = (f"aspell -d {aspell_language} dump master |"
                f"aspell -l {aspell_language} expand |"
                fr"sed 's/ /\n/g'")

    _process(pipeline, 'utf-8')

    print(f'aspell done')


def _process_hunspell(hunspell_language):
    print('start hunspell')

    pipeline = (f'unmunch /usr/share/hunspell/{hunspell_language}.dic '
                f'/usr/share/hunspell/{hunspell_language}.aff')

    _process(pipeline, 'iso-8859-15')

    print(f'hunspell done')


def _generate(workdir):
    for file in glob(f'{workdir}/*'):
        with open(file, encoding='utf-8') as datafile:
            for line in datafile:
                yield line


@click.command()
@click.option(
    '--wordlist',
    callback=_validate_plainfile,
    type=click.File(),
    help='plaintext wordlist path eg. /usr/share/dict/italian',
)
@click.option(
    '--aspell', 'aspell_language',
    callback=_validate_aspell,
    help='aspell language eg. it',
)
@click.option(
    '--hunspell', 'hunspell_language',
    callback=_validate_hunspell,
    help='hunspell language eg. it_IT',
)
def main(wordlist, aspell_language, hunspell_language):
    '''
    Main command.

    :param wlist:
    :param aspell:
    :param hunspell:
    '''

    workdir = tempfile.mkdtemp(suffix='-wordlist-build')
    os.environ['TMPDIR'] = workdir
    tempfile.tempdir = workdir

    atexit.register(cleanup, workdir)

    print(f'wl: {wordlist} as: {aspell_language}')

    if wordlist:
        wordlist_temp = tempfile.NamedTemporaryFile(delete=False)
        for line in wordlist:

            wordlist_temp.write(_cleanup(line) + b'\n')

        print(f'cane {wordlist_temp.name}')

    pool = []

    if aspell_language:

        process = Process(target=_process_aspell,
                          args=(aspell_language, ))

        pool.append(process)
        process.start()

    if hunspell_language:

        process = Process(target=_process_hunspell,
                          args=(hunspell_language, ))

        pool.append(process)
        process.start()

    for process in pool:
        process.join()

    print('making trie')
    trie = marisa_trie.Trie(_generate(workdir))

    print('saving trie')
    trie.save('out')
    print('done')


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
