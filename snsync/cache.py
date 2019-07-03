""" Functions to cache and track service now data locally """
import logging
import os
import json
import hashlib
import copy
from enum import Enum
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ModStatus(Enum):
    NOCHANGE = 0
    LOCAL = 1
    REMOTE = 2
    BOTH = 3


class LocalFile(object):
    """ Represents a local file """

    def __init__(self, path):
        self._path = Path(path)

    @property
    def contents(self):
        return self._path.read_text()

    @property
    def hash(self):
        return hashlib.md5(self._path.read_bytes()).hexdigest()

    @property
    def mtime(self):
        datetime.fromtimestamp(self._path.stat().st_mtime)

    def samefile(self, file_path):
        return self._path.samefile(file_path)

    def stats(self):
        return self._path.stats()

    def save(self, contents):
        pass

    def __str__(self):
        return str(self._path)


class SNRecord(object):
    """ Represents a cached file """

    def __init__(self, cache, record_type, name, meta=None):
        # The parent cache this record belongs to
        self.cache = cache
        # The type of record we are
        self.record_type = record_type
        # The uniquely identifying key of this record
        self.name = name
        # The configuration for this particular record type
        self.config = self.cache.config.get_record_config(record_type)
        # A Map of fields to local files
        self.lfile_field_map = {}
        # Contains the metadata key by Service Now Instances
        self.meta = meta or {}
        # Contains the previous;y known meta data for service now instances
        self.prev_meta = {}
        # File has not been saved if we have not passed in Meta
        self._new = (meta is not None)

    @property
    def table(self):
        return self.config['table']

    @property
    def file(self):
        """ The file this record should be saved too """
        folders = self.name.split(os.sep)
        return os.path.join(self.cache.path, *folders[:-1], folders[-1] + '.json')

    def get_sn_keys(self):
        """ Get the fields and their values to look this record up in Service Now """
        keys = self.config['key'].split('/')
        values = self.name.split(os.sep)
        return dict(zip(keys, values))

    def get_sn_field(self, instance, field):
        """ Get the meta for a field on a particular instance
        :param instance: Instance to check
        :param field: field to check
        """
        try:
            return self.meta[instance]['fields'][field]
        except KeyError:
            return None

    def add_lfile(self, file, file_ext):
        """ Adds a local file to the map
        :param file: path to the local file
        :param file_ext: extension of the local file
        """

        # Get the name of the field for this extension
        field = None
        for name, ext in self.config['fields'].items():
            if ext == file_ext:
                field = name
                break

        self.lfile_field_map[field] = LocalFile(file)

    def is_new(self):
        """ Returns True if this file has never been saved """
        return self._new

    def get_file_field(self, file_path):
        """ Get the field for a particular local file path
        :param file_path: path to a local file
        :returns: The field name
        """
        for field, lfile in self.lfile_field_map.items():
            if lfile.samefile(file_path):
                return field
        return None

    def contains_file(self, file_path):
        """ Checks to see if this record is responsible for a local file
        :param file_path: path to a local file
        :returns: Returns True if file_path is local_files
        """
        return self.get_file_field(file_path) is not None

    def update(self, instance, meta):
        """ Update meta data for a particular instance
        :param instance: Name of the instance to update
        :param meta: Dict containing information on the record in Service Now
        """

        # Copy old meta to prev
        if instance in self.meta:
            self.prev_meta[instance] = copy.deepcopy(self.meta[instance])

        self.meta[instance] = {
            'sys_id': meta['sys_id'],
            'updated_on': meta['sys_updated_on'],
            'updated_by': meta['sys_updated_by'],
            'fields': {}
        }

        for name in self.config['fields'].keys():
            self.meta[instance]['fields'][name] = {
                'hash': hashlib.md5(meta[name].encode()).hexdigest(),
                'contents': meta[name]
            }

    def save(self):
        """ Saves the file to the local cache directory """
        meta_file = Path(self.file)
        # Create any parents that need to exist
        meta_file.parent.mkdir(parents=True, exist_ok=True)

        logger.debug("Saving cache meta file {}".format(meta_file))

        with open(meta_file, 'w') as outfile:
            json.dump(self.meta, outfile)

        self._saved = True

    def compare(self, instance, files=None):
        """ Compare local files with a local instance
        :param instance: Name of the remote Service Now Instance
        :param files: List of files to compare
        :returns: A list of tuples containing field, LocalFile and ModStatus
        """
        # Convert the above files into a list of fields
        check_fields = {}
        if files:
            for file in files:
                field = self.get_file_field(file)
                if field:
                    check_fields[field] = self.lfile_field_map[field]
        # Else check all fields
        else:
            check_fields = self.lfile_field_map

        comparison = []

        for field, lfile in check_fields.items():
            # Get the different hashes
            local_hash = lfile.hash
            remote_hash = self.meta[instance]['fields'][field]['hash']
            try:
                prev_remote_hash = self.prev_meta[instance]['fields'][field]['hash']
            except KeyError:
                prev_remote_hash = None

            # TEMP
            # TODO: Remove
            from pprint import pprint
            pprint(local_hash)
            pprint(remote_hash)
            pprint(prev_remote_hash)

            # There can be 4 different cases when comparing a file:
            # 1. There are no changes local hash
            # 2. There are only remote changes
            # 3. There are only local changes
            # 4. There are remote and local changes

            # Case 1: No Changes
            # Local and Remote hashes line up
            if local_hash == remote_hash:
                comparison.append((field, lfile, ModStatus.NOCHANGE))

            # Case 2: Remote Changes
            # Local and Remote conflict, but the local lines up with our previous hash
            elif local_hash != remote_hash and \
                    (prev_remote_hash is None or local_hash == prev_remote_hash):
                comparison.append((field, lfile, ModStatus.REMOTE))

            # Case 3: Local Changes
            # Local and Remote Conflict, but prev hash and remote hash match
            elif local_hash != remote_hash and remote_hash == prev_remote_hash:
                comparison.append((field, lfile, ModStatus.LOCAL))

            # Case 4: Local and Remote Changes
            # No hashes match
            elif local_hash != remote_hash != prev_remote_hash:
                comparison.append((field, lfile, ModStatus.BOTH))

        return comparison


