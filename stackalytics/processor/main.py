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

import collections

from oslo.config import cfg
import psutil
import six
import yaml

from stackalytics.openstack.common import log as logging
from stackalytics.openstack.common.py3kcompat import urlutils
from stackalytics.processor import config
from stackalytics.processor import default_data_processor
from stackalytics.processor import lp
from stackalytics.processor import mls
from stackalytics.processor import rcs
from stackalytics.processor import record_processor
from stackalytics.processor import runtime_storage
from stackalytics.processor import utils
from stackalytics.processor import vcs


LOG = logging.getLogger(__name__)


def get_pids():
    uwsgi_dict = {}
    for pid in psutil.get_pid_list():
        try:
            p = psutil.Process(pid)
            if p.cmdline and p.cmdline[0].find('/uwsgi'):
                if p.parent:
                    uwsgi_dict[p.pid] = p.parent.pid
        except Exception as e:
            LOG.debug('Exception while iterating process list: %s', e)
            pass

    result = set()
    for pid in uwsgi_dict:
        if uwsgi_dict[pid] in uwsgi_dict:
            result.add(pid)

    return result


def update_pids(runtime_storage):
    pids = get_pids()
    if not pids:
        return
    runtime_storage.active_pids(pids)


def _merge_commits(original, new):
    if new['branches'] < original['branches']:
        return False
    else:
        original['branches'] |= new['branches']
        return True


def _record_typer(record_iterator, record_type):
    for record in record_iterator:
        record['record_type'] = record_type
        yield record


def process_repo(repo, runtime_storage_inst, record_processor_inst):
    uri = repo['uri']
    LOG.debug('Processing repo uri %s' % uri)

    bp_iterator = lp.log(repo)
    bp_iterator_typed = _record_typer(bp_iterator, 'bp')
    processed_bp_iterator = record_processor_inst.process(
        bp_iterator_typed)
    runtime_storage_inst.set_records(processed_bp_iterator,
                                     utils.merge_records)

    vcs_inst = vcs.get_vcs(repo, cfg.CONF.sources_root)
    vcs_inst.fetch()

    rcs_inst = rcs.get_rcs(repo, cfg.CONF.review_uri)
    rcs_inst.setup(key_filename=cfg.CONF.ssh_key_filename,
                   username=cfg.CONF.ssh_username)

    branches = set(['master'])
    for release in repo.get('releases'):
        if 'branch' in release:
            branches.add(release['branch'])

    for branch in branches:
        LOG.debug('Processing repo %s, branch %s', uri, branch)

        vcs_key = 'vcs:' + str(urlutils.quote_plus(uri) + ':' + branch)
        last_id = runtime_storage_inst.get_by_key(vcs_key)

        commit_iterator = vcs_inst.log(branch, last_id)
        commit_iterator_typed = _record_typer(commit_iterator, 'commit')
        processed_commit_iterator = record_processor_inst.process(
            commit_iterator_typed)
        runtime_storage_inst.set_records(
            processed_commit_iterator, _merge_commits)

        last_id = vcs_inst.get_last_id(branch)
        runtime_storage_inst.set_by_key(vcs_key, last_id)

        LOG.debug('Processing reviews for repo %s, branch %s', uri, branch)

        rcs_key = 'rcs:' + str(urlutils.quote_plus(uri) + ':' + branch)
        last_id = runtime_storage_inst.get_by_key(rcs_key)

        review_iterator = rcs_inst.log(branch, last_id)
        review_iterator_typed = _record_typer(review_iterator, 'review')
        processed_review_iterator = record_processor_inst.process(
            review_iterator_typed)
        runtime_storage_inst.set_records(processed_review_iterator,
                                         utils.merge_records)

        last_id = rcs_inst.get_last_id(branch)
        runtime_storage_inst.set_by_key(rcs_key, last_id)


