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

import itertools

import jsonschema
from oslo_config import cfg
from oslo_log import log as logging
import psutil
import six

from stackalytics.processor import bps
from stackalytics.processor import config
from stackalytics.processor import default_data_processor
from stackalytics.processor import governance
from stackalytics.processor import lp
from stackalytics.processor import mls
from stackalytics.processor import mps
from stackalytics.processor import rcs
from stackalytics.processor import record_processor
from stackalytics.processor import runtime_storage
from stackalytics.processor import schema
from stackalytics.processor import utils
from stackalytics.processor import vcs
from stackalytics.processor import zanata

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def get_pids():
    result = set([])
    for pid in psutil.pids():
        try:
            p = psutil.Process(pid)
            name = p.name()
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


def _get_repo_branches(repo):
    return ({repo.get('default_branch', 'master')} |
            set(r['branch'] for r in repo.get('releases', [])
                if 'branch' in r))


def _process_repo_blueprints(repo, runtime_storage_inst,
                             record_processor_inst):
    LOG.info('Processing blueprints for repo: %s', repo['uri'])

    bp_iterator = lp.log(repo)
    bp_iterator_typed = _record_typer(bp_iterator, 'bp')
    processed_bp_iterator = record_processor_inst.process(bp_iterator_typed)

    runtime_storage_inst.set_records(processed_bp_iterator,
                                     utils.merge_records)


def _process_repo_bugs(repo, runtime_storage_inst, record_processor_inst):
    LOG.info('Processing bugs for repo: %s', repo['uri'])

    current_date = utils.date_to_timestamp('now')
    bug_modified_since = runtime_storage_inst.get_by_key(
        'bug_modified_since-%s' % repo['module'])

    bug_iterator = bps.log(repo, bug_modified_since)
    bug_iterator_typed = _record_typer(bug_iterator, 'bug')
    processed_bug_iterator = record_processor_inst.process(bug_iterator_typed)

    runtime_storage_inst.set_records(processed_bug_iterator,
                                     utils.merge_records)
    runtime_storage_inst.set_by_key('bug_modified_since-%s' % repo['module'],
                                    current_date)


def _process_repo_reviews(repo, runtime_storage_inst, record_processor_inst,
                          rcs_inst):
    for branch in _get_repo_branches(repo):
        LOG.info('Processing reviews for repo: %s, branch: %s',
                 repo['uri'], branch)

        quoted_uri = six.moves.urllib.parse.quote_plus(repo['uri'])
        rcs_key = 'rcs:%s:%s' % (quoted_uri, branch)
        last_retrieval_time = runtime_storage_inst.get_by_key(rcs_key)
        current_retrieval_time = utils.date_to_timestamp('now')

        review_iterator = itertools.chain(
            rcs_inst.log(repo, branch, last_retrieval_time, status='open'),
            rcs_inst.log(repo, branch, last_retrieval_time, status='merged'),
            rcs_inst.log(repo, branch, last_retrieval_time, status='abandoned',
                         grab_comments=True), )

        review_iterator_typed = _record_typer(review_iterator, 'review')
        processed_review_iterator = record_processor_inst.process(
            review_iterator_typed)

        runtime_storage_inst.set_records(processed_review_iterator,
                                         utils.merge_records)
        runtime_storage_inst.set_by_key(rcs_key, current_retrieval_time)


def _process_repo_vcs(repo, runtime_storage_inst, record_processor_inst):
    vcs_inst = vcs.get_vcs(repo, CONF.sources_root)
    vcs_inst.fetch()

    for branch in _get_repo_branches(repo):
        LOG.info('Processing commits in repo: %s, branch: %s',
                 repo['uri'], branch)

        quoted_uri = six.moves.urllib.parse.quote_plus(repo['uri'])
        vcs_key = 'vcs:%s:%s' % (quoted_uri, branch)
        last_id = runtime_storage_inst.get_by_key(vcs_key)

        commit_iterator = vcs_inst.log(branch, last_id)
        commit_iterator_typed = _record_typer(commit_iterator, 'commit')
        processed_commit_iterator = record_processor_inst.process(
            commit_iterator_typed)
        runtime_storage_inst.set_records(
            processed_commit_iterator, _merge_commits)

        last_id = vcs_inst.get_last_id(branch)
        runtime_storage_inst.set_by_key(vcs_key, last_id)


def _process_repo(repo, runtime_storage_inst, record_processor_inst,
                  rcs_inst):
    LOG.info('Processing repo: %s', repo['uri'])

    _process_repo_vcs(repo, runtime_storage_inst, record_processor_inst)

    _process_repo_bugs(repo, runtime_storage_inst, record_processor_inst)

    _process_repo_blueprints(repo, runtime_storage_inst, record_processor_inst)

    if 'has_gerrit' in repo:
        _process_repo_reviews(repo, runtime_storage_inst,
                              record_processor_inst, rcs_inst)