class SNCache(object):

    def __init__(self, config):
        # The global configuration
        self.config = config
        # Records grouped by type
        self.records = {}

    @property
    def root(self):
        return self.config.root_dir

    @property
    def path(self):
        return os.path.join(self.root, '.sncache')

    @property
    def record_types(self):
        return self.config.records.keys()

    def scan(self, record_types=None):
        """ Performs a scan optionally limited to a set of record types
        :param record_types: List of record types to scan
        """

        if record_types is None:
            record_types = self.record_types

        for rtype in record_types:
            path = Path(os.path.join(self.root, rtype))
            rconfig = self.config.get_record_config(rtype)

            if rtype not in self.records:
                self.records[rtype] = {}

            for file in path.rglob('*'):
                if file.is_dir():
                    continue
                self.scan_file(path, rconfig, rtype, file)

    def scan_file(self, path, rconfig, record_type, file):
        """ Scan a single file
        :param config: configuration for the record type
        :param file_path: Path to the file
        """

        # Workout the key and field this file relates to
        rel = file.relative_to(path)
        key, ext = os.path.splitext(str(rel))

        # Ensure that the file path corresponds to the key in the config
        if len(key.split(os.sep)) != len(rconfig['key'].split('/')):
            logger.warn('File location does not match key file: {} key: {}'.format(
                    key, rconfig['key']))
            return

        # Check that the extension is correct
        if ext in rconfig['fields'].values():
            logger.debug("Found {}".format(file))
            record = self.load_record(record_type, key)
            record.add_lfile(str(file), ext)
        else:
            logger.warn("Unknown suffix for file: {} extension: {} expected: {}".format(
                    file, ext, ','.join(rconfig['fields'].values())))
            return

    def load_record(self, record_type, key):
        """ Load a record for the in-memory list or from the file system
        :param record_type: Type of record to load
        :param key: Key of the record
        :returns: A SNRecord instance
        """

        # Look in memory first
        if record_type in self.records and key in self.records[record_type]:
            return self.records[record_type][key]

        # Try and load meta from disk from the disk
        try:
            folders = key.split(os.sep)
            meta_file = os.path.join(self.path, record_type, *folders[:-1], folders[-1] + '.json')
            logger.debug("Looking for file {}".format(meta_file))
            with open(meta_file, 'r') as f:
                meta = json.load(f)
                logger.debug("Existing SNRecord loaded from disk")
        except FileNotFoundError:
            logger.debug("Existing SNRecord not found")
            meta = None

        record = SNRecord(self, record_type, key, meta)
        self.records[record_type][key] = record
        return record

    def get_records(self, files=None):
        """ Gets all records within this cache

        :param files: Optionally specify a list of local files to filter records by
        :returns: A list of SNRecord objects within this cache
        """
        records = []
        # Loop through each record type
        for rtype, values in self.records.items():
            for key, record in values.items():
                if not files or any(record.contains_file(file) for file in files):
                    records.append(record)
        return records
