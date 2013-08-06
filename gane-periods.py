
import csv
import datetime
import logging
from optparse import OptionParser
import sys

from DateTime import DateTime
from Products.CMFCore.utils import getToolByName

from pleiades.bulkup import secure, setup_cmfuid
from Products.PleiadesEntity.time import to_ad

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s") )
root_logger.addHandler(handler)
LOG = logging.getLogger('pleiades.scripts')

MESSAGE = (
"New time periods for the Near East from the "
"Alexandria Archive Institute's GANE project: "
"http://alexandriaarchive.org/projects/gane/." )

def fmt_time_range(start, stop):
    start = int(start.replace(",", ""))
    stop = int(stop.replace(",", ""))
    a = to_ad(start)
    b = to_ad(stop)
    start = abs(start)
    stop = abs(stop)
    if "BC" in a and "BC" in b:
        return u"%s\u2013%s BC" % (max(start, stop), min(start, stop))
    elif "AD" in a and "AD" in b:
        return u"AD %s\u2013%s" % (min(start, stop), max(start, stop))
    else:
        return u"%s \u2013 %s" % (a, b)

def main(context, rows):
    
    catalog = getToolByName(context, 'portal_catalog')
    repo = getToolByName(context, 'portal_repository')
    wftool = getToolByName(context, 'portal_workflow')
    utils = getToolByName(context, 'plone_utils')
    periods = context['vocabularies']['time-periods']
    
    import transaction
    savepoint = transaction.savepoint()
    try:

        for row in rows[1:]:
            
            title, tid, start, stop, area, note, other = row
            if tid in periods:
                continue

            start = start.replace(",", "")
            stop = stop.replace(",", "")

            title=u"%s (%s)" % (
                unicode(title, "utf-8"),
                fmt_time_range(start, stop) )

            tid = periods.invokeFactory(
                'PleiadesVocabularyTerm',
                tid,
                title=title,
                description="%s [[%s,%s]]" % (note or area, start, stop) )
            period = periods[tid]

            now = DateTime(datetime.datetime.now().isoformat())
            period.setModificationDate(now)
            repo.save(period, MESSAGE)
            wftool.doActionFor(period, action='submit')
            wftool.doActionFor(period, action='publish')
            period.reindexObject()
                
            LOG.info("Created period %s", tid)

    except Exception, e:
        savepoint.rollback()
        LOG.error("Rolled back after catching exception: %s" % e)
 
    transaction.commit()

if __name__ == '__main__':
    # Zopectl doesn't handle command line arguments well, necessitating
    # quoting :wqlike this:
    #
    # $ instance run 'names.py -f names.csv -m "Set all descriptions from names-up2.csv again" -j description'
    
    parser = OptionParser()
    parser.add_option(
        "-f", "--file", dest="filename",
        help="Input filename", metavar="FILE")
    parser.add_option(
        "-u", "--user", dest="user",
        help="Run script as user")

    opts, args = parser.parse_args(sys.argv[1:])
    filename = opts.filename
    f = open(filename)
    rows = list(csv.reader(f))
    site = app['plone']
    setup_cmfuid(site)
    secure(site, opts.user or 'admin')
    main(site, rows)
    app._p_jar.sync()

