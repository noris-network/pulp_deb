from gettext import gettext as _
import hashlib
import logging
import os
import shutil

from debian import debian_support

import urlparse
from nectar.request import DownloadRequest
from pulp.plugins.util import misc
from pulp.plugins.util.publish_step import PluginStep, GetLocalUnitsStep, DownloadStep
from pulp.server.exceptions import PulpCodedValidationException
from pulp_deb.common import constants
from pulp_deb.plugins import error_codes

_logger = logging.getLogger(__name__)


class SyncStep(PluginStep):
    def __init__(self, **kwargs):
        """
        :param repo:        repository to sync
        :type  repo:        pulp.plugins.model.Repository
        :param conduit:     sync conduit to use
        :type  conduit:     pulp.plugins.conduits.repo_sync.RepoSyncConduit
        :param config:      config object for the sync
        :type  config:      pulp.plugins.config.PluginCallConfiguration
        :param working_dir: full path to the directory in which transient files
                            should be stored before being moved into long-term
                            storage. This should be deleted by the caller after
                            step processing is complete.
        :type  working_dir: basestring
        """
        super(SyncStep, self).__init__(constants.IMPORT_STEP_MAIN,
                                       plugin_type=constants.WEB_IMPORTER_TYPE_ID, **kwargs)
        self.description = _('Syncing Repository')

        # Unit keys, populated by GetMetadataStep
        self.available_units = []

        # config = self.get_config()
        working_dir = self.get_working_dir()
        self.deb_data = {}
        # repo = self.get_repo()

        # create a Repository object to interact with
        self.add_child(GetMetadataStep())
        self.step_get_local_units = GetLocalUnitsStepDeb(working_dir)
        self.add_child(self.step_get_local_units)
        self.add_child(
            DownloadStep(constants.SYNC_STEP_DOWNLOAD, downloads=self.generate_download_requests(),
                         repo=kwargs["repo"], config=kwargs["config"],
                         working_dir=kwargs["working_dir"],
                         description=_('Downloading remote files')))
        self.add_child(SaveUnits(working_dir))

    def generate_download_requests(self):
        """
        generator that yields DownloadRequests for needed units.

        :return:    generator of DownloadRequest instances
        :rtype:     collections.Iterable[DownloadRequest]
        """
        feed_url = self.get_config().get('feed')
        for unit_key in self.step_get_local_units.units_to_download:
            key_hash = get_key_hash(unit_key)
            # Don't save all the units in one directory as there could be 50k + units
            hash_dir = generate_internal_storage_path(self.deb_data[key_hash]['file_name'])
            # make sure the download directory exists
            dest_dir = os.path.join(self.working_dir, hash_dir)
            download_dir = os.path.dirname(dest_dir)
            misc.mkdir(download_dir)
            file_path = self.deb_data[key_hash]['file_path']
            packages_url = urlparse.urljoin(feed_url, file_path)
            yield DownloadRequest(packages_url, dest_dir)


class GetMetadataStep(PluginStep):
    def __init__(self, **kwargs):
        """
        :param repo:        repository to sync
        :type  repo:        pulp.plugins.model.Repository
        :param conduit:     sync conduit to use
        :type  conduit:     pulp.plugins.conduits.repo_sync.RepoSyncConduit
        :param config:      config object for the sync
        :type  config:      pulp.plugins.config.PluginCallConfiguration
        :param working_dir: full path to the directory in which transient files
                            should be stored before being moved into long-term
                            storage. This should be deleted by the caller after
                            step processing is complete.
        :type  working_dir: basestring
        """
        super(GetMetadataStep, self).__init__(constants.IMPORT_STEP_METADATA,
                                              plugin_type=constants.WEB_IMPORTER_TYPE_ID,
                                              **kwargs)
        self.description = _('Retrieving metadata')

    def process_main(self):
        """
        determine what images are available upstream, get the upstream tags, and
        save a list of available unit keys on the parent step
        """
        super(GetMetadataStep, self).process_main()
        _logger.debug(self.description)
        packages_url = self.get_config().get('feed')
        packages_path = self.get_config().get('package-file-path')
        if not packages_url.endswith('/'):
            packages_url += '/'
        if packages_path:
            if packages_path.startswith('/'):
                packages_path = packages_path[1:]
            packages_url = urlparse.urljoin(packages_url, packages_path)
        packpath = os.path.join(self.get_working_dir(), "Packages")
        debian_support.download_file(packages_url + "Packages", packpath)
        for package in debian_support.PackageFile(packpath):
            package_data = dict(package)
            metadata = get_metadata(package_data)
            unit_key_hash = get_key_hash(metadata)
            self.parent.deb_data[unit_key_hash] = {
                'file_name': os.path.basename(package_data['Filename']),
                'file_path': package_data['Filename'],
                'file_size': package_data['Size']
            }
            self.parent.available_units.append(metadata)


