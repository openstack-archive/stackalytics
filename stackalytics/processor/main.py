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

import time

from oslo.config import cfg
import psutil
from psutil import _error
import sh

from stackalytics.openstack.common import log as logging
from stackalytics.openstack.common import timeutils
from stackalytics.processor import commit_processor
from stackalytics.processor import persistent_storage
from stackalytics.processor import runtime_storage
from stackalytics.processor import vcs


LOG = logging.getLogger(__name__)

OPTS = [
    cfg.StrOpt('default-data', default='etc/default_data.json',
               help='Default data'),
    cfg.StrOpt('sources-root', default=None, required=True,
               help='The folder that holds all project sources to analyze'),
    cfg.StrOpt('runtime-storage-uri', default='memcached://127.0.0.1:11211',
               help='Storage URI'),
    cfg.StrOpt('frontend-update-address',
               default='http://user:user@localhost/update/%s',
               help='Address of update handler'),
    cfg.StrOpt('repo-poll-period', default='300',
               help='Repo poll period in seconds'),
    cfg.StrOpt('persistent-storage-uri', default='mongodb://localhost',
               help='URI of persistent storage'),
    cfg.BoolOpt('sync-default-data', default=False,
                help='Update persistent storage with default data. '
                     'Existing data is not overwritten'),
    cfg.BoolOpt('force-sync-default-data', default=False,
                help='Completely overwrite persistent storage with the '
                     'default data'),
    cfg.StrOpt('launchpad-user', default='stackalytics-bot',
               help='User to access Launchpad'),
    cfg.BoolOpt('filter-robots', default=True,
                help='Filter out commits from robots'),
]


def get_pids():
    uwsgi_dict = {}
    for pid in psutil.get_pid_list():
        try:
            p = psutil.Process(pid)
            if p.cmdline and p.cmdline[0].find('/uwsgi '):
                uwsgi_dict[p.pid] = p.parent
        except _error.NoSuchProcess:
            # the process may disappear after get_pid_list call, ignore it
            pass

    result = set()
    for pid in uwsgi_dict:
        if uwsgi_dict[pid] in uwsgi_dict:
            result.add(pid)

    return result


def update_pid(pid):
    url = cfg.CONF.frontend_update_address % pid
    sh.curl(url)


def update_pids(runtime_storage):
    pids = get_pids()
    if not pids:
        return
    runtime_storage.active_pids(pids)
    current_time = time.time()
    for pid in pids:
        if current_time > runtime_storage.get_pid_update_time(pid):
            update_pid(pid)
    return current_time


def process_repo(repo, runtime_storage, processor):
    uri = repo['uri']
    LOG.debug('Processing repo uri %s' % uri)

    vcs_inst = vcs.get_vcs(repo)
    vcs_inst.fetch()

    for branch in repo['branches']:
        LOG.debug('Processing repo %s, branch %s' % (uri, branch))

        head_commit_id = runtime_storage.get_head_commit_id(uri, branch)

        commit_iterator = vcs_inst.log(branch, head_commit_id)
        processed_commit_iterator = processor.process(commit_iterator)
        runtime_storage.set_records(processed_commit_iterator)

        head_commit_id = vcs_inst.get_head_commit_id(branch)
        runtime_storage.set_head_commit_id(uri, branch, head_commit_id)


def update_repos(runtime_storage, persistent_storage):
    current_time = time.time()
    repo_update_time = runtime_storage.get_repo_update_time()

    if current_time < repo_update_time:
        LOG.info('The next update is scheduled at %s. Skipping' %
                 timeutils.iso8601_from_timestamp(repo_update_time))
        return

    repos = persistent_storage.get_repos()
    processor = commit_processor.CommitProcessorFactory.get_processor(
        commit_processor.COMMIT_PROCESSOR_CACHED,
        persistent_storage)

    for repo in repos:
        process_repo(repo, runtime_storage, processor)

    runtime_storage.set_repo_update_time(time.time() +
                                         int(cfg.CONF.repo_poll_period))


def main():
    # init conf and logging
    conf = cfg.CONF
    conf.register_cli_opts(OPTS)
    conf.register_opts(OPTS)
    conf()

    logging.setup('stackalytics')
    LOG.info('Logging enabled')

    persistent_storage_inst = persistent_storage.get_persistent_storage(
        cfg.CONF.persistent_storage_uri)

    if conf.sync_default_data or conf.force_sync_default_data:
        LOG.info('Going to synchronize persistent storage with default data '
                 'from file %s' % cfg.CONF.default_data)
        persistent_storage_inst.sync(cfg.CONF.default_data,
                                     force=conf.force_sync_default_data)
        return 0

    runtime_storage_inst = runtime_storage.get_runtime_storage(
        cfg.CONF.runtime_storage_uri)

    update_pids(runtime_storage_inst)

    update_repos(runtime_storage_inst, persistent_storage_inst)


if __name__ == '__main__':
    main()
