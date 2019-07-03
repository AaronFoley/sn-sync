from distutils.core import setup
from snsync import __version__


setup(
    name='sn-sync',
    version=__version__,
    description='Syncs files between local computer and Service Now',
    author='Aaron Foley',
    author_email='me@aaronfoley.net',
    packages=['snsync'],
)
