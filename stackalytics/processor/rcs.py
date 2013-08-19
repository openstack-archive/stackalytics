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

import paramiko

from stackalytics.openstack.common import log as logging


LOG = logging.getLogger(__name__)

DEFAULT_PORT = 29418
GERRIT_URI_PREFIX = r'^gerrit:\/\/'
PAGE_LIMIT = 100


class Rcs(object):
    def __init__(self, repo, uri):
        self.repo = repo

    def setup(self, **kwargs):
        pass

    def log(self, branch, last_id):
        return []

    def get_last_id(self, branch):
        return -1


class Gerrit(Rcs):
    def __init__(self, repo, uri):
        super(Gerrit, self).__init__(repo, uri)

        stripped = re.sub(GERRIT_URI_PREFIX, '', uri)
        if stripped:
            self.hostname, semicolon, self.port = stripped.partition(':')
            if not self.port:
                self.port = DEFAULT_PORT
        else:
            raise Exception('Invalid rcs uri %s' % uri)

        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def setup(self, **kwargs):
        if 'key_filename' in kwargs:
            self.key_filename = kwargs['key_filename']
        else:
            self.key_filename = None

        if 'username' in kwargs:
            self.username = kwargs['username']
        else:
            self.username = None

    def _connect(self):
        self.client.connect(self.hostname, port=self.port,
                            key_filename=self.key_filename,
                            username=self.username)
        LOG.debug('Successfully connected to Gerrit')

    def _get_cmd(self, project_organization, module, branch, sort_key,
                 is_open):
        cmd = ('gerrit query --all-approvals --patch-sets --format JSON '
               'project:\'%(ogn)s/%(module)s\' branch:%(branch)s '
               'limit:%(limit)s' %
               {'ogn': project_organization, 'module': module,
                'branch': branch, 'limit': PAGE_LIMIT})
        if is_open:
            cmd += ' is:open'
        if sort_key:
            cmd += ' resume_sortkey:%016x' % sort_key
        return cmd

    def _poll_reviews(self, project_organization, module, branch,
                      start_id=None, last_id=None, is_open=False):
        sort_key = start_id

        while True:
            cmd = self._get_cmd(project_organization, module, branch, sort_key,
                                is_open)
            LOG.debug('Executing command: %s', cmd)
            stdin, stdout, stderr = self.client.exec_command(cmd)

            proceed = False
            for line in stdout:
                review = json.loads(line)

                if 'sortKey' in review:
                    sort_key = int(review['sortKey'], 16)
                    if sort_key == last_id:
                        proceed = False
                        break

                    proceed = True
                    review['module'] = module
                    yield review

            if not proceed:
                break

    def log(self, branch, last_id):
        match = re.search(r'([^\/]+)/([^\/]+)\.git$', self.repo['uri'])
        if not match:
            LOG.error('Invalid repo uri: %s', self.repo['uri'])
        project_organization = match.group(1)
        module = match.group(2)

        self._connect()

        # poll new reviews from the top down to last_id
        LOG.debug('Poll new reviews')
        for review in self._poll_reviews(project_organization, module, branch,
                                         last_id=last_id):
            yield review

        # poll open reviews from last_id down to bottom
        LOG.debug('Poll open reviews')
        for review in self._poll_reviews(project_organization, module, branch,
                                         start_id=last_id + 1, is_open=True):
            yield review

        self.client.close()

    def get_last_id(self, branch):
        module = self.repo['module']
        LOG.debug('Get last id for module %s', module)

        self._connect()

        cmd = ('gerrit query --all-approvals --patch-sets --format JSON '
               '%(module)s branch:%(branch)s limit:1' %
               {'module': module, 'branch': branch})

        stdin, stdout, stderr = self.client.exec_command(cmd)
        last_id = None
        for line in stdout:
            review = json.loads(line)
            if 'sortKey' in review:
                last_id = int(review['sortKey'], 16)
                break

        self.client.close()

        LOG.debug('Last id for module %s is %s', module, last_id)
        return last_id


def get_rcs(repo, uri):
    LOG.debug('Review control system is requested for uri %s' % uri)
    match = re.search(GERRIT_URI_PREFIX, uri)
    if match:
        return Gerrit(repo, uri)
    else:
        LOG.warning('Unsupported review control system, fallback to dummy')
        return Rcs(repo, uri)
