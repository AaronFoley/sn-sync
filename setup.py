from distutils.core import setup
from snsync import __version__

install_requires = [
    'requests>=2.22',
    'merge3==0.0.2',
    'click>=7.0',
    'keyring>=19.0.2'
]

with open('README.md') as fh:
    long_description = fh.read()

setup(
    name='sn-sync',
    version=__version__,
    description='Syncs files between local computer and Service Now',
    long_description=long_description,
    author='Aaron Foley',
    author_email='me@aaronfoley.net',
    packages=['snsync'],
    install_requires=install_requires,
    url='https://github.com/AaronFoley/sn-sync',
    download_url='https://github.com/AaronFoley/sn-sync',
    license='MCS DevOps',
)
