import os
from setuptools import find_packages, setup

setup(
    name='app',
    version='1.0',
    package_dir={'': 'src'},
    packages=find_packages('src'),
    include_package_data=True,
    entry_points={
        'console_scripts': ['cli=apporder.cli:cli'],
    },
    scripts=['bin/pycheck', 'bin/profile'],
    classifiers=[
        'Environment :: Console',
        'Development Status :: 2',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.7',
    ],
)