def _process_mail_list(uri, runtime_storage_inst, record_processor_inst):
    mail_iterator = mls.log(uri, runtime_storage_inst)
    mail_iterator_typed = _record_typer(mail_iterator, 'email')
    processed_mail_iterator = record_processor_inst.process(
        mail_iterator_typed)
    runtime_storage_inst.set_records(processed_mail_iterator)


def _process_translation_stats(runtime_storage_inst, record_processor_inst):
    translation_iterator = zanata.log(runtime_storage_inst,
                                      CONF.translation_team_uri)
    translation_iterator_typed = _record_typer(translation_iterator, 'i18n')
    processed_translation_iterator = record_processor_inst.process(
        translation_iterator_typed)
    runtime_storage_inst.set_records(processed_translation_iterator)


def _process_member_list(uri, runtime_storage_inst, record_processor_inst):
    member_iterator = mps.log(uri, runtime_storage_inst,
                              CONF.days_to_update_members,
                              CONF.members_look_ahead)
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
        vcs_inst = vcs.get_vcs(repo, CONF.sources_root)
        release_index.update(vcs_inst.fetch())

    LOG.debug('Post-process all records')
    record_processor_inst.post_processing(release_index)


def process(runtime_storage_inst, record_processor_inst):
    repos = utils.load_repos(runtime_storage_inst)

    rcs_inst = rcs.get_rcs(CONF.review_uri)
    rcs_inst.setup(key_filename=CONF.ssh_key_filename,
                   username=CONF.ssh_username,
                   gerrit_retry=CONF.gerrit_retry)

    for repo in repos:
        _process_repo(repo, runtime_storage_inst, record_processor_inst,
                      rcs_inst)

    rcs_inst.close()

    LOG.info('Processing mail lists')
    mail_lists = runtime_storage_inst.get_by_key('mail_lists') or []
    for mail_list in mail_lists:
        _process_mail_list(mail_list, runtime_storage_inst,
                           record_processor_inst)

    LOG.info('Processing translations stats')
    _process_translation_stats(runtime_storage_inst, record_processor_inst)

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
            LOG.warning('Correction misses primary key: %s', c)
    runtime_storage_inst.apply_corrections(valid_corrections)


def process_project_list(runtime_storage_inst):
    module_groups = runtime_storage_inst.get_by_key('module_groups') or {}
    releases = runtime_storage_inst.get_by_key('releases') or {}

    official_module_groups = governance.process_official_list(releases)

    LOG.debug('Update module groups with official: %s', official_module_groups)
    module_groups.update(official_module_groups)

    # make list of OpenStack unofficial projects
    others = module_groups.get('openstack-others')
    off_rm = module_groups.get('openstack-official', {}).get('releases')
    official = dict((r, set(m)) for r, m in six.iteritems(off_rm))

    for module in module_groups.get('openstack', {}).get('modules', []):
        for r, off_m in six.iteritems(official):
            if module not in off_m:
                others['releases'][r].add(module)

    # register modules as module groups
    repos = runtime_storage_inst.get_by_key('repos') or []
    for repo in repos:
        module = repo['module'].lower()
        module_groups[module] = utils.make_module_group(module, tag='module')

    # register module 'unknown' - used for emails not mapped to any module
    module_groups['unknown'] = utils.make_module_group('unknown', tag='module')

    runtime_storage_inst.set_by_key('module_groups', module_groups)


def main():
    utils.init_config_and_logging(config.CONNECTION_OPTS +
                                  config.PROCESSOR_OPTS)

    runtime_storage_inst = runtime_storage.get_runtime_storage(
        CONF.runtime_storage_uri)

    default_data = utils.read_json_from_uri(CONF.default_data_uri)
    if not default_data:
        LOG.critical('Unable to load default data')
        return not 0

    try:
        jsonschema.validate(default_data, schema.default_data)
    except jsonschema.ValidationError as e:
        LOG.critical('The default data is invalid: %s' % e)
        return not 0

    default_data_processor.process(runtime_storage_inst,
                                   default_data)

    process_project_list(runtime_storage_inst)

    update_pids(runtime_storage_inst)

    record_processor_inst = record_processor.RecordProcessor(
        runtime_storage_inst)

    process(runtime_storage_inst, record_processor_inst)

    apply_corrections(CONF.corrections_uri, runtime_storage_inst)

    # long operation should be the last
    update_members(runtime_storage_inst, record_processor_inst)

    runtime_storage_inst.set_by_key('runtime_storage_update_time',
                                    utils.date_to_timestamp('now'))
    LOG.info('stackalytics-processor succeeded.')


if __name__ == '__main__':
    main()
