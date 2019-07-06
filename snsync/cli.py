import click
import logging
import sys
from snsync import __version__
from snsync.exceptions import ConfigurationFileNotFound, InvalidConfiguration, InstanceNotFound
from snsync.logging import configure_logger
from snsync.config import SNConfig
from snsync.cache import SNCache

logger = logging.getLogger(__name__)


class SNContext(object):
    def __init__(self):
        self.config = None
        self.cache = None


pass_sn_context = click.make_pass_decorator(SNContext, ensure=True)


def instance_option(*param_decls, **attrs):
    """ Specify the instance to talk to for a command else use the default """

    def decorator(f):
        def callback(ctx, param, value):
            # Get the SN Context object
            snctx = ctx.find_object(SNContext)
            if snctx is None:
                raise RuntimeError('Unable to find SNContext')

            if value is None:
                return snctx.config.default_instance

            # Ensure that the instance name passed is in the configuration
            if not value in snctx.config.instances:
                raise InstanceNotFound("Unable to find instance {} in configuration".format(value))
            return value

        attrs.setdefault('callback', callback)
        attrs.setdefault('help', 'The Service Now Instances to interact with as it appears in config')
        return click.option(*(param_decls or ('--instance','-i',)), **attrs)(f)

    return decorator


@click.group()
@click.version_option(__version__)
@click.option(
    '--verbosity', '-v',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'], case_sensitive=False),
    is_eager=True,
    default='INFO'
)
@pass_sn_context
def main(ctx, verbosity):
    # Configure logging
    configure_logger(verbosity)

    # Load Configuration
    try:
        ctx.config = SNConfig()
    except (ConfigurationFileNotFound, InvalidConfiguration) as e:
        logger.critical(e)
        sys.exit(1)

    # Setup the cache
    ctx.cache = SNCache(ctx.config)
    ctx.cache.scan()


@main.command('pull', short_help='Updates local files to match what is in Service Now')
@click.argument('files', type=click.Path(exists=True), required=False, nargs=-1)
@instance_option()
@pass_sn_context
def pull(ctx, files, instance):
    from snsync.sync import do_pull
    retval = do_pull(ctx.config, ctx.cache, instance, files)

    if retval:
        sys.exit(retval)


@main.command('status', short_help='Shows changes in local repo')
@click.argument('instance', required=False)
@pass_sn_context
def status(ctx, instance):

    instance = instance or ctx.config.default_instance

    from snsync.sync import get_status
    retval = get_status(ctx.config, ctx.cache, instance)

    if retval:
        sys.exit(retval)


@main.command('push', short_help='Push local changes to Service Now',
    context_settings=dict(ignore_unknown_options=True,)
)
@click.argument('files', type=click.Path(exists=True), required=False, nargs=-1)
@instance_option()
@pass_sn_context
def push(ctx, files, instance):
    from snsync.sync import do_push
    retval = do_push(ctx.config, ctx.cache, instance, files)

    if retval:
        sys.exit(retval)


@main.command('diff', short_help='Shows difference between local file and Service Now')
@click.argument('files', type=click.Path(exists=True), required=False, nargs=-1)
@instance_option()
@pass_sn_context
def diff(ctx, files, instance):
    instance = instance or ctx.config.default_instance

    from snsync.sync import do_diff
    retval = do_diff(ctx.config, ctx.cache, instance, files)

    if retval:
        sys.exit(retval)


@main.command('sync', short_help='Watches for changes and syncs them with Service Now')
@pass_sn_context
def sync(ctx):
    click.echo("Hello World!")
