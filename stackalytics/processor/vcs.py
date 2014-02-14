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

import os
import re
import shutil

import sh
import six

from stackalytics.openstack.common import log as logging
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)


class Vcs(object):
    def __init__(self, repo, sources_root):
        self.repo = repo
        self.sources_root = sources_root
        if not os.path.exists(sources_root):
            os.mkdir(sources_root)
        else:
            if not os.access(sources_root, os.W_OK):
                raise Exception('Sources root folder %s is not writable' %
                                sources_root)

    def fetch(self):
        pass

    def get_release_index(self):
        pass

    def log(self, branch, head_commit_id):
        pass

    def get_last_id(self, branch):
        pass


GIT_LOG_PARAMS = [
    ('commit_id', '%H'),
    ('date', '%at'),
    ('author_name', '%an'),
    ('author_email', '%ae'),
    ('subject', '%s'),
    ('message', '%b'),
]
GIT_LOG_FORMAT = ''.join([(r[0] + ':' + r[1] + '%n')
                          for r in GIT_LOG_PARAMS]) + 'diff_stat:'
DIFF_STAT_PATTERN = ('[^\d]+(\d+)\s+[^\s]*\s+changed'
                     '(,\s+(\d+)\s+([^\d\s]*)\s+(\d+)?)?')
GIT_LOG_PATTERN = re.compile(''.join([(r[0] + ':(.*?)\n')
                                      for r in GIT_LOG_PARAMS]) +
                             'diff_stat:' + DIFF_STAT_PATTERN,
                             re.DOTALL)

CO_AUTHOR_PATTERN_RAW = '(?P<author_name>.+?)\s*<(?P<author_email>.+)>'
CO_AUTHOR_PATTERN = re.compile(CO_AUTHOR_PATTERN_RAW, re.IGNORECASE)

MESSAGE_PATTERNS = {
    'bug_id': re.compile(r'bug[\s#:]*(?P<id>\d+)', re.IGNORECASE),
    'blueprint_id': re.compile(r'\b(?:blueprint|bp)\b[ \t]*[#:]?[ \t]*'
                               r'(?P<id>[a-z0-9-]+)', re.IGNORECASE),
    'change_id': re.compile('Change-Id: (?P<id>I[0-9a-f]{40})', re.IGNORECASE),
    'coauthor': re.compile(r'(?:Co-Authored|Also)-By:'
                           r'\s*(?P<id>%s)\s' % CO_AUTHOR_PATTERN_RAW,
                           re.IGNORECASE)
}


