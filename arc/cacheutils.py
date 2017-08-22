from deromanize import cacheutils
import unicodedata
import arc.decode
VOWELS = set('ieaou')
gstops = {'ʿ', 'ʾ'}


def loc_coverter_factory(simple_reps, set_reps):
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
    phon = loc.replace('ḥ', 'ch').replace('kh', 'ch')
    if phon[-1] == 'h' and phon[-2:-1] in VOWELS:
        phon = phon[:-1]
    phon = ''.join(
        c for c in unicodedata.normalize('NFD', phon)
        if unicodedata.category(c)[0] == 'L' and c not in gstops
    )
    for v in VOWELS:
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
