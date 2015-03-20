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

import json
import re

from oslo_log import log as logging
import paramiko


LOG = logging.getLogger(__name__)

DEFAULT_PORT = 29418
GERRIT_URI_PREFIX = r'^gerrit:\/\/'
PAGE_LIMIT = 100
REQUEST_COUNT_LIMIT = 20


class Rcs(object):
    def __init__(self):
        pass

    def setup(self, **kwargs):
        return True

    def get_project_list(self):
        pass

    def log(self, repo, branch, last_id):
        return []

    def get_last_id(self, repo, branch):
        return -1

    def close(self):
        pass


class Gerrit(Rcs):
    def __init__(self, uri):
        super(Gerrit, self).__init__()

        stripped = re.sub(GERRIT_URI_PREFIX, '', uri)
        if stripped:
            self.hostname, semicolon, self.port = stripped.partition(':')
            if not self.port:
                self.port = DEFAULT_PORT
        else:
            raise Exception('Invalid rcs uri %s' % uri)

        self.key_filename = None
        self.username = None

        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self.request_count = 0

    def setup(self, **kwargs):
        self.key_filename = kwargs.get('key_filename')
        self.username = kwargs.get('username')

        return self._connect()

    def _connect(self):
        try:
            self.client.connect(self.hostname, port=self.port,
                                key_filename=self.key_filename,
                                username=self.username)
            LOG.debug('Successfully connected to Gerrit')
            return True
        except Exception as e:
            LOG.error('Failed to connect to gerrit %(host)s:%(port)s. '
                      'Error: %(err)s', {'host': self.hostname,
                                         'port': self.port, 'err': e})
            LOG.exception(e)
            return False

    def _get_cmd(self, project_organization, module, branch, sort_key=None,
                 is_open=False, limit=PAGE_LIMIT, grab_comments=False):
        cmd = ('gerrit query --all-approvals --patch-sets --format JSON '
               'project:\'%(ogn)s/%(module)s\' branch:%(branch)s '
               'limit:%(limit)s' %
               {'ogn': project_organization, 'module': module,
                'branch': branch, 'limit': limit})
        if is_open:
            cmd += ' is:open'
        if sort_key:
            cmd += ' resume_sortkey:%016x' % sort_key
        if grab_comments:
            cmd += ' --comments'
        return cmd

    def _exec_command(self, cmd):
        # check how many requests were sent over connection and reconnect
        if self.request_count >= REQUEST_COUNT_LIMIT:
            self.close()
            self.request_count = 0
            self._connect()
        else:
            self.request_count += 1

        try:
            return self.client.exec_command(cmd)
        except Exception as e:
            LOG.error('Error %(error)s while execute command %(cmd)s',
                      {'error': e, 'cmd': cmd})
            LOG.exception(e)
            self.request_count = REQUEST_COUNT_LIMIT
            return False

    def _poll_reviews(self, project_organization, module, branch,
                      start_id=0, last_id=0, is_open=False,
                      grab_comments=False):
        sort_key = start_id

        while True:
            cmd = self._get_cmd(project_organization, module, branch, sort_key,
                                is_open, grab_comments=grab_comments)
            LOG.debug('Executing command: %s', cmd)
            exec_result = self._exec_command(cmd)
            if not exec_result:
                break
            stdin, stdout, stderr = exec_result

            proceed = False
            for line in stdout:
                review = json.loads(line)

                if 'sortKey' in review:
                    sort_key = int(review['sortKey'], 16)
                    if sort_key <= last_id:
                        proceed = False
                        break

                    proceed = True
                    review['module'] = module
                    yield review

            if not proceed:
                break

    def get_project_list(self):
        exec_result = self._exec_command('gerrit ls-projects')
        if not exec_result:
            raise Exception("Unable to retrieve list of projects from gerrit.")
        stdin, stdout, stderr = exec_result
        result = [line.strip() for line in stdout]

        return result

    def log(self, repo, branch, last_id, grab_comments=False):
        # poll new reviews from the top down to last_id
        LOG.debug('Poll new reviews for module: %s', repo['module'])
        for review in self._poll_reviews(repo['organization'],
                                         repo['module'], branch,
                                         last_id=last_id,
                                         grab_comments=grab_comments):
            yield review

        # poll open reviews from last_id down to bottom
        LOG.debug('Poll open reviews for module: %s', repo['module'])
        start_id = None
        if last_id:
            start_id = last_id + 1  # include the last review into query
        for review in self._poll_reviews(repo['organization'],
                                         repo['module'], branch,
                                         start_id=start_id, is_open=True,
                                         grab_comments=grab_comments):
            yield review

    def get_last_id(self, repo, branch):
        LOG.debug('Get last id for module: %s', repo['module'])

        cmd = self._get_cmd(repo['organization'], repo['module'],
                            branch, limit=1)
        LOG.debug('Executing command: %s', cmd)
        exec_result = self._exec_command(cmd)
        if not exec_result:
            return None
        stdin, stdout, stderr = exec_result

        last_id = None
        for line in stdout:
            review = json.loads(line)
            if 'sortKey' in review:
                last_id = int(review['sortKey'], 16)
                break

        LOG.debug('Module %(module)s last id is %(id)s',
                  {'module': repo['module'], 'id': last_id})
        return last_id

    def close(self):
        self.client.close()


def get_rcs(uri):
    LOG.debug('Review control system is requested for uri %s' % uri)
    match = re.search(GERRIT_URI_PREFIX, uri)
    if match:
        return Gerrit(uri)
    else:
        LOG.warning('Unsupported review control system, fallback to dummy')
        return Rcs()