class Git(Vcs):

    def __init__(self, repo, sources_root):
        super(Git, self).__init__(repo, sources_root)
        uri = self.repo['uri']
        match = re.search(r'([^/]+)\.git$', uri)
        if match:
            self.folder = os.path.normpath(self.sources_root + '/' +
                                           match.group(1))
        else:
            raise Exception('Unexpected uri %s for git' % uri)
        self.release_index = {}

    def _checkout(self, branch):
        try:
            sh.git('checkout', 'origin/' + branch)
            return True
        except sh.ErrorReturnCode as e:
            LOG.error('Unable to checkout branch %(branch)s from repo '
                      '%(uri)s. Ignore it',
                      {'branch': branch, 'uri': self.repo['uri']})
            LOG.exception(e)
            return False

    def fetch(self):
        LOG.debug('Fetching repo uri %s' % self.repo['uri'])

        if os.path.exists(self.folder):
            os.chdir(self.folder)
            uri = str(sh.git('config', '--get', 'remote.origin.url')).strip()
            if uri != self.repo['uri']:
                LOG.debug('Repo uri %(uri)s differs from cloned %(old)s',
                          {'uri': self.repo['uri'], 'old': uri})
                os.chdir('..')
                shutil.rmtree(self.folder)

        if not os.path.exists(self.folder):
            os.chdir(self.sources_root)
            try:
                sh.git('clone', self.repo['uri'])
            except sh.ErrorReturnCode as e:
                LOG.error('Unable to clone git repo %s. Ignore it',
                          self.repo['uri'])
                LOG.exception(e)
            os.chdir(self.folder)
        else:
            os.chdir(self.folder)
            try:
                sh.git('fetch')
            except sh.ErrorReturnCode as e:
                LOG.error('Unable to fetch git repo %s. Ignore it',
                          self.repo['uri'])
                LOG.exception(e)

        self.get_release_index()

    def get_release_index(self):
        if not os.path.exists(self.folder):
            return {}

        LOG.debug('Get release index for repo uri: %s', self.repo['uri'])
        os.chdir(self.folder)
        if not self.release_index:
            for release in self.repo.get('releases', []):
                release_name = release['release_name'].lower()

                if 'branch' in release:
                    branch = release['branch']
                else:
                    branch = 'master'
                if not self._checkout(branch):
                    continue

                if 'tag_from' in release:
                    tag_range = release['tag_from'] + '..' + release['tag_to']
                else:
                    tag_range = release['tag_to']
                git_log_iterator = sh.git('log', '--pretty=%H', tag_range,
                                          _tty_out=False)
                for commit_id in git_log_iterator:
                    self.release_index[commit_id.strip()] = release_name
        return self.release_index

    def log(self, branch, head_commit_id):
        LOG.debug('Parsing git log for repo uri %s', self.repo['uri'])

        os.chdir(self.folder)
        if not self._checkout(branch):
            return

        commit_range = 'HEAD'
        if head_commit_id:
            commit_range = head_commit_id + '..HEAD'
        output = sh.git('log', '--pretty=%s' % GIT_LOG_FORMAT, '--shortstat',
                        '-M', '--no-merges', commit_range, _tty_out=False,
                        _decode_errors='ignore')

        for rec in re.finditer(GIT_LOG_PATTERN, str(output)):
            i = 1
            commit = {}
            for param in GIT_LOG_PARAMS:
                commit[param[0]] = six.text_type(rec.group(i), 'utf8')
                i += 1

            if not utils.check_email_validity(commit['author_email']):
                continue

            commit['files_changed'] = int(rec.group(i))
            i += 1
            lines_changed_group = rec.group(i)
            i += 1
            lines_changed = rec.group(i)
            i += 1
            deleted_or_inserted = rec.group(i)
            i += 1
            lines_deleted = rec.group(i)
            i += 1

            if lines_changed_group:  # there inserted or deleted lines
                if not lines_deleted:
                    if deleted_or_inserted[0] == 'd':  # deleted
                        lines_deleted = lines_changed
                        lines_changed = 0

            commit['lines_added'] = int(lines_changed or 0)
            commit['lines_deleted'] = int(lines_deleted or 0)

            for pattern_name, pattern in six.iteritems(MESSAGE_PATTERNS):
                collection = set()
                for item in re.finditer(pattern, commit['message']):
                    collection.add(item.group('id'))
                if collection:
                    commit[pattern_name] = list(collection)

            commit['date'] = int(commit['date'])
            commit['module'] = self.repo['module']
            commit['branches'] = set([branch])
            if commit['commit_id'] in self.release_index:
                commit['release'] = self.release_index[commit['commit_id']]
            else:
                commit['release'] = None

            if 'blueprint_id' in commit:
                commit['blueprint_id'] = [(commit['module'] + ':' + bp_name)
                                          for bp_name
                                          in commit['blueprint_id']]

            if 'coauthor' in commit:
                verified_coauthors = []
                for coauthor in commit['coauthor']:
                    m = re.match(CO_AUTHOR_PATTERN, coauthor)
                    if m and utils.check_email_validity(
                            m.group("author_email")):
                        verified_coauthors.append(m.groupdict())

                if verified_coauthors:
                    commit['coauthor'] = verified_coauthors
                else:
                    del commit['coauthor']  # no valid authors

            yield commit

    def get_last_id(self, branch):
        LOG.debug('Get head commit for repo uri: %s', self.repo['uri'])

        os.chdir(self.folder)
        if not self._checkout(branch):
            return None
        return str(sh.git('rev-parse', 'HEAD')).strip()


def get_vcs(repo, sources_root):
    uri = repo['uri']
    LOG.debug('Factory is asked for VCS uri: %s', uri)
    match = re.search(r'\.git$', uri)
    if match:
        return Git(repo, sources_root)
    else:
        LOG.warning('Unsupported VCS, fallback to dummy')
        return Vcs(repo, uri)
