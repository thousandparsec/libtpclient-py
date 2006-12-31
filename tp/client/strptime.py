"""Strptime-related classes and functions.

CLASSES:
    TimeRE -- Creates regexes for pattern matching a string of text containing
                time information

FUNCTIONS:
    strptime -- Calculates the time struct represented by the passed-in string

"""
import time
import calendar
from re import compile as re_compile
from re import IGNORECASE
from re import escape as re_escape
from datetime import date as datetime_date
try:
    from thread import allocate_lock as _thread_allocate_lock
except:
    from dummy_thread import allocate_lock as _thread_allocate_lock

__author__ = "Brett Cannon"
__email__ = "brett@python.org"

__all__ = ['strptime']

class TimeRE(dict):
    """Handle conversion from format directives to regexes."""

    def __init__(self):
        """Create keys/values.

        Order of execution is important for dependency reasons.

        """
        base = super(TimeRE, self)
        base.__init__({
            # The " \d" part of the regex is to make %c from ANSI C work
            'd': r"(?P<d>3[0-1]|[1-2]\d|0[1-9]|[1-9]| [1-9])",
            'H': r"(?P<H>2[0-3]|[0-1]\d|\d)",
            'I': r"(?P<I>1[0-2]|0[1-9]|[1-9])",
            'j': r"(?P<j>36[0-6]|3[0-5]\d|[1-2]\d\d|0[1-9]\d|00[1-9]|[1-9]\d|0[1-9]|[1-9])",
            'm': r"(?P<m>1[0-2]|0[1-9]|[1-9])",
            'M': r"(?P<M>[0-5]\d|\d)",
            'S': r"(?P<S>6[0-1]|[0-5]\d|\d)",
            'U': r"(?P<U>5[0-3]|[0-4]\d|\d)",
            'w': r"(?P<w>[0-6])",
            # W is set below by using 'U'
            'y': r"(?P<y>\d\d)",
            #XXX: Does 'Y' need to worry about having less or more than
            #     4 digits?
            'Y': r"(?P<Y>\d\d\d\d)",
            'A': self.__seqToRE(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'], 'A'),
            'a': self.__seqToRE(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], 'a'),
            'B': self.__seqToRE(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'], 'B'),
            'b': self.__seqToRE(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 'b'),
            'p': self.__seqToRE(['am', 'pm'], 'p'),
            'Z': self.__seqToRE(['utc', 'cst', 'gmt', 'cst'], 'Z'),
            '%': '%'})
        base.__setitem__('W', base.__getitem__('U').replace('U', 'W'))
        base.__setitem__('c', self.pattern('%a %b %d %H:%M:%S %Y'))
        base.__setitem__('x', self.pattern('%m/%d/%y'))
        base.__setitem__('X', self.pattern('%H:%M:%S'))

    def __seqToRE(self, to_convert, directive):
        """Convert a list to a regex string for matching a directive.

        Want possible matching values to be from longest to shortest.  This
        prevents the possibility of a match occuring for a value that also
        a substring of a larger value that should have matched (e.g., 'abc'
        matching when 'abcdef' should have been the match).

        """
        to_convert = sorted(to_convert, key=len, reverse=True)
        for value in to_convert:
            if value != '':
                break
        else:
            return ''
        regex = '|'.join(re_escape(stuff) for stuff in to_convert)
        regex = '(?P<%s>%s' % (directive, regex)
        return '%s)' % regex

    def pattern(self, format):
        """Return regex pattern for the format string.

        Need to make sure that any characters that might be interpreted as
        regex syntax are escaped.

        """
        processed_format = ''
        # The sub() call escapes all characters that might be misconstrued
        # as regex syntax.  Cannot use re.escape since we have to deal with
        # format directives (%m, etc.).
        regex_chars = re_compile(r"([\\.^$*+?\(\){}\[\]|])")
        format = regex_chars.sub(r"\\\1", format)
        whitespace_replacement = re_compile('\s+')
        format = whitespace_replacement.sub('\s*', format)
        while '%' in format:
            directive_index = format.index('%')+1
            processed_format = "%s%s%s" % (processed_format,
                                           format[:directive_index-1],
                                           self[format[directive_index]])
            format = format[directive_index+1:]
        return "%s%s" % (processed_format, format)

    def compile(self, format):
        """Return a compiled re object for the format string."""
        return re_compile(self.pattern(format), IGNORECASE)

_cache_lock = _thread_allocate_lock()
# DO NOT modify _TimeRE_cache or _regex_cache without acquiring the cache lock
# first!
_TimeRE_cache = TimeRE()
_CACHE_MAX_SIZE = 5 # Max number of regexes stored in _regex_cache
_regex_cache = {}

def strptime(data_string, format="%a %b %d %H:%M:%S %Y"):
    """Return a time struct based on the input string and the format string."""
    global _TimeRE_cache
    _cache_lock.acquire()
    try:
        time_re = _TimeRE_cache
        if len(_regex_cache) > _CACHE_MAX_SIZE:
            _regex_cache.clear()
        format_regex = _regex_cache.get(format)
        if not format_regex:
            format_regex = time_re.compile(format)
            _regex_cache[format] = format_regex
    finally:
        _cache_lock.release()
    found = format_regex.match(data_string)
    if not found:
        raise ValueError("time data did not match format:  data=%s  fmt=%s" %
                         (data_string, format))
    if len(data_string) != found.end():
        raise ValueError("unconverted data remains: %s" %
                          data_string[found.end():])
    year = 1900
    month = day = 1
    hour = minute = second = 0
    tz = -1
    # Default to -1 to signify that values not known; not critical to have,
    # though
    week_of_year = -1
    week_of_year_start = -1
    # weekday and julian defaulted to -1 so as to signal need to calculate
    # values
    weekday = julian = -1
    found_dict = found.groupdict()
    for group_key in found_dict.iterkeys():
        # Directives not explicitly handled below:
        #   c, x, X
        #      handled by making out of other directives
        #   U, W
        #      worthless without day of the week
        if group_key == 'y':
            year = int(found_dict['y'])
            # Open Group specification for strptime() states that a %y
            #value in the range of [00, 68] is in the century 2000, while
            #[69,99] is in the century 1900
            if year <= 68:
                year += 2000
            else:
                year += 1900
        elif group_key == 'Y':
            year = int(found_dict['Y'])
        elif group_key == 'm':
            month = int(found_dict['m'])
        elif group_key == 'B':
            month = ['', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'].index(found_dict['B'].lower())
        elif group_key == 'b':
            month = ['', 'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'].index(found_dict['b'].lower())
        elif group_key == 'd':
            day = int(found_dict['d'])
        elif group_key == 'H':
            hour = int(found_dict['H'])
        elif group_key == 'I':
            hour = int(found_dict['I'])
            ampm = found_dict.get('p', '').lower()
            # If there was no AM/PM indicator, we'll treat this like AM
            if ampm in ('', 'am'):
                # We're in AM so the hour is correct unless we're
                # looking at 12 midnight.
                # 12 midnight == 12 AM == hour 0
                if hour == 12:
                    hour = 0
            elif ampm == 'pm':
                # We're in PM so we need to add 12 to the hour unless
                # we're looking at 12 noon.
                # 12 noon == 12 PM == hour 12
                if hour != 12:
                    hour += 12
        elif group_key == 'M':
            minute = int(found_dict['M'])
        elif group_key == 'S':
            second = int(found_dict['S'])
        elif group_key == 'A':
            weekday = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].index(found_dict['A'].lower())
        elif group_key == 'a':
            weekday = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].index(found_dict['a'].lower())
        elif group_key == 'w':
            weekday = int(found_dict['w'])
            if weekday == 0:
                weekday = 6
            else:
                weekday -= 1
        elif group_key == 'j':
            julian = int(found_dict['j'])
        elif group_key in ('U', 'W'):
            week_of_year = int(found_dict[group_key])
            if group_key == 'U':
                # U starts week on Sunday
                week_of_year_start = 6
            else:
                # W starts week on Monday
                week_of_year_start = 0
        elif group_key == 'Z':
            # Since -1 is default value only need to worry about setting tz if
            # it can be something other than -1.
            found_zone = found_dict['Z'].lower()
            for value, tz_values in enumerate((frozenset(['utc', 'cst', 'gmt']), frozenset(['cst']))):
                if found_zone in tz_values:
                    # Deal with bad locale setup where timezone names are the
                    # same and yet time.daylight is true; too ambiguous to
                    # be able to tell what timezone has daylight savings
                    if (time.tzname[0] == time.tzname[1] and
                       time.daylight and found_zone not in ("utc", "gmt")):
                        break
                    else:
                        tz = value
                        break
    # If we know the week of the year and what day of that week, we can figure
    # out the Julian day of the year
    # Calculations below assume 0 is a Monday
    if julian == -1 and week_of_year != -1 and weekday != -1:
        # Calculate how many days in week 0
        first_weekday = datetime_date(year, 1, 1).weekday()
        preceeding_days = 7 - first_weekday
        if preceeding_days == 7:
            preceeding_days = 0
        # Adjust for U directive so that calculations are not dependent on
        # directive used to figure out week of year
        if weekday == 6 and week_of_year_start == 6:
            week_of_year -= 1
        # If a year starts and ends on a Monday but a week is specified to
        # start on a Sunday we need to up the week to counter-balance the fact
        # that with %W that first Monday starts week 1 while with %U that is
        # week 0 and thus shifts everything by a week
        if weekday == 0 and first_weekday == 0 and week_of_year_start == 6:
            week_of_year += 1
        # If in week 0, then just figure out how many days from Jan 1 to day of
        # week specified, else calculate by multiplying week of year by 7,
        # adding in days in week 0, and the number of days from Monday to the
        # day of the week
        if week_of_year == 0:
            julian = 1 + weekday - first_weekday
        else:
            days_to_week = preceeding_days + (7 * (week_of_year - 1))
            julian = 1 + days_to_week + weekday
    # Cannot pre-calculate datetime_date() since can change in Julian
    #calculation and thus could have different value for the day of the week
    #calculation
    if julian == -1:
        # Need to add 1 to result since first day of the year is 1, not 0.
        julian = datetime_date(year, month, day).toordinal() - \
                  datetime_date(year, 1, 1).toordinal() + 1
    else:  # Assume that if they bothered to include Julian day it will
           #be accurate
        datetime_result = datetime_date.fromordinal((julian - 1) + datetime_date(year, 1, 1).toordinal())
        year = datetime_result.year
        month = datetime_result.month
        day = datetime_result.day
    if weekday == -1:
        weekday = datetime_date(year, month, day).weekday()
    return time.struct_time((year, month, day, hour, minute, second, weekday, julian, tz))
