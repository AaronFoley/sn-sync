import click
import logging
import keyring
import difflib
from requests.exceptions import HTTPError
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
    :param base: The previous contents of the file
    :param local: The local contents of the file
    :param remote: The remote contents of a file
    :param confirm: Whether to confirm overwriting a file
    :param prefer: The side to prefer when overwriting
    """

    results = None
    action = 's'

    if not confirm:
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
        if prefer == 'local':
            results = local
        elif prefer == 'remote':
            results = remote
    elif action == 'm':
        had_conflict, contents = merge3_has_conflict(local, base, remote)
        contents = ''.join(contents)

        if had_conflict:
            return None
            pass  # We should prompt for an editor here, else skip

    elif confirm or action == 's':
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
        for field_name, file, status in record.compare(instance, files=files):
            field = record.get_sn_field(instance, field_name)
            prev_field = record.get_prev_sn_field(instance, field_name)
            # For files that have been modified, we need to either merge or overwrite the file
            if status == ModStatus.LOCAL or status == ModStatus.BOTH:
                contents = resolve_conflict(
                    prev_field['contents'], file.contents(), field['contents'])
                if contents is not None:
                    pass
                    # file.save(contents)
            # Else we can just overwrite the local content
            elif status == ModStatus.REMOTE:
                pass
                # file.save(field['contents'])

        record.save()

    """ Updates local files with contents from Service Now """

    client = setup_client(config, instance)

    for record in cache.get_records(file=file):
        # Update the metadata for a file
        logger.debug("Fetching meta for {}/{}".format(record.rtype, record.key))
        resp = client.get(record.table, query=record.keys, limit=1)
        record.update_meta(instance, resp['records'][0])

        # Check if the file has been updated
        modified_files = record.get_modified(instance, file)

        for status in modified_files:
            logger.debug("{} Modified locally: {} remotely: {}".format(
                status['name'], status['local'], status['remote']))

            # If it has been modified remotely, but not locally update the content
            if not status['local'] and status['remote']:
                pass
            # If it has been modified locally, prompt to overwrite the content
            elif status['local']:
                logger.info("{} has been modified locally".format(status['name']))
                if not confirm or click.confirm("Overwrite local file"):
                    with open(status['local_path'], 'w') as outfile:
                        outfile.write(record.meta[instance]['fields'][status['name']]['contents'])
            # Else, do nothing
            else:
                pass


def get_status(config, cache, instance):

    client = setup_client(config, instance)

    local = []
    remote = []
    both = []

    # Update the cache
    for record in cache.get_records():
        logger.debug("Fetching meta for {}/{}".format(record.rtype, record.key))
        resp = client.get(record.table, query=record.keys, limit=1)
        record.update_meta(instance, resp['records'][0])

        # Get all modified
        modified_files = record.get_modified(instance)

        for status in modified_files:
            if not status['local'] and status['remote']:
                remote.append("{} (by {} at {})".format(
                    status['local_path'],
                    record.meta[instance]['updated_by'],
                    record.meta[instance]['updated_on']))
            elif status['local'] and not status['remote']:
                local.append(status['local_path'])
            elif status['local'] and status['remote']:
                both.append("{} (by {} at {})".format(
                    status['local_path'],
                    record.meta[instance]['updated_by'],
                    record.meta[instance]['updated_on']))

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


def do_diff(config, cache, file, instance):
    client = setup_client(config, instance)

    for record in cache.get_records(file=file):

        logger.debug("Fetching meta for {}/{}".format(record.rtype, record.key))
        resp = client.get(record.table, query=record.keys, limit=1)
        record.update_meta(instance, resp['records'][0])

        field = record.get_file_field(file)

        with open(file, 'rb') as file:
            local = file.read()

        local = local.decode().splitlines(True)
        remote = record.meta[instance]['fields'][field]['contents'].splitlines(True)

        diff = difflib.unified_diff(local, remote, fromfile='local', tofile='remote')

    click.echo_via_pager(''.join(diff))


def do_push(config, cache, instance, files=None):
    """ Pushes changes made to local files up to the service now instance

    :param config: SNConfig instance
    :param cache: SNCache instance
    :param instance: Name of the Service Now Instance
    :param files: List of files to push to Service Now
    :returns: 0 on success, 1 on failure
    """

    # Setup the client for this particular instance
    client = setup_client(config, instance)

    # Get all records that relate to the local files
    for record in cache.get_records(files=files):
        update_meta(client, record, instance)

        from pprint import pprint
        for file, status in record.compare(instance, files=files):
            logger.debug("{}: {}".format(file, status))

    #     for file in record.local_files


    #     # Go through the
    #     for field, lfile in record.local_files:
    #         if not lfile.is_same()











    # for record in cache.get_records()


    # for record in cache.get_records(file=file):
    #     # Update the metadata for a file
    #     logger.debug("Fetching meta for {}/{}".format(record.rtype, record.key))
    #     resp = client.get(record.table, query=record.keys, limit=1)
    #     record.update_meta(instance, resp['records'][0])

    #     # Check if the file has been updated
    #     modified_files = record.get_modified(instance, file)

    #     fields = {}

    #     for status in modified_files:
    #         logger.debug("{} Modified locally: {} remotely: {}".format(
    #             status['name'], status['local'], status['remote']))

    #         # If only local changes, we can push it
    #         if status['local'] and not status['remote']:
    #             fields[status['name']] =
    #         # If only remote changes, prompt for overwrite
    #         elif not status['local'] and status['remote']:
    #             pass
    #         # If Both, must be pulled first
    #         elif not status['local'] and status['remote']:
    #             pass
    #         # If no changes no action

    #     # Push changes for this record




