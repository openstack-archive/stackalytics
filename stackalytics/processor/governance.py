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

from oslo_log import log as logging
import six
import yaml

from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

TAGS = ['tc-approved-release']  # list of supported tags


def read_projects_yaml(project_list_uri):
    LOG.debug('Process list of projects from uri: %s', project_list_uri)
    content = yaml.safe_load(utils.read_uri(project_list_uri))
    module_groups = collections.defaultdict(lambda: {'modules': []})

    for tag in TAGS:
        m = module_groups[tag]  # object created by defaultdict
        m['tag'] = 'project_type'
        m['module_group_name'] = tag

    for name, project in six.iteritems(content):
        group_id = '%s-group' % name.lower()
        module_groups[group_id]['module_group_name'] = '%s Official' % name
        module_groups[group_id]['tag'] = 'program'

        for d_name, deliverable in six.iteritems(project['deliverables']):
            for repo in deliverable['repos']:
                repo_split = repo.split('/')
                if len(repo_split) < 2:
                    continue  # valid repo must be in form of 'org/module'
                module_name = repo_split[1]

                module_groups[group_id]['modules'].append(module_name)

                tags = deliverable.get('tags', [])
                for tag in tags:
                    if tag in TAGS:
                        module_groups[tag]['modules'].append(module_name)

    # set ids for module groups
    for group_id, group in six.iteritems(module_groups):
        group['id'] = group_id
        group['modules'].sort()

    return module_groups
