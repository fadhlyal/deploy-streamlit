#!/usr/bin/env python

from Cython.Build import cythonize
from setuptools import setup
from setuptools.extension import Extension

import os

project_root = os.path.dirname(__file__)
project_dir = os.path.abspath(os.path.join(project_root, "lpsolve"))

extensions = Extension(
      'clara.pylpsolve',
      ['clara/pylpsolve.pyx'],
      libraries=['lpsolve55'],
      
      library_dirs=[r'https://github.com/fadhlyal/deploy-streamlit/tree/main/lpsolve'],
      include_dirs=[r'https://github.com/fadhlyal/deploy-streamlit/tree/main/lpsolve'],
      define_macros=[
            ('WIN32', None),
            ('NOMINMAX', None),
            ('_USRDLL', None),
            ('_MBCS', None),
            ('_CRT_SECURE_NO_WARNINGS', None),
            ('YY_NO_UNISTD_H', None),
            ('_WINDLL', None),
            ('_hypot', 'hypot'),  # This prevents the macro redefinition
      ]
)

setup(name='clara',
      version='1.0',
      description='CLuster And RepAir tool for introductory programming assignments',
      author='Ivan Radicek',
      author_email='radicek@forsyte.at',
      url='https://github.com/iradicek/clara',
      packages=['clara'],
      package_data={
            'clara': ['lpsolve55.dll'],
      },
      ext_modules = cythonize(extensions),
      install_requires=['pycparser', 'zss'],
      scripts=['bin/clara'],
      entry_points={
          'console_scripts': [
              'clara=clara.cli:main',
            ],
      },
)
