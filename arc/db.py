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


breaks = re.compile('[\s־]+')
nocheck = {'־', 'ה', '-', '։', ';'}


class ArcDB(pica_parse.db.PicaDB):
    """wraps an sqlite database containing pica records so they will be
    converted to pica_parse.PicaRecord instances when they are returned.

    It also has facilities for adding verified normalizations into the
    database.
    """
    def __init__(self, connection, sep='ƒ'):
        """database queries for pica records.

        - connection: an sqlit3 database. The schema for the records is
          assigned to the values of the variable `scheme` near the top of
          the file.

        - sep is the character used to separate subfields in the records.
        """
        super().__init__(connection)
        self.sep = sep
        with self.con as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS checked (
                ppn VARCHAR PRIMARY KEY,
                words INTEGER,
                errors INTEGER,
                corrected VARCHAR
            );
            CREATE INDEX IF NOT EXISTS errors ON checked (errors);

            CREATE TABLE IF NOT EXISTS changes (
                ppn VARCHAR,
                suggested VARCHAR,
                corrected VARCHAR
            );
            CREATE INDEX IF NOT EXISTS  change_ppns ON changes (ppn);

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
                            as float) as clean
            ''')

    def add_input(self, ppn, generated, submitted):
        words, errors, badwords = diff_output(generated, submitted)
        self.con.execute(
            'INSERT OR REPLACE INTO checked VALUES (?, ?, ?, ?)',
            (ppn, words, errors, submitted or None))
        if errors:
            self.con.execute('DELETE FROM changes WHERE ppn = ?', (ppn,))
            self.con.executemany('INSERT INTO changes VALUES(?, ?, ?)',
                                 ((ppn, *w) for w in badwords))

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


if __name__ == '__main__':
    from pathlib import Path
    import sqlite3
    PROJECT_DIR = Path(__file__).absolute().parents[1]
    DB_PATH = PROJECT_DIR/'pica.db'
    db = ArcDB(sqlite3.connect(str(DB_PATH)))
