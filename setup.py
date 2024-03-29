import fastentrypoints
from setuptools import setup, find_packages

setup(
    name="arc",
    version="0.1",
    author="FID-Judaica, Goethe Universitätsbibliothek",
    license="MLP 2.0/EUPL 1.1",
    author_email="a.christianson@ub.uni-frankfurt.de",
    # url='https://github.com/FID-Judaica/-parse.py',
    description="transliteration to Hebrew translator",
    long_description=open("README.rst").read(),
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "fl=arc.filters:main",
            "derom=arc.util:main",
            "dump-arc-config=arc.config:dump_config_file",
        ]
    },
    install_requires=[
        "pica_parse @ git+https://github.com/FID-Judaica/pica_parse.py.git",
        "filtermaker @ git+https://github.com/FID-Judaica/filtermaker.git",
        "deromanize @ git+https://github.com/ubffm/deromanize.git",
        "PyYaml",
        "sqlalchemy",
        "libaaron @ git+https://github.com/ninjaaron/libaaron.git@master",
        "listdict @ git+https://github.com/ubffm/listdict.git",
        "requests",
        "tornado",
        "python-Levenshtein",
        "python-hebrew-numbers @ git+https://github.com/OriHoch/python-hebrew-numbers.git",
    ],
)
