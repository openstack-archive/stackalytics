# Copyright (c) 2013 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pickle
import sys

from oslo.config import cfg

from stackalytics.openstack.common import log as logging
from stackalytics.processor import config
from stackalytics.processor import runtime_storage


LOG = logging.getLogger(__name__)

OPTS = [
    cfg.BoolOpt('reverse',
                short='r',
                help='Load data to runtime storage'),
    cfg.StrOpt('file',
               short='f',
               help='File name'),
]


def read_records_from_fd(fd):
    while True:
        try:
            record = pickle.load(fd)
        except EOFError:
            break
        yield record


def import_data(runtime_storage_inst, fd):
    bucket = {}
    count = 0
    for record in read_records_from_fd(fd):
        count += 1
        if len(bucket) < runtime_storage.RECORD_ID_PREFIX:
            bucket[record['record_id']] = record
        else:
            runtime_storage_inst.memcached.set_multi(
                bucket, key_prefix=runtime_storage.RECORD_ID_PREFIX)
            bucket = {}
    if bucket:
        runtime_storage_inst.memcached.set_multi(
            bucket, key_prefix=runtime_storage.RECORD_ID_PREFIX)

    runtime_storage_inst._set_record_count(count)


def export_data(runtime_storage_inst, fd):
    for record in runtime_storage_inst.get_all_records():
        pickle.dump(record, fd)


def main():
    # init conf and logging
    conf = cfg.CONF
    conf.register_cli_opts(config.OPTS)
    conf.register_cli_opts(OPTS)
    conf.register_opts(config.OPTS)
    conf.register_opts(OPTS)
    conf()

    logging.setup('stackalytics')
    LOG.info('Logging enabled')

    runtime_storage_inst = runtime_storage.get_runtime_storage(
        cfg.CONF.runtime_storage_uri)

    filename = cfg.CONF.file

    if cfg.CONF.reverse:
        if filename:
            fd = open(filename, 'r')
        else:
            fd = sys.stdin
        import_data(runtime_storage_inst, fd)
    else:
        if filename:
            fd = open(filename, 'w')
        else:
            fd = sys.stdout
        export_data(runtime_storage_inst, fd)


if __name__ == '__main__':
    main()
