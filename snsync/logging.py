import logging
import click


class ClickHandler(logging.Handler):

    def emit(self, record):
        try:
            msg = self.format(record)
            click.echo(msg)
        except Exception:
            self.handleError(record)


class ColourFormatter(logging.Formatter):
    """ Defines a custom logger that sets a default colour """

    COLOURS = {
        'ERROR': dict(fg='red'),
        'EXCEPTION': dict(fg='red'),
        'CRITICAL': dict(fg='red'),
        'DEBUG': dict(fg='blue'),
        'WARNING': dict(fg='yellow')
    }

    def format(self, record):
        if not record.exc_info:
            msg = record.getMessage()
            level = record.levelname
            if level in self.COLOURS:
                return click.style('{}: {}'.format(level.title(), msg), **self.COLOURS[level])
            return msg
        return logging.Formatter.format(self, record)


def configure_logger(log_level):

    logger = logging.getLogger('snsync')
    logger.setLevel(logging.DEBUG)

    log_level = log_level.upper()

    # Remove all attached handlers, in case there was
    # a logger with using the name 'snsync'
    del logger.handlers[:]

    handler = ClickHandler()
    handler.formatter = ColourFormatter()
    handler.setLevel(log_level)

    logger.addHandler(handler)
