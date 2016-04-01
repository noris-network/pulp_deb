from setuptools import setup, find_packages

setup(
    name='pulp_deb_plugins',
    version='1.1.0a1',
    packages=find_packages(),
    url='http://www.pulpproject.org',
    license='GPLv2+',
    author='Pulp Team',
    author_email='pulp-list@redhat.com',
    description='plugins for deb support in pulp',
    entry_points={
        'pulp.importers': [
            'importer = pulp_deb.plugins.importers.web:entry_point',
        ],
        'pulp.distributors': [
            'distributor = pulp_deb.plugins.distributors.web:entry_point'
        ],
        'pulp.unit_models': [
            'deb = pulp_deb.plugins.db.models:DEB'
        ]
    }
)
