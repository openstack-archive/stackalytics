from stackalytics.processor import user_utils

MEMORY_STORAGE_CACHED = 0


class MemoryStorage(object):
    def __init__(self, records):
        pass


class CachedMemoryStorage(MemoryStorage):
    def __init__(self, records):
        super(CachedMemoryStorage, self).__init__(records)

        self.records = {}
        self.company_index = {}
        self.date_index = {}
        self.module_index = {}
        self.launchpad_id_index = {}
        self.release_index = {}
        self.dates = []
        for record in records:
            self.records[record['record_id']] = record
            self.index(record)
        self.dates = sorted(self.date_index)
        self.company_name_mapping = dict((c.lower(), c)
                                         for c in self.company_index.keys())

    def index(self, record):

        self._add_to_index(self.company_index, record, 'company_name')
        self._add_to_index(self.module_index, record, 'module')
        self._add_to_index(self.launchpad_id_index, record, 'launchpad_id')
        self._add_to_index(self.release_index, record, 'release')
        self._add_to_index(self.date_index, record, 'date')

        record['week'] = user_utils.timestamp_to_week(record['date'])
        record['loc'] = record['lines_added'] + record['lines_deleted']

    def _add_to_index(self, record_index, record, key):
        record_key = record[key]
        if record_key in record_index:
            record_index[record_key].add(record['record_id'])
        else:
            record_index[record_key] = set([record['record_id']])

    def _get_record_ids_from_index(self, items, index):
        record_ids = set()
        for item in items:
            if item not in index:
                raise Exception('Parameter %s not valid' % item)
            record_ids |= index[item]
        return record_ids

    def get_record_ids_by_modules(self, modules):
        return self._get_record_ids_from_index(modules, self.module_index)

    def get_record_ids_by_companies(self, companies):
        return self._get_record_ids_from_index(
            map(self._get_company_name, companies),
            self.company_index)

    def get_record_ids_by_launchpad_ids(self, launchpad_ids):
        return self._get_record_ids_from_index(launchpad_ids,
                                               self.launchpad_id_index)

    def get_record_ids_by_releases(self, releases):
        return self._get_record_ids_from_index(releases, self.release_index)

    def get_record_ids(self):
        return set(self.records.keys())

    def get_records(self, record_ids):
        for i in record_ids:
            yield self.records[i]

    def _get_company_name(self, company_name):
        normalized = company_name.lower()
        if normalized not in self.company_name_mapping:
            raise Exception('Unknown company name %s' % company_name)
        return self.company_name_mapping[normalized]

    def get_companies(self):
        return self.company_index.keys()

    def get_modules(self):
        return self.module_index.keys()

    def get_launchpad_ids(self):
        return self.launchpad_id_index.keys()


class MemoryStorageFactory(object):

    @staticmethod
    def get_storage(memory_storage_type, records):
        if memory_storage_type == MEMORY_STORAGE_CACHED:
            return CachedMemoryStorage(records)
        else:
            raise Exception('Unknown memory storage type')