class GetLocalUnitsStepDeb(GetLocalUnitsStep):

    def __init__(self, working_dir):
        super(GetLocalUnitsStepDeb, self).__init__(constants.WEB_IMPORTER_TYPE_ID,
                                                   constants.DEB_TYPE_ID, constants.UNIT_KEY_FIELDS,
                                                   working_dir)

    def _dict_to_unit(self, unit_dict):
        unit_key_hash = get_key_hash(unit_dict)
        file_name = self.parent.deb_data[unit_key_hash]['file_name']
        storage_path = generate_internal_storage_path(file_name)
        unit_dict.pop('_id')
        return_unit = self.get_conduit().init_unit(
            constants.DEB_TYPE_ID, unit_dict,
            {'file_name': file_name},
            storage_path)
        return return_unit


class SaveUnits(PluginStep):
    def __init__(self, working_dir):
        super(SaveUnits, self).__init__(step_type=constants.SYNC_STEP_SAVE,
                                        plugin_type=constants.WEB_IMPORTER_TYPE_ID,
                                        working_dir=working_dir)
        self.description = _('Saving packages')

    def process_main(self):
        _logger.debug(self.description)
        for unit_key in self.parent.step_get_local_units.units_to_download:
            hash_key = get_key_hash(unit_key)
            file_name = self.parent.deb_data[hash_key]['file_name']
            storage_path = generate_internal_storage_path(file_name)
            dest_dir = os.path.join(self.working_dir, storage_path)
            # validate the size of the file downloaded
            file_size = int(self.parent.deb_data[hash_key]['file_size'])
            if file_size != os.stat(dest_dir).st_size:
                raise PulpCodedValidationException(error_code=error_codes.DEB1001,
                                                   file_name=file_name)

            unit = self.get_conduit().init_unit(constants.DEB_TYPE_ID, unit_key,
                                                {'file_name': file_name},
                                                storage_path)
            shutil.move(dest_dir, unit.storage_path)
            self.get_conduit().save_unit(unit)


def get_key_hash(metadata):
    unit_key_hash = '::'.join([metadata['name'],
                               metadata['version'],
                               metadata['architecture']])
    return unit_key_hash


def generate_internal_storage_path(file_name):
    """
    Generate the internal storage directory for a given deb filename

    :param file_name: base filename of the unit
    :type file_name: str

    :returns str: The relative path for storing the unit
    """
    hasher = hashlib.md5()
    hasher.update(file_name)
    hash_digest = hasher.hexdigest()
    part1 = hash_digest[0:1]
    part2 = hash_digest[2:4]
    part3 = hash_digest[5:]
    storage_path = os.path.join(part1, part2, part3, file_name)
    return storage_path


def get_metadata(package):
    """
    converts an dictionary representing a package to a unit key dictionary
    :param package: dictionary parsed by debian_support
    :type  package: dict
    :return:        unit key
    :rtype          dict
    """
    unit_key = {"name": package["Package"], "version": package["Version"],
                "architecture": package["Architecture"], "md5sum": package["MD5sum"]}
    return unit_key
