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

from stackalytics.openstack.common import log as logging
from stackalytics.processor import normalizer
from stackalytics.processor import persistent_storage
from stackalytics.processor import record_processor
from stackalytics.processor import vcs

LOG = logging.getLogger(__name__)


def _update_persistent_storage(persistent_storage_inst, default_data):

    need_update = False

    for table, primary_key in persistent_storage.PRIMARY_KEYS.iteritems():
        for item in default_data[table]:
            param = {primary_key: item[primary_key]}
            for p_item in persistent_storage_inst.find(table, **param):
                break
            else:
                p_item = None

            if item != p_item:
                need_update = True
                if p_item:
                    persistent_storage_inst.update(table, item)
                else:
                    persistent_storage_inst.insert(table, item)

    return need_update


def process(persistent_storage_inst, runtime_storage_inst, default_data,
            sources_root):

    normalizer.normalize_default_data(default_data)

    if _update_persistent_storage(persistent_storage_inst, default_data):

        release_index = {}
        for repo in persistent_storage_inst.find('repos'):
            vcs_inst = vcs.get_vcs(repo, sources_root)
            release_index.update(vcs_inst.get_release_index())

        persistent_storage_inst.reset(default_data)
        record_processor_inst = record_processor.RecordProcessor(
            persistent_storage_inst)
        updated_records = record_processor_inst.update(
            runtime_storage_inst.get_all_records(), release_index)
        runtime_storage_inst.set_records(updated_records)
