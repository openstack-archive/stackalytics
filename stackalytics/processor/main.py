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
from six.moves.urllib import parse
import yaml

from stackalytics.openstack.common import log as logging
from stackalytics.processor import bps
from stackalytics.processor import config
from stackalytics.processor import default_data_processor
from stackalytics.processor import lp
from stackalytics.processor import mls
from stackalytics.processor import mps
from stackalytics.processor import rcs
from stackalytics.processor import record_processor
from stackalytics.processor import runtime_storage
from stackalytics.processor import utils
from stackalytics.processor import vcs


LOG = logging.getLogger(__name__)


def get_pids():
    # needs to be compatible with psutil >= 1.1.1 since it's a global req.
    PSUTIL2 = psutil.version_info >= (2, 0)
    result = set([])
    for pid in psutil.get_pid_list():
        try:
            p = psutil.Process(pid)
            name = p.name() if PSUTIL2 else p.name
            if name == 'uwsgi':
                LOG.debug('Found uwsgi process, pid: %s', pid)
                result.add(pid)
        except Exception as e:
            LOG.debug('Exception while iterating process list: %s', e)
            pass

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


def _process_repo(repo, runtime_storage_inst, record_processor_inst,
                  bug_modified_since):
    uri = repo['uri']
    LOG.info('Processing repo uri: %s', uri)

    LOG.debug('Processing blueprints for repo uri: %s', uri)
    bp_iterator = lp.log(repo)
    bp_iterator_typed = _record_typer(bp_iterator, 'bp')
    processed_bp_iterator = record_processor_inst.process(
        bp_iterator_typed)
    runtime_storage_inst.set_records(processed_bp_iterator,
                                     utils.merge_records)

    LOG.debug('Processing bugs for repo uri: %s', uri)
    bug_iterator = bps.log(repo, bug_modified_since)
    bug_iterator_typed = _record_typer(bug_iterator, 'bug')
    processed_bug_iterator = record_processor_inst.process(
        bug_iterator_typed)
    runtime_storage_inst.set_records(processed_bug_iterator,
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
        LOG.debug('Processing commits in repo: %s, branch: %s', uri, branch)

        vcs_key = 'vcs:' + str(parse.quote_plus(uri) + ':' + branch)
        last_id = runtime_storage_inst.get_by_key(vcs_key)

        commit_iterator = vcs_inst.log(branch, last_id)
        commit_iterator_typed = _record_typer(commit_iterator, 'commit')
        processed_commit_iterator = record_processor_inst.process(
            commit_iterator_typed)
        runtime_storage_inst.set_records(
            processed_commit_iterator, _merge_commits)

        last_id = vcs_inst.get_last_id(branch)
        runtime_storage_inst.set_by_key(vcs_key, last_id)

        LOG.debug('Processing reviews for repo: %s, branch: %s', uri, branch)

        rcs_key = 'rcs:' + str(parse.quote_plus(uri) + ':' + branch)
        last_id = runtime_storage_inst.get_by_key(rcs_key)

        review_iterator = rcs_inst.log(branch, last_id)
        review_iterator_typed = _record_typer(review_iterator, 'review')
        processed_review_iterator = record_processor_inst.process(
            review_iterator_typed)
        runtime_storage_inst.set_records(processed_review_iterator,
                                         utils.merge_records)

        last_id = rcs_inst.get_last_id(branch)
        runtime_storage_inst.set_by_key(rcs_key, last_id)


def _process_mail_list(uri, runtime_storage_inst, record_processor_inst):
    mail_iterator = mls.log(uri, runtime_storage_inst)
    mail_iterator_typed = _record_typer(mail_iterator, 'email')
    processed_mail_iterator = record_processor_inst.process(
        mail_iterator_typed)
    runtime_storage_inst.set_records(processed_mail_iterator)


def _process_member_list(uri, runtime_storage_inst, record_processor_inst):
    member_iterator = mps.log(uri, runtime_storage_inst,
                              cfg.CONF.days_to_update_members)
    member_iterator_typed = _record_typer(member_iterator, 'member')
    processed_member_iterator = record_processor_inst.process(
        member_iterator_typed)
    runtime_storage_inst.set_records(processed_member_iterator)


def update_members(runtime_storage_inst, record_processor_inst):
    member_lists = runtime_storage_inst.get_by_key('member_lists') or []
    for member_list in member_lists:
        _process_member_list(member_list, runtime_storage_inst,
                             record_processor_inst)


def _post_process_records(record_processor_inst, repos):
    LOG.debug('Build release index')
    release_index = {}
    for repo in repos:
        vcs_inst = vcs.get_vcs(repo, cfg.CONF.sources_root)
        release_index.update(vcs_inst.fetch())

    LOG.debug('Post-process all records')
    record_processor_inst.post_processing(release_index)


def process(runtime_storage_inst, record_processor_inst):
    repos = utils.load_repos(runtime_storage_inst)

    current_date = utils.date_to_timestamp('now')
    bug_modified_since = runtime_storage_inst.get_by_key('bug_modified_since')
    for repo in repos:
        _process_repo(repo, runtime_storage_inst, record_processor_inst,
                      bug_modified_since)
    runtime_storage_inst.set_by_key('bug_modified_since', current_date)

    LOG.info('Processing mail lists')
    mail_lists = runtime_storage_inst.get_by_key('mail_lists') or []
    for mail_list in mail_lists:
        _process_mail_list(mail_list, runtime_storage_inst,
                           record_processor_inst)

    _post_process_records(record_processor_inst, repos)


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


def _read_official_programs_yaml(program_list_uri, release_names):
    LOG.debug('Process list of programs from uri: %s', program_list_uri)
    content = yaml.safe_load(utils.read_uri(program_list_uri))
    module_groups = collections.defaultdict(
        lambda: {'modules': [], 'releases': collections.defaultdict(list)})

    official_integrated = module_groups['official-integrated']
    official_integrated['tag'] = 'project_type'
    official_integrated['module_group_name'] = 'official-integrated'
    official_incubated = module_groups['official-incubated']
    official_incubated['tag'] = 'project_type'
    official_incubated['module_group_name'] = 'official-incubated'
    official_other = module_groups['official-other']
    official_other['tag'] = 'project_type'
    official_other['module_group_name'] = 'official-other'

    for name, info in six.iteritems(content):
        # for one program
        group_id = name.lower()
        if 'codename' in info:
            name = '%s (%s)' % (info['codename'], name)
            group_id = '%s-group' % info['codename'].lower()

        module_groups[group_id]['module_group_name'] = name
        module_groups[group_id]['tag'] = 'program'

        for module in info['projects']:
            module_name = module['repo'].split('/')[1]

            module_groups[group_id]['modules'].append(module_name)

            if ('integrated-since' in module) or ('incubated-since' in module):
                project_type = 'official-other'
                for release_name in release_names:
                    if release_name == module.get('incubated-since'):
                        project_type = 'official-incubated'
                    elif release_name == module.get('integrated-since'):
                        project_type = 'official-integrated'

                    module_groups[project_type]['releases'][
                        release_name].append(module_name)
            else:
                module_groups['official-other']['modules'].append(module_name)

    # set ids for module groups
    for group_id, group in six.iteritems(module_groups):
        group['id'] = group_id

    return module_groups


def process_program_list(runtime_storage_inst, program_list_uri):
    module_groups = runtime_storage_inst.get_by_key('module_groups') or {}
    release_names = [r['release_name'].lower()
                     for r in runtime_storage_inst.get_by_key('releases')[1:]]

    official_module_groups = _read_official_programs_yaml(
        program_list_uri, release_names)
    LOG.debug('Update module groups with official: %s', official_module_groups)
    module_groups.update(official_module_groups)

    # register modules as module groups
    repos = runtime_storage_inst.get_by_key('repos') or []
    for repo in repos:
        module = repo['module']
        module_groups[module] = utils.make_module_group(module, tag='module')

    # register module 'unknown' - used for emails not mapped to any module
    module_groups['unknown'] = utils.make_module_group('unknown', tag='module')

    runtime_storage_inst.set_by_key('module_groups', module_groups)


def main():
    # init conf and logging
    conf = cfg.CONF
    conf.register_cli_opts(config.OPTS)
    conf.register_opts(config.OPTS)
    conf(project='stackalytics')

    logging.setup('stackalytics')
    LOG.info('Logging enabled')

    runtime_storage_inst = runtime_storage.get_runtime_storage(
        cfg.CONF.runtime_storage_uri)

    default_data = utils.read_json_from_uri(cfg.CONF.default_data_uri)
    if not default_data:
        LOG.critical('Unable to load default data')
        return not 0

    gerrit = rcs.get_rcs(None, cfg.CONF.review_uri)
    gerrit.setup(key_filename=cfg.CONF.ssh_key_filename,
                 username=cfg.CONF.ssh_username)

    default_data_processor.process(runtime_storage_inst,
                                   default_data,
                                   cfg.CONF.git_base_uri,
                                   gerrit)

    process_program_list(runtime_storage_inst, cfg.CONF.program_list_uri)

    update_pids(runtime_storage_inst)

    record_processor_inst = record_processor.RecordProcessor(
        runtime_storage_inst)

    process(runtime_storage_inst, record_processor_inst)

    apply_corrections(cfg.CONF.corrections_uri, runtime_storage_inst)

    # long operation should be the last
    update_members(runtime_storage_inst, record_processor_inst)

    runtime_storage_inst.set_by_key('runtime_storage_update_time',
                                    utils.date_to_timestamp('now'))


if __name__ == '__main__':
    main()
