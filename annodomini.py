"""annodomini: utilities for Anno Domini dates and ranges"""

def to_ad(year):
    """Takes an integer year and returns an AD/BC formatted string.

    No calendar adjustments of any kind are made.
    
    Example:
    
      >>> print to_ad(1900)
      AD 1900
      >>> print to_ad(-100)
      100 BC
    """
    if year == 0:
        raise ValueError("There is no year 0 in the AD system")
    sign = (year>0)*2-1
    if sign >= 0:
        return u"AD %d" % year
    else:
        return u"%d BC" % (sign*year)

def to_ad_range(start, stop):
    """Takes two integer years and returns an AD/BC formatted string.

    The result is consistent with Wikipedia policy: 
    http://en.wikipedia.org/wiki/Wikipedia:Manual_of_Style/Dates_and_numbers

    Example:

      >>> to_ad_range(-100, 100)
      u'100 BC \u2013 AD 100'
      >>> to_ad_range(100, 200)
      u'AD 100\u2013200'
    """
    if start == 0 or stop == 0:
        raise ValueError("There is no year 0 in the AD system")
    sign_start = (start>0)*2-1
    sign_stop = (stop>0)*2-1
    abs_start = abs(start)
    abs_stop = abs(stop)
    if sign_start < 0 and sign_stop < 0:
        return u"%s\u2013%s BC" % (
            max(abs_start, abs_stop), min(abs_start, abs_stop) )
    elif sign_start > 0 and sign_stop > 0:
        return u"AD %s\u2013%s" % (
            min(abs_start, abs_stop), max(abs_start, abs_stop) )
    else:
        return u"%s \u2013 %s" % (
            to_ad(min(start, stop)), to_ad(max(start, stop)) )