def process_mail_list(uri, runtime_storage_inst, record_processor_inst):
    mail_iterator = mls.log(uri, runtime_storage_inst)
    mail_iterator_typed = _record_typer(mail_iterator, 'email')
    processed_mail_iterator = record_processor_inst.process(
        mail_iterator_typed)
    runtime_storage_inst.set_records(processed_mail_iterator)


def update_records(runtime_storage_inst):
    repos = utils.load_repos(runtime_storage_inst)
    record_processor_inst = record_processor.RecordProcessor(
        runtime_storage_inst)

    for repo in repos:
        process_repo(repo, runtime_storage_inst, record_processor_inst)

    mail_lists = runtime_storage_inst.get_by_key('mail_lists') or []
    for mail_list in mail_lists:
        process_mail_list(mail_list, runtime_storage_inst,
                          record_processor_inst)

    record_processor_inst.update()


def apply_corrections(uri, runtime_storage_inst):
    LOG.info('Applying corrections from uri %s', uri)
    corrections = utils.read_json_from_uri(uri)
    if not corrections:
        LOG.error('Unable to read corrections from uri: %s', uri)
        return

    valid_corrections = []
    for c in corrections['corrections']:
        if 'primary_key' in c:
            valid_corrections.append(c)
        else:
            LOG.warn('Correction misses primary key: %s', c)
    runtime_storage_inst.apply_corrections(valid_corrections)


def _make_module_group(group_id, name, modules, tag=None):
    module_group = {'id': group_id, 'module_group_name': name,
                    'modules': modules, 'tag': tag}
    LOG.debug('New module group: %s', module_group)
    return module_group


def _read_module_groups(program_list_uri):
    LOG.debug('Process list of programs from uri: %s', program_list_uri)
    content = yaml.safe_load(utils.read_uri(program_list_uri))
    module_groups = []
    modules_by_types = collections.defaultdict(list)
    for name, info in six.iteritems(content):
        group_id = name.lower()
        if 'codename' in info:
            name = '%s (%s)' % (info['codename'], name)
            group_id = '%s-group' % info['codename'].lower()

        all_modules = []
        for project_type, project_list in six.iteritems(info['projects']):
            module_list = [s.split('/')[1] for s in project_list]
            modules_by_types[project_type] += module_list
            all_modules += module_list

        module_groups.append(_make_module_group(
            group_id, name, all_modules, 'program'))

    all_modules = []
    for project_type, modules_list in six.iteritems(modules_by_types):
        all_modules += modules_list
        module_groups.append(
            _make_module_group(
                'official-%s' % project_type, project_type.capitalize(),
                modules_list, 'project_type'))
    module_groups.append(_make_module_group(
        'official-all', 'OpenStack', all_modules, 'project_type'))
    return module_groups


def process_program_list(runtime_storage_inst, program_list_uri):
    module_groups = runtime_storage_inst.get_by_key('module_groups') or {}
    for mg in _read_module_groups(program_list_uri):
        module_groups[mg['module_group_name']] = mg
    runtime_storage_inst.set_by_key('module_groups', module_groups)


def main():
    # init conf and logging
    conf = cfg.CONF
    conf.register_cli_opts(config.OPTS)
    conf.register_opts(config.OPTS)
    conf()

    logging.setup('stackalytics')
    LOG.info('Logging enabled')

    runtime_storage_inst = runtime_storage.get_runtime_storage(
        cfg.CONF.runtime_storage_uri)

    default_data = utils.read_json_from_uri(cfg.CONF.default_data_uri)
    if not default_data:
        LOG.critical('Unable to load default data')
        return not 0
    default_data_processor.process(runtime_storage_inst,
                                   default_data,
                                   cfg.CONF.sources_root,
                                   cfg.CONF.force_update)

    process_program_list(runtime_storage_inst, cfg.CONF.program_list_uri)

    update_pids(runtime_storage_inst)

    update_records(runtime_storage_inst)

    apply_corrections(cfg.CONF.corrections_uri, runtime_storage_inst)


if __name__ == '__main__':
    main()
