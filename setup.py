# Kubetools Client
# File: setup.py
# Desc: python wants

import re

from setuptools import find_packages, setup


# Regex matching pattern followed by 3 numerical values separated by '.'
pattern = re.compile(r'[0-9]+\.[0-9]+\.?[0-9]*\.?[a-z0-9]*')


def get_version():
    with open('CHANGELOG.md', 'r') as fn:
        while True:
            version = pattern.findall(fn.readline())
            if len(version) > 0:
                return ''.join(version[0])


if __name__ == '__main__':
    setup(
        version=get_version(),
        name='kubetools',
        description='Client library for Kubetools',
        author='Devs @ EDITED',
        author_email='nick@edited.com',
        url='http://github.com/EDITD/kubetools-client',
        packages=find_packages(),
        entry_points={
            'console_scripts': (
                # kubetools client commands
                'kubetools-server=kubetools_client.cli.__main__:main',
                'kubetools=kubetools_client.cli.__main__:main',  # backwards compat
                # ktd dev commands
                'ktd=kubetools_client.dev.__main__:main',
            ),
        },
        install_requires=(
            'click>=7',
            'docker>=3.7,<4.0',
            'pyyaml>=3,<4.3',
            'pydash',
            'pyretry',
            'requests>2.18,<2.21',
            'six',
            'setuptools',
        ),
        extras_require={
            'dev': (
                'ipdb',
            ),
        },
    )
