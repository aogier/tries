#!/usr/bin/env python
'''
Created on 26 feb 2019

@author: Alessandro Ogier <alessandro.ogier@gmail.com>
'''
import multiprocessing
import sys

import click
import cloudant
import ijson
import os
import cProfile


STOP = 'KTHXBYE'


def _worker(in_queue, db, when_existing):

    batch = []
    for item in iter(in_queue.get, STOP):

        try:
            doc = db[item['_id']]
        except KeyError:
            batch.append(item)
            continue

        if item.items() <= doc.items():
            continue

        if when_existing == 'overwrite':
            print(f'overwriting {item}')
            doc.delete()
            doc.update(item)
        elif when_existing == 'update':
            print(f'updating {item}')
            doc.update(item)
        elif when_existing == 'ignore':
            #             print(f'ignoring {item}')
            continue

        batch.append(doc)

        if len(batch) > 100:
            db.bulk_docs(batch)
            batch = []

    if batch:
        db.bulk_docs(batch)


def _profi_worker(in_queue, db, when_existing):
    cProfile.runctx('_worker(in_queue, db, when_existing)',
                    globals(), locals(), 'prof%d.prof' % os.getpid())


@click.command()
@click.option('--couchdb-user', help='couchdb username', required=True)
@click.option('--couchdb-pass', help='couchdb password', required=True)
@click.option('--couchdb-url', 'couchdb_url',
              help='couchdb url',
              default='http://localhost:5984', show_default=True)
@click.option('--database', 'dbname',
              help='database name', required=True)
@click.option('--create-database',
              help='create database if it does not exist',
              default=True, show_default=True)
@click.option('--id-field',
              help='which json field is document _id')
@click.option('--when-existing',
              help='action when record already exists.',
              type=click.Choice(['overwrite', 'update', 'ignore']),
              default='ignore', show_default=True)
@click.option('--pool-size',
              help='pool size',
              default=2)
@click.option('--single',
              help='input is a single object, ie. not an array',
              is_flag=True, default=False)
@click.option('--profile',
              help='profile process (debug only',
              is_flag=True, default=False)
def main(couchdb_user, couchdb_pass, couchdb_url,
         dbname, create_database,
         id_field, when_existing,
         pool_size, single, profile):

    process_queue = multiprocessing.Queue(50)

    process_pool = []
    for _ in range(pool_size):
        client = cloudant.CouchDB(couchdb_user, couchdb_pass,
                                  url=couchdb_url,
                                  connect=True)
        if create_database:
            db = client.create_database(dbname)  # pylint: disable=invalid-name
        else:
            try:
                db = client[dbname]  # pylint: disable=invalid-name
            except KeyError:
                print(f'database {dbname} not found')
                sys.exit(1)

        if profile:
            process = multiprocessing.Process(
                target=_profi_worker, args=(process_queue, db, when_existing))
        else:
            process = multiprocessing.Process(
                target=_worker, args=(process_queue, db, when_existing))

        process.start()
        process_pool.append(process)

    if single:
        items = ijson.items(sys.stdin, '')
    else:
        items = ijson.items(sys.stdin, 'item')

    for item in items:

        if id_field:
            if not item[id_field]:
                print(f'skipping null id: {item}')
                continue
            else:
                item['_id'] = item[id_field]

        process_queue.put(item)

    for _ in range(pool_size):
        process_queue.put(STOP)

    for process in process_pool:
        process.join()


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
