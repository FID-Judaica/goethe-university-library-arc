import re
import unicodedata
import arc.decode
from deromanize import cacheutils
CacheObject, CacheDB = cacheutils.CacheObject, cacheutils.CacheDB


class FieldError(Exception):
    pass


def loc_converter_factory(simple_reps, set_reps):
    replace = cacheutils.replacer_maker(simple_reps, set_reps)

    def get_loc(rep):
        flat_vowels = cacheutils.strip_chars(rep.keyvalue)
        try:
            loc = ''.join((i[0] for i in replace(flat_vowels)))
        except TypeError:
            print(rep.keyvalue)
            loc = 'whatever'
        if len(loc) > 1:
            if loc[0] == 'ʾ':
                loc = loc[1:]
            if loc[-1] == 'ʾ':
                loc = loc[-1]
            loc = loc.replace('-ʾ', '-')
        return loc

    return get_loc


def loc2phon(loc):
    vowels = set('ieaou')
    gstops = {'ʿ', 'ʾ'}
    phon = loc.replace('ḥ', 'ch').replace('kh', 'ch')
    if phon[-1] == 'h' and phon[-2:-1] in vowels:
        phon = phon[:-1]
    phon = ''.join(
        c for c in unicodedata.normalize('NFD', phon)
        if unicodedata.category(c)[0] == 'L' and c not in gstops
    )
    for v in vowels:
        phon = phon.replace(v+v, v+"'"+v)
    return phon


def remove_prefixes(pairs):
    new = []
    for heb, loc in pairs:
        _, heb, _ = arc.decode.double_junker(heb)
        _, loc, _ = arc.decode.double_junker(loc)
        romlist = loc.split('-')
        newheb = heb[len(romlist)-1:]
        # if len(romlist) > 1:
        #     print(romlist[-1], newheb)
        loc = romlist[-1]
        if len(loc) > 1:
            if loc[0] == 'ʾ':
                loc = loc[1:]
            if loc[-1] == 'ʾ':
                loc = loc[-1]
        new.append([newheb, loc])
    return new


def matcher_factory(simple_reps, set_reps):
    get_loc = loc_converter_factory(simple_reps, set_reps)
    nocheck = {'־', 'h', 'ה', '-', '։', ';'}

    def match_output(generated, submitted):
        breaks = re.compile('[\s־]+')
        submittedl = [i for i in breaks.split(submitted) if i not in nocheck]
        generatedl = [i for i in generated if i.key not in nocheck]
        if len(submittedl) != len(generatedl):
            raise FieldError("number of fields didn't match")
        else:
            matches = []
            for gen, sub in zip(generatedl, submittedl):
                for rep in gen:
                    if str(rep) == sub:
                        matches.append((sub, get_loc(rep)))
                        break

            return matches

    return match_output


def form_builder_factory(simple_reps, set_reps):
    match_output = matcher_factory(simple_reps, set_reps)

    def form_builder(decoded, submitted):
        matches = match_output(decoded, submitted)
        matches = remove_prefixes(matches)
        for m in matches:
            m.append(loc2phon(m[1]))
        return matches

    return form_builder