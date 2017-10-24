import fastentrypoints
from setuptools import setup

setup(
    name='arc',
    version='0.0',
    author='FID-Judaica, Goethe Universitätsbibliothek',
    license='MLP 2.0/EUPL 1.1',
    author_email='a.christianson@ub.uni-frankfurt.de',
    # url='https://github.com/FID-Judaica/-parse.py',
    description='transliteration to Hebrew translator',
    long_description=open('README.rst').read(),
    packages=['arc'],
    entry_points={'console_scripts': [
        'fl=arc.filters:main',
        'derom=arc.util:main']},
    install_requires=[
        'pica_parse',
        'filtermaker',
        'deromanize',
        'PyYaml',],
)
