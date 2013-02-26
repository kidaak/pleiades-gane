
import csv
import datetime
import logging
from optparse import OptionParser
import os
import simplejson
import sys

from contentratings.storage import UserRatingStorage
from DateTime import DateTime
from Products.CMFCore.utils import getToolByName
from zope.annotation.interfaces import IAnnotations

from pleiades.bulkup import secure, setup_cmfuid

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s") )
root_logger.addHandler(handler)
LOG = logging.getLogger('pleiades.scripts')

MESSAGE = (
"New locations, names, and places for the Ancient Near East from the "
"Alexandria Archive Institute's GANE project: "
"http://alexandriaarchive.org/projects/gane/." )

DIDKEY = 'OBJECTID'

def is_high_quality(ob):
    return not(
        ob.getId().startswith(
        'darmc') or ob.getId().startswith(
        'batlas') or ob.getId().startswith(
        'undeterm') or ob.getId().startswith(
        'gane') )

def rate(ob, user, val):
    # Set the magnitude or rating of the place
    annotations = IAnnotations(ob)
    if 'contentratings.userrating.three_stars' not in annotations:
        annotations[
            'contentratings.userrating.three_stars'] = UserRatingStorage()
    storage = annotations['contentratings.userrating.three_stars']
    storage.rate(float(val), user)

