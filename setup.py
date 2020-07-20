from setuptools import setup, find_packages

setup(
   name='cms50dplus7',
   version='1.0',
   author='Alexander Blum',
   url='https://github.com/timegrid/CMS50Dplus',
   description='python interface for the cms50dplus pulse oximeter v7.0',
   packages=find_packages(),
   install_requires=['python-dateutil', 'pyserial', 'matplotlib']
)
