"""
Some functions for dealing with Hebrew dates.
"""
import string
import deromanize
import hebrew_numbers

num_strip = deromanize.stripper_factory(string.digits)


def date2years(datestring):
    probably_dates = (
        split.strip(string.punctuation)
        for part in datestring.split()
        for piece in part.split("-")
        for split in piece.split("/")
    )
    for date in probably_dates:
        if not date:
            continue
        try:
            _, d, _ = num_strip(date)
            yield int(d)
        except ValueError:
            yield hebrew_numbers.gematria_to_int(date)


def yearnorm(year):
    if 6000 < year or year < 32:
        return ()
    if year < 1000:
        year += 5000
    if year > 3760:
        newyear = year - 3760
        return (year, newyear, newyear - 1)
    else:
        return (year,)
