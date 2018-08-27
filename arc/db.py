# Copyright 2017, Goethe University
#
# This library is free software; you can redistribute it and/or
# modify it either under the terms of:
#
#   the EUPL, Version 1.1 or – as soon they will be approved by the
#   European Commission - subsequent versions of the EUPL (the
#   "Licence"). You may obtain a copy of the Licence at:
#   https://joinup.ec.europa.eu/software/page/eupl
#
# or
#
#   the terms of the Mozilla Public License, v. 2.0. If a copy of the
#   MPL was not distributed with this file, You can obtain one at
#   http://mozilla.org/MPL/2.0/.
#
# If you do not alter this notice, a recipient may use your version of
# this file under either the MPL or the EUPL.
import re
import pica_parse.db
import sqlalchemy as sa
breaks = re.compile(r'[\s־]+')
nocheck = {'־', 'ה', '-', '։', ';'}

SQLite_VIEWS = '''\
CREATE VIEW If NOT EXISTS `audit` AS
    SELECT c.ppn, records.content, c.suggested, c.corrected
    FROM changes AS c
    JOIN records ON c.ppn = records.ppn AND records.field = '021A';
CREATE VIEW IF NOT EXISTS `word_totals` AS
    select cast(sum(errors) as float) as errors,
           cast(sum(words) as float) as words
           from checked;
CREATE VIEW IF NOT EXISTS `word_percision` AS
    select 1 - errors/words from word_totals;
CREATE VIEW IF NOT EXISTS `title_totals` AS
    select cast((select count(ppn) from checked)
                as float) as titles,
           cast((select count(ppn) from checked where errors = 0)
                as float) as clean;'''


class Checked(pica_parse.db.Base):
    __tablename__ = 'checked'

    id = sa.Column(sa.Integer, primary_key=True)
    ppn = sa.Column(sa.String, sa.ForeignKey('records.ppn'), index=True)
    words = sa.Column(sa.Integer)
    errors = sa.Column(sa.Integer, index=True)
    corrected = sa.Column(sa.String)


class Change(pica_parse.db.Base):
    __tablename__ = 'changes'

    id = sa.Column(sa.Integer, primary_key=True)
    ppn = sa.Column(sa.String, sa.ForeignKey('checked.ppn'), index=True)
    suggested = sa.Column(sa.String)
    corrected = sa.Column(sa.String)


class ArcDB(pica_parse.db.PicaDB):
    """wraps an sqlite database containing pica records so they will be
    converted to pica_parse.PicaRecord instances when they are returned.

    It also has facilities for adding verified normalizations into the
    database.
    """
    def __init__(self, sqlachemy_url):
        """database queries for pica records.

        - sqlachemy_url: a sqlalchemy-format database url. see:
        http://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls
        """
        super().__init__(sqlachemy_url)

    def add_input(self, ppn, generated, submitted):
        words, errors, badwords = diff_output(generated, submitted)
        self.session.add(Checked(ppn=ppn, words=words, errors=errors,
                                 corrected=submitted or None))
        if errors:
            self.session.query(Change).filter(Change.ppn == ppn).delete()
            self.session.add_all(
                Change(ppn=ppn, suggested=w[0], corrected=w[1])
                for w in badwords)

    def get_title(self, ppn):
        fields = self[ppn, '021A']
        for field in fields:
            lang = field.get('U')
            if lang is None or lang == 'Latn':
                maintitle = field.get('a')
                break
        subtitle = field.get('d')
        if subtitle:
            title = maintitle + ' ։ ' + subtitle
        else:
            title = maintitle
        return title


def diff_output(generated, submitted):
    errors = 0
    generatedl = [i for i in breaks.split(generated) if i not in nocheck]
    submittedl = [i for i in breaks.split(submitted) if i not in nocheck]
    badwords = []
    if len(submittedl) != len(generatedl):
        errors = 1
        badwords.append((generated, submitted))
    else:
        for gen, sub in zip(generatedl, submittedl):
            if gen != sub:
                errors += 1
                badwords.append((gen, sub))
    words = len(submittedl)
    return words, errors, badwords
