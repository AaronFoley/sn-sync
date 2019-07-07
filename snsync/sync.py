import click
import logging
import keyring
import difflib
import time
from pathlib import Path
from requests.exceptions import HTTPError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from snsync.exceptions import LoginFailed
from snsync.cache import ModStatus
from snsync.snow import SNClient
from snsync.merge import merge3_has_conflict

logger = logging.getLogger(__name__)


def prompt_for_auth_details(instance):
    """ Prompt or fetch authentication details
    :param instance: Name of the instance to get credentials for
    """

    # Check keyring
    logger.debug("Checking keyring for credential for instance: {}".format(instance))

    username = keyring.get_password('sn-sync-{}'.format(instance), 'username')
    password = keyring.get_password('sn-sync-{}'.format(instance), 'password')

    if username is None:
        username = click.prompt('{} username'.format(instance))

        # Now try and set it in the keyring
        keyring.set_password('sn-sync-{}'.format(instance), 'username', username)

    if password is None:
        password = click.prompt('{} password'.format(instance), hide_input=True)

        # Now try and set it in the keyring
        keyring.set_password('sn-sync-{}'.format(instance), 'password', password)

    return username, password


def clear_keyring(instance):
    """ Clear credentials stored in keyring for an instance
    :param instance: Instance to clear credentials for
    """
    logger.debug("Clearing existing credentials for sn-sync-{}".format(instance))
    keyring.delete_password('sn-sync-{}'.format(instance), 'username')
    keyring.delete_password('sn-sync-{}'.format(instance), 'password')


def setup_client(config, instance):
    """ Sets up and tests a Service Now Client
    :param config: SNConfig object
    :param instance: Instance to setup client for
    """

    client = None
    inst_config = config.instances[instance]

    # 3 attempts
    for x in range(3):
        username, password = prompt_for_auth_details(instance)
        client = SNClient(inst_config['host'],
                          username=username,
                          password=password,
                          verify=inst_config['verify_ssl'],
                          read_only=inst_config['read_only'])
        try:
            # Attempt a simple get to confirm that authentication is working
            client.get('invalid_table')
            return client
        except HTTPError as err:
            if err.response is not None and err.response.status_code == 401:
                logger.error("Username/Password is incorrect")
                clear_keyring(instance)

    raise LoginFailed("Unable to login to instance: {}".format(instance))


def update_meta(client, record, instance):
    """ Fetch and update meta for a SNRecord on a particular instance

    :param client: The SNClient to use
    :param record: SNRecord to update meta for
    :param instance: Name of the Service Now Instance
    """
    logger.debug("Fetching meta for {}/{}".format(record.record_type, record.name))
    resp = client.get(record.table, query=record.get_sn_keys(), limit=1)
    record.update(instance, resp['records'][0])


def resolve_conflict(base, local, remote, confirm=True, prefer='local'):
    """ Attempt to resolve a conflict between local and remote files
    :param base: A string containing the previous contents of the file
    :param local: A string containing the local contents of the file
    :param remote: A string containing the remote contents of a file
    :param confirm: Whether to confirm overwriting a file
    :param prefer: The side to prefer when overwriting
    """

    results = None
    action = 's'

    if confirm:
        action = click.prompt(
            'Overwrite/Merge/Skip',
            type=click.Choice(['o', 'overwrite', 'm', 'merge', 's', 'skip'], case_sensitive=False),
            show_choices=False,
            show_default=False,
            prompt_suffix=' [o/m/S]: ',
            default='s'
        )
        action = action[0]
    if action == 'o':
        logger.debug("Overwriting with {} copy".format(prefer))
        if prefer == 'local':
            results = local
        elif prefer == 'remote':
            results = remote
    elif action == 'm':
        had_conflict, contents = merge3_has_conflict(
            local.splitlines(True), base.splitlines(True), remote.splitlines(True))
        contents = ''.join(contents)

        if had_conflict:
            logger.debug("File has a conflict")
            contents = click.edit(text=contents, require_save=True)

        return contents

    elif not confirm or action == 's':
        return None

    return results


def do_pull(config, cache, instance, files=None, confirm=True):
    """ Pull down update from Service Now, updating local files
    :param config: SNConfig object
    :param cache: SNCache Object
    :param instance: Instance to pull from
    :param files: List of local files to pull
    :param confirm: Require confirmation before overwriting local files
    """
    client = setup_client(config, instance)
    for record in cache.get_records(files=files):
        update_meta(client, record, instance)
        # Compare any files that match the files passed in
        for name, field, file, status in record.compare(instance, files=files):
            # If the file has not been modified, we can continue
            if status == ModStatus.NOCHANGE:
                logger.debug("File not modified - not saving")
                continue
            # For files that have been modified, we need to either merge or overwrite the file
            if status == ModStatus.LOCAL or status == ModStatus.BOTH:
                contents = resolve_conflict(
                    field['prev_contents'], file.contents, field['contents'], prefer='remote')
                # If this file was skipped or something went wrong
                if contents is None:
                    logger.warn("Skipping file: {}".format(file))
                    continue
            # Else we can just overwrite the local content
            elif status == ModStatus.REMOTE:
                logger.debug("File modified remotely - updating")
                contents = field['contents']

            # Now save the file
            file.save(contents)
            record.update_field_meta(instance, name)

        record.save()