def main(context, gane_tree, period_map):
    
    catalog = getToolByName(context, 'portal_catalog')
    repo = getToolByName(context, 'portal_repository')
    wftool = getToolByName(context, 'portal_workflow')
    utils = getToolByName(context, 'plone_utils')
    places = context['places']

    # Language adjustment
    lang_map = {
        'arbd': 'arbd',
        'ethp': 'amh', 
        'hbbb': 'hbo', 
        'nabt': 'qhy-nor', 
        'pmph': 'grc-pam' }

    import transaction
    savepoint = transaction.savepoint()
    try:

        # Proper language codes

        for pk, cluster in gane_tree.items():
            
            if not pk in cluster:
                LOG.info("Skipping %s", pk)
                continue
            
            primary = cluster.pop(pk)

            if "pleiades.stoa.org" in primary['placeURI']:
                pass

            elif "gap.alexandriaarchive.org" in primary['placeURI']:
                
                gname = primary
                title = gname['title']
                description = "A place from the TAVO Index"
                text = "GANE OBJECT %s" % gname['GANEid']
                placeTypes = ['settlement']
                creators = gname['creators'].split(", ")
                contributors = gname['authors']
                contributors = contributors.replace("F. Deblauwe", "fdeblauwe")
                contributors = contributors.replace("E. Kansa", "ekansa")
                contributors = contributors.split(", ")

                pid = places.invokeFactory('Place',
                    places.generateId(prefix=''),
                    title=title,
                    placeType=placeTypes,
                    description=description,
                    text=text,
                    creators=creators,
                    contributors=contributors,
                    initialProvenance='TAVO Index'
                    )
                place = places[pid]
            
                citations= [dict(
                    identifier="http://www.worldcat.org/oclc/32624915",
                    range="TAVO Index (Vol. %s, pp. %s)" % (
                        gname['reference']['index-volume'],
                        gname['reference']['index-page'] ),
                    type="cites" )]

                for link in gname.get('externalURIs') or []:
                    citations.append(dict(
                        identifier=link['uri'],
                        range=link.get('title', "Untitled GANE Link"),
                        type="seeAlso",
                        ))

                field = place.getField('referenceCitations')
                field.resize(len(citations), place)
                place.setReferenceCitations(citations)

                now = DateTime(datetime.datetime.now().isoformat())
            
                place.setModificationDate(now)
                repo.save(place, MESSAGE)
                #wftool.doActionFor(location, action='submit')
                #wftool.doActionFor(location, action='publish')
                place.reindexObject()
                
                LOG.info("Created gname GANE place %d", pid)

            # New name
            for gid, gname, rating in [(pk, primary, 3)] + [
                    (k, v, 2) for k, v in cluster.items() ]:
                
                for lang in (gname.get('title-languages') or
                             [{'iso': None}]):
                    # Add a name to the place
                    nameAttested = gname['title']
                    title = (gname.get('nameTransliterated') or
                             [nameAttested] )[0]
                    description = (
                        "A place name from the TAVO Index (Vol. %s, pp. %s)" 
                        % (gname['reference']['index-volume'],
                           gname['reference']['index-page']))
                    nameLanguage = lang_map.get(lang['iso'], lang['iso'])
                    nameTransliterated = ", ".join(
                        gname.get('nameTransliterated') or [] )
                    text = "GANE OBJECT %s" % gname['GANEid']
                    creators = gname['creators'].split(", ")
                    contributors = gname['authors']
                    contributors = contributors.replace(
                        "F. Deblauwe", "fdeblauwe")
                    contributors = contributors.replace(
                        "E. Kansa", "ekansa")
                    contributors = contributors.split(", ")

                    nid = place.invokeFactory(
                        'Name',
                        utils.normalizeString(title),
                        title=title,
                        description=description,
                        text=text,
                        nameAttested = nameAttested,
                        nameLanguage = nameLanguage,
                        nameTransliterated=nameTransliterated,
                        nameType="geographic",
                        creators=creators,
                        contributors=contributors,
                        initialProvenance='TAVO Index')
                    ob = place[nid]

                    atts = [dict(
                        confidence='confident', 
                        timePeriod=period_map[p] # utils.normalizeString(p) 
                        ) for p in gname.get('periods', [])]
                    field = ob.getField('attestations')
                    field.resize(len(atts), ob)
                    ob.setAttestations(atts)

                    citations= [dict(
                        identifier="http://www.worldcat.org/oclc/32624915",
                        range="TAVO Index (Vol. %s, pp. %s)" % (
                            gname['reference']['index-volume'],
                            gname['reference']['index-page']),
                        type="cites")]

                    if gid != pk:
                        # Skip external links that have already been saved
                        # on the parent place

                        for link in gname.get('externalURIs') or []:
                            citations.append(dict(
                                identifier=link['uri'],
                                range=link.get('title', "Untitled GANE Link"),
                                type="seeAlso"))

                        field = ob.getField('referenceCitations')
                        field.resize(len(citations), ob)
                        ob.setReferenceCitations(citations)

                    now = DateTime(datetime.datetime.now().isoformat())
                    ob.setModificationDate(now)
                    repo.save(ob, MESSAGE)
                    rate(ob, "fdeblauwe", rating)
                    rate(ob, "ekansa", rating)

                    #wftool.doActionFor(ob, action='submit')
                    #wftool.doActionFor(ob, action='publish')
                
                    ob.reindexObject()

                    LOG.info("Created gname (Name) GANE %d", nid)

                if filter(is_high_quality, place.getLocations()):
                    # No need for GANE locations
                    continue

                extent = gname.get('extent')
                if not extent:
                    continue
                
                geometry = "%s:%s" % (extent['type'], extent['coordinates'])
                placeTypes = ['settlement']

                lid = place.invokeFactory(
                    'Location',
                    'gane-location-%s' % gname['GANEid'],
                    title="GANE Location %s" % gname['GANEid'],
                    description="Approximate location from the TAVO index",
                    text=text,
                    featureType=placeTypes,
                    geometry=geometry,
                    creators=creators,
                    contributors=contributors,
                    initialProvenance='TAVO Index'
                    )
                ob = place[lid]
                
                # TODO: accuracy assessment
                # positional accuracy
                #geostatus = row.get('GEOSTATUS').strip() or 'C'
                #mdid = "darmc-%s" % geostatus.lower()
                #metadataDoc = context['features']['metadata'][mdid]
                #location.addReference(metadataDoc, 'location_accuracy')

                atts = [dict(
                    confidence='confident', 
                    timePeriod=period_map[p] # utils.normalizeString(p) 
                    ) for p in gname.get('periods', []) ]
                field = ob.getField('attestations')
                field.resize(len(atts), ob)
                ob.setAttestations(atts)

                citations= [dict(
                    identifier="http://www.worldcat.org/oclc/32624915",
                    range="TAVO Index (Vol. %s, pp. %s)" % (
                        gname['reference']['index-volume'],
                        gname['reference']['index-page'] ),
                    type="cites" )]

                if gid != pk:
                    # Skip external links that have already been saved
                    # on the parent place

                    for link in gname.get('externalURIs') or []:
                        citations.append(dict(
                            identifier=link['uri'],
                            range=link.get('title', "Untitled GANE Link"),
                            type="seeAlso"))

                    field = ob.getField('referenceCitations')
                    field.resize(len(citations), ob)
                    ob.setReferenceCitations(citations)

                now = DateTime(datetime.datetime.now().isoformat())
                ob.setModificationDate(now)
                repo.save(ob, MESSAGE)
                #wftool.doActionFor(ob, action='submit')
                #wftool.doActionFor(ob, action='publish')
                ob.reindexObject()

                LOG.info("Created gname (Location) GANE %s", nid)

            place.setModificationDate(now)
            repo.save(place, MESSAGE)
            place.reindexObject()

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
    data = simplejson.loads(open(filename, 'rb').read())

    # Mapping of TAVO period names to keys
    path = os.path.sep.join(
        [os.path.dirname(sys.argv[0]), "time-periods.csv"])
    f = open(os.path.abspath(path))
    rows = list(csv.reader(f))[1:]
    f.close()
    period_map = dict([
        (title, tid) for title, tid, start, stop, area, note, other 
        in rows ])

    site = app['plone']
    setup_cmfuid(site)
    secure(site, opts.user or 'admin')
    
    main(site, data, period_map)

    app._p_jar.sync()

