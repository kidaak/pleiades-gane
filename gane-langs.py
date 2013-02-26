
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
"New languages for the Near East from the "
"Alexandria Archive Institute's GANE project: "
"http://alexandriaarchive.org/projects/gane/." )

def main(context, rows):
    
    catalog = getToolByName(context, 'portal_catalog')
    repo = getToolByName(context, 'portal_repository')
    wftool = getToolByName(context, 'portal_workflow')
    utils = getToolByName(context, 'plone_utils')
    langs = context['vocabularies']['ancient-name-languages']
    
    import transaction
    savepoint = transaction.savepoint()
    try:

        for row in rows[1:]:
            
            tavo, title, iso, ll, note = row
            lid = ll or iso
            if lid in langs:
                LOG.info("Existing language %s", lid)
                continue
            
            if ll:
                descr = u"From LINGUIST list"
            else:
                descr = u"From ISO 639-3"

            lid = langs.invokeFactory(
                'PleiadesVocabularyTerm',
                lid,
                title=title,
                description=(descr + u" (TAVO abbrev: %s)" % 
                             tavo.decode("utf-8") ))
            lang = langs[lid]

            now = DateTime(datetime.datetime.now().isoformat())
            lang.setModificationDate(now)
            repo.save(lang, MESSAGE)
            wftool.doActionFor(lang, action='submit')
            wftool.doActionFor(lang, action='publish')
            lang.reindexObject()
                
            LOG.info("Created language %s", lid)

    except Exception, e:
        savepoint.rollback()
        LOG.error("Rolled back after catching exception: %s" % e)
 
    transaction.commit()

if __name__ == '__main__':
    # Zopectl doesn't handle command line arguments well, necessitating quoting
    # like this:
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
    f = open(filename, 'rb')
    rows = list(csv.reader(f))
    site = app['plone']
    setup_cmfuid(site)
    secure(site, opts.user or 'admin')
    main(site, rows)
    app._p_jar.sync()