def get_status(config, cache, instance):
    """ Print differences between local files and remote files
    :param config: SNConfig object
    :param cache: SNCache Object
    :param instance: Instance to compare
    """

    client = setup_client(config, instance)

    local = []
    remote = []
    both = []

    for record in cache.get_records():
        update_meta(client, record, instance)
        # Compare any files that match the files passed in
        for name, field, file, status in record.compare(instance):
            if status == ModStatus.NOCHANGE:
                continue
            elif status == ModStatus.LOCAL:
                local.append(file.relative_path)
            elif status == ModStatus.REMOTE:
                remote.append("{} (by {} at {})".format(
                    file.relative_path,
                    record.meta[instance]['updated_by'],
                    record.meta[instance]['updated_on']
                ))
            elif status == ModStatus.BOTH:
                both.append("{} (by {} at {})".format(
                    file.relative_path,
                    record.meta[instance]['updated_by'],
                    record.meta[instance]['updated_on']
                ))

    # Display the results
    if local or remote or both:
        click.echo("Checking instance {}".format(instance))
        click.echo("")
        if both:
            click.echo("Both:")
            for file in both:
                click.echo("\t{}".format(file))
            click.echo("")
        if remote:
            click.echo("Remote:")
            for file in remote:
                click.echo("\t{}".format(file))
            click.echo("")
        if local:
            click.echo("Local:")
            for file in local:
                click.echo("\t{}".format(file))
    else:
        click.echo("No files modified")


def do_diff(config, cache, instance, files=None):
    """ Show diffs between local and remote files
    :param config: SNConfig object
    :param cache: SNCache Object
    :param instance: Instance to compare
    :param files: List of local files to compare
    """
    client = setup_client(config, instance)

    diffs = []

    for record in cache.get_records(files=files):
        update_meta(client, record, instance)
        for name, file in record.get_files(files=files):
            field = record.meta[instance]['fields'][name]
            diff = difflib.unified_diff(
                field['contents'].splitlines(True),
                file.contents.splitlines(True),
                fromfile='remote',
                tofile='local'
            )
            diff = ''.join(diff)
            if diff:
                diffs.append('{}:\n{}\n'.format(file.relative_path, diff))

    # Display the results
    if diffs:
        click.echo_via_pager(''.join(diffs))
    else:
        click.echo("No files modified")


def do_push(config, cache, instance, files=None):
    """ Pushes changes made to local files up to the service now instance

    :param config: SNConfig instance
    :param cache: SNCache instance
    :param instance: Name of the Service Now Instance
    :param files: List of files to push to Service Now
    :returns: 0 on success, 1 on failure
    """
    client = setup_client(config, instance)

    for record in cache.get_records(files=files):
        update_meta(client, record, instance)
        for name, field, file, status in record.compare(instance, files=files):
            # If the file has not been modified, we can continue
            if status == ModStatus.NOCHANGE:
                logger.debug("File not modified - not saving")
                continue
            # For files that have been modified, we need to either merge or overwrite the file
            if status == ModStatus.REMOTE or status == ModStatus.BOTH:
                contents = resolve_conflict(
                    field['prev_contents'], file.contents, field['contents'], prefer='local')
                # If this file was skipped or something went wrong
                if contents is None:
                    logger.warn("Skipping file: {}".format(file))
                    continue
            # Else we can just overwrite the remote content
            elif status == ModStatus.LOCAL:
                logger.debug("File modified locally - updating")
                contents = file.contents

            # Now save the file
            file.save(contents)
            resp = client.update(record.table, record.get_sys_id(instance), {
                name: contents
            })
            update_meta(client, record, instance)
            record.update_field_meta(instance, name)

        record.save()


class SNSyncHandler(FileSystemEventHandler):
    """ Watches the filesystem for changes to be sent up to service now """

    def __init__(self, config, cache, instance, client):
        self._config = config
        self._cache = cache
        self._instance = instance
        self._client = client

    def dispatch(self, event):
        if event.is_directory:
            return
        super().dispatch(event)

    def on_modified(self, event):
        """ Triggered when a file is modified """
        for record in self._cache.get_records(files=[event.src_path]):
            update_meta(self._client, record, self._instance)
            for name, field, file, status in record.compare(self._instance, files=[event.src_path]):
                if status == ModStatus.NOCHANGE:
                    logger.debug("File not modified - not saving")
                    continue
                # For files that have been modified, we need to either merge or overwrite the file
                if status == ModStatus.REMOTE or status == ModStatus.BOTH:
                    contents = resolve_conflict(
                        field['prev_contents'], file.contents, field['contents'], prefer='local')
                    # If this file was skipped or something went wrong
                    if contents is None:
                        logger.warn("Skipping file: {}".format(file))
                        continue
                # Else we can just overwrite the remote content
                elif status == ModStatus.LOCAL:
                    logger.debug("File modified locally - updating")
                    contents = file.contents

                # Now save the file
                file.save(contents)
                resp = self._client.update(record.table, record.get_sys_id(self._instance), {
                    name: contents
                })
                update_meta(self._client, record, self._instance)
                record.update_field_meta(self._instance, name)

            record.save()


def do_watch(config, cache, instance):
    """ Watch the local folders """
    client = setup_client(config, instance)

    # Update all records
    for record in cache.get_records():
        update_meta(client, record, instance)

    event_handler = SNSyncHandler(config, cache, instance, client)
    observer = Observer()

    watching = False

    for record_type in config.records.keys():
        path = Path('.', record_type)
        if path.is_dir():
            watching = True
            logger.debug("Watching {}".format(path))
            observer.schedule(event_handler, path=str(path), recursive=True)

    if not watching:
        logger.error("No directories found to watch")
        return 1

    observer.start()

    try:
        while True:
          time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()