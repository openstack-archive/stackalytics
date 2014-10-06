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


def make_user_id(email=None, launchpad_id=None, member_id=None):
    if member_id:
        return 'member:%s' % member_id
    else:
        return launchpad_id or email


def store_user(runtime_storage_inst, user):
    if not user.get('seq'):
        user['seq'] = runtime_storage_inst.inc_user_count()
    runtime_storage_inst.set_by_key('user:%s' % user['seq'], user)
    if user.get('user_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['user_id'], user)
    if user.get('launchpad_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['launchpad_id'], user)
    for email in user.get('emails') or []:
        runtime_storage_inst.set_by_key('user:%s' % email, user)


def load_user(runtime_storage_inst, seq=None, user_id=None, email=None,
              launchpad_id=None, member_id=None):
    if member_id:
        key = 'member:%s' % member_id
    else:
        key = seq or user_id or launchpad_id or email
    if key:
        return runtime_storage_inst.get_by_key('user:%s' % key)
    return None


def delete_user(runtime_storage_inst, user):
    runtime_storage_inst.delete_by_key('user:%s' % user['seq'])
