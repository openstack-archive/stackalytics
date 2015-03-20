# Copyright (c) 2014 Mirantis Inc.
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

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


def make_user_id(emails=None, launchpad_id=None, gerrit_id=None,
                 member_id=None, github_id=None, ldap_id=None):
    if launchpad_id or emails:
        return launchpad_id or emails[0]
    if gerrit_id:
        return 'gerrit:%s' % gerrit_id
    if member_id:
        return 'member:%s' % member_id
    if github_id:
        return 'github:%s' % github_id
    if ldap_id:
        return 'ldap:%s' % ldap_id


def store_user(runtime_storage_inst, user):
    write_flag = False

    if not user.get('seq'):
        user['seq'] = runtime_storage_inst.inc_user_count()
        LOG.debug('New user: %s', user)
        write_flag = True
    else:
        stored_user = runtime_storage_inst.get_by_key(
            'user:%d' % user.get('seq'))
        if stored_user != user:
            LOG.debug('User updated: %s', user)
            write_flag = True

    if not write_flag:
        return

    runtime_storage_inst.set_by_key('user:%d' % user['seq'], user)
    if user.get('user_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['user_id'], user)
    if user.get('launchpad_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['launchpad_id'], user)
    if user.get('gerrit_id'):
        runtime_storage_inst.set_by_key('user:gerrit:%s' % user['gerrit_id'],
                                        user)
    if user.get('github_id'):
        runtime_storage_inst.set_by_key('user:github:%s' % user['github_id'],
                                        user)
    if user.get('ldap_id'):
        runtime_storage_inst.set_by_key('user:ldap:%s' % user['ldap_id'],
                                        user)
    for email in user.get('emails') or []:
        runtime_storage_inst.set_by_key('user:%s' % email, user)


def load_user(runtime_storage_inst, seq=None, user_id=None, email=None,
              launchpad_id=None, gerrit_id=None, member_id=None,
              github_id=None, ldap_id=None):
    if gerrit_id:
        key = 'gerrit:%s' % gerrit_id
    elif member_id:
        key = 'member:%s' % member_id
    elif github_id:
        key = 'github:%s' % github_id
    elif ldap_id:
        key = 'ldap:%s' % ldap_id
    else:
        key = seq or user_id or launchpad_id or email
    if key:
        return runtime_storage_inst.get_by_key('user:%s' % key)
    return None


def delete_user(runtime_storage_inst, user):
    LOG.debug('Delete user: %s', user)
    runtime_storage_inst.delete_by_key('user:%s' % user['seq'])
