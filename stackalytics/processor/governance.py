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

# list of supported tags
TAGS = ['tc:approved-release', 'type:service', 'type:library']


def _make_module_group(module_groups, name):
    m = module_groups[name]  # object created by defaultdict
    m['tag'] = 'project_type'
    m['module_group_name'] = name
    m['releases'] = collections.defaultdict(set)
    return m


def read_legacy_programs_yaml(module_groups, release_name, content):
    all_official = module_groups['openstack-official']

    for name, info in six.iteritems(content):
        for module in info['projects']:
            mn = module['repo'].split('/')[1]  # module_name

            # module_groups[group_id]['releases'][release_name].append(mn)
            all_official['releases'][release_name].add(mn)


def read_early_big_tent_projects_yaml(module_groups, release_name, content):
    all_official = module_groups['openstack-official']

    for name, info in six.iteritems(content):
        for module in info['projects']:
            repo_split = module['repo'].split('/')
            if len(repo_split) < 2:
                continue  # valid repo must be in form of 'org/module'
            mn = repo_split[1]

            # module_groups[group_id]['releases'][release_name].append(mn)
            all_official['releases'][release_name].add(mn)


def read_big_tent_projects_yaml(module_groups, release_name, content):
    all_official = module_groups['openstack-official']

    for name, project in six.iteritems(content):
        group_id = '%s-group' % name.lower()
        module_groups[group_id]['module_group_name'] = (
            '%s Official' % name.title())
        module_groups[group_id]['tag'] = 'program'

        for d_name, deliverable in six.iteritems(project['deliverables']):
            for repo in deliverable['repos']:
                repo_split = repo.split('/')
                if len(repo_split) < 2:
                    continue  # valid repo must be in form of 'org/module'

                mn = repo_split[1]  # module_name

                module_groups[group_id]['modules'].add(mn)
                all_official['releases'][release_name].add(mn)

                tags = deliverable.get('tags', [])
                for tag in tags:
                    if tag in TAGS:
                        module_groups[tag]['releases'][release_name].add(mn)


def _make_default_module_groups():
    # create default module groups
    module_groups = collections.defaultdict(lambda: {'modules': set()})

    # openstack official
    _make_module_group(module_groups, 'openstack-official')

    # openstack others
    _make_module_group(module_groups, 'openstack-others')

    # tags
    for tag in TAGS:
        _make_module_group(module_groups, tag)

    return module_groups


GOVERNANCE_PROCESSORS = {
    'legacy': read_legacy_programs_yaml,
    'early_big_tent': read_early_big_tent_projects_yaml,
    'big_tent': read_big_tent_projects_yaml,
}


def process_official_list(releases):
    module_groups = _make_default_module_groups()
    releases_with_refs = (r for r in releases if r.get('refs'))

    for release in releases_with_refs:
        ref_governance = release['refs'].get('governance')
        if not ref_governance:
            continue

        gov_type = ref_governance['type']
        gov_source = ref_governance['source']
        release_name = release['release_name'].lower()

        LOG.debug('Process governance content from uri: %s', gov_source)
        content = yaml.safe_load(utils.read_uri(gov_source))

        GOVERNANCE_PROCESSORS[gov_type](module_groups, release_name, content)

    # set ids for module groups
    for group_id, group in six.iteritems(module_groups):
        group['id'] = group_id

    return module_groups
