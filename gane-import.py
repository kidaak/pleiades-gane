
import csv
import datetime
from itertools import chain
import logging
from optparse import OptionParser
import os
import re
import simplejson
import sys

from contentratings.storage import UserRatingStorage
from DateTime import DateTime
from Products.CMFCore.utils import getToolByName
from quadtree import Quadtree
from zope.annotation.interfaces import IAnnotations

from pleiades.bulkup import secure, setup_cmfuid
from pleiades.capgrids import box
from pleiades.dump import getSite, spoofRequest


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
        'batlas') or ob.getId().startswith(
        'undeterm') or ob.getId().startswith(
        'gane') )

def get_accuracy(name):
    main_map = name.get('main-map')
    if main_map:
        return main_map.get('accuracy')
    else:
        return None

def rate(ob, user, val):
    # Set the magnitude or rating of the place
    annotations = IAnnotations(ob)
    if 'contentratings.userrating.three_stars' not in annotations:
        annotations[
            'contentratings.userrating.three_stars'] = UserRatingStorage()
    storage = annotations['contentratings.userrating.three_stars']
    storage.rate(float(val), user)

def capgrids_tree():
    tree = Quadtree((-180, -90, 180, 90))
    keys = {}
    i = 0
    for mapid in range(1, 100):
        mapid = str(mapid)
        for letter in 'abcdefghijklmnop':
            for num in range(1, 10):
                try:
                    b = box(mapid, letter + str(num))
                except IndexError:
                    continue
                v = "%s/%s" % (mapid, (letter + str(num)).capitalize())
                if v not in keys:
                    tree.add(i, b)
                    keys[i] = v
                    i += 1
    return keys, tree

cap_keys, cap_tree = capgrids_tree()

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
        'pmph': 'grc-pam',
        'scr': 'sh',
        'ave': 'ae',
        'bul': 'bg',
        'deu': 'de',
        'ell': 'el',
        'eng': 'en',
        'fas': 'fa',
        'fra': 'fr',
        'hin': 'hi',
        'hun': 'hu',
        'hye': 'hy',
        'ita': 'it',
        'kat': 'ka',
        'kur': 'ku',
        'lat': 'ka',
        'pol': 'pl',
        'por': 'pt',
        'pus': 'ps',
        'ron': 'ro',
        'rus': 'ru',
        'san': 'sa',
        'snd': 'sd',
        'som': 'so',
        'spa': 'es',
        'sqi': 'sq',
        'swa': 'sw',
        'tur': 'tr',
        'urd': 'ur',
        'uzb': 'uz',
        'zho': 'zh'
        }

    import transaction

    for i, (pk, cluster) in enumerate(gane_tree.items()):
        
        # Because 'continue' is used below to skip through the loop, we need
        # to check at the top to see if it's time to batch commit.
        if i > 1 and (i-1) % 100 == 0:
            transaction.commit()
            LOG.info("Subtransaction committed at %s", i)

        savepoint = transaction.savepoint()
        try:
            
            if not pk in cluster:
                LOG.warn("Primary not found, skipping cluster, Pk: %s", pk)
                continue
            
            primary = cluster.pop(pk)
            pid = primary.get('pid')

            LOG.info("Importing cluster, i: %s, Pk: %s, Pid: %s, num items: %s", i, pk, pid, len(cluster))

            if pid:
                place = places[pid]
                action = 'append'
                place_citations = []
                
                LOG.info("Pid: %s, action: %s", pid, action)

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
                action = 'create'
            
                place_citations = [dict(
                    identifier="http://www.worldcat.org/oclc/32624915",
                    range="TAVO Index (Vol. %s, p. %s)" % (
                        gname['reference']['index-volume'],
                        gname['reference']['index-page'] ),
                    type="cites" )]

                for link in gname.get('externalURIs') or []:
                    if "wikipedia" in link['uri']:
                        label = 'Wikipedia "%s."' % link.get('title')
                    else:
                        label = link.get('title', "Untitled GANE Link")
                    place_citations.append(dict(
                        identifier=link['uri'],
                        range=label,
                        type="seeAlso",
                        ))
                
                field = place.getField('referenceCitations')
                field.resize(len(place_citations), place)
                place.setReferenceCitations(place_citations)
                place_citations = []

                now = DateTime(datetime.datetime.now().isoformat())
            
                place.setModificationDate(now)
                repo.save(place, MESSAGE)
            
                LOG.info("Created and archived Place, GANE id: %s, Pleiades id: %s", pk, pid)
            
                wftool.doActionFor(place, action='submit')
                LOG.info("Submitted Place, GANE id: %s, Pleiades id: %s", pk, pid)
            
                wftool.doActionFor(place, action='publish')
                LOG.info("Published Place, GANE id: %s, Pleiades id: %s", pk, pid)
            
            # New name
            for gid, gname, rating in [(pk, primary, 3)] + [
                    (k, v, 2) for k, v in cluster.items() ]:
                
                LOG.info("Naming, gid: %s, gname: %s, rating: %s", gid, gname, rating)

                for lang in (gname.get('title-languages') or
                             [{'iso': None}]):

                    if not gname.get('nameTransliterated'):
                        LOG.warn("No transliteration")

                    # Add a name to the place
                    title = gname['title']
                    description = (
                        "A place name from the TAVO Index (Vol. %s, p. %s)" 
                        % (gname['reference']['index-volume'],
                           gname['reference']['index-page']))
                    nameLanguage = lang_map.get(lang['iso'], lang['iso'])
                    nameTransliterated = u", ".join([title] + 
                        (gname.get('nameTransliterated') or []))
                    text = "GANE OBJECT %s" % gname['GANEid']
                    creators = gname['creators'].split(", ")
                    contributors = gname['authors']
                    contributors = contributors.replace(
                        "F. Deblauwe", "fdeblauwe")
                    contributors = contributors.replace(
                        "E. Kansa", "ekansa")
                    contributors = contributors.split(", ")
                    
                    # Determine a good id for the name
                    nid = utils.normalizeString(title)
                    if len(gname.get('title-languages', None) or []) > 1 and lang['iso']:
                        nid = nid + "-" + lang['iso'].lower()

                    while nid in place.contentIds():
                        match = re.search('-(\d+)$', nid)
                        if match:
                            num = int(match.group(1))
                            nid = re.sub('\d+$', str(num+1), nid)
                        else:
                            nid = nid + "-1"
                    
                    nid = place.invokeFactory(
                        'Name',
                        nid,
                        title=title,
                        description=description,
                        text=text,
                        nameAttested=None,
                        nameLanguage=nameLanguage,
                        nameTransliterated=nameTransliterated,
                        nameType="geographic",
                        creators=creators,
                        contributors=contributors,
                        initialProvenance='TAVO Index')
                    ob = place[nid]

                    atts = [dict(
                        confidence='confident',
                        timePeriod=period_map[p]
                        ) for p in (gname.get('periods') or []) if p in period_map]
                        
                    field = ob.getField('attestations')
                    field.resize(len(atts), ob)
                    ob.setAttestations(atts)

                    citations= [dict(
                        identifier="http://www.worldcat.org/oclc/32624915",
                        range="TAVO Index (Vol. %s, p. %s)" % (
                            gname['reference']['index-volume'],
                            gname['reference']['index-page']),
                        type="cites")]

                    # Possible Wikipedia and other links
                    for link in gname.get('externalURIs') or []:
                    
                        if ("wikipedia" in link['uri'] and 
                            link['uri'] not in [c['identifier'] for c in place_citations]):
                                label = 'Wikipedia "%s."' % link.get('title')
                                place_citations.append(dict(
                                    identifier=link['uri'],
                                    range=label,
                                    type="seeAlso"))
                        else:
                            label = link.get('title', "Untitled GANE Link")
                            citations.append(dict(
                                identifier=link['uri'],
                                range=label,
                                type="seeAlso"))

                    field = ob.getField('referenceCitations')
                    field.resize(len(citations), ob)
                    ob.setReferenceCitations(citations)

                    now = DateTime(datetime.datetime.now().isoformat())
                    ob.setModificationDate(now)
                    repo.save(ob, MESSAGE)
                    rate(ob, "fdeblauwe", rating)
                    rate(ob, "ekansa", rating)

                    LOG.info("Created and archived Name, GANE id: %s, Pleiades id: %s", gid, pid)
            
                    wftool.doActionFor(ob, action='submit')
                    LOG.info("Submitted Name, GANE id: %s, Pleiades id: %s", gid, pid)
            
                    wftool.doActionFor(ob, action='publish')
                    LOG.info("Published Location, GANE id: %s, Pleiades id: %s", gid, pid)

                    if len(place_citations) > 0:
                        field = place.getField('referenceCitations')
                        prev_citations = place.getReferenceCitations()
                        place_citations.extend(prev_citations)
                        field.resize(len(place_citations), place)
                        place.setReferenceCitations(place_citations)
                        place.reindexObject()
                        LOG.info("Updated Place reference citations, GANE id: %s, Pleiades id: %s", gid, pid)

            # Locations

            LOG.info("Locating...")

            if filter(is_high_quality, place.getLocations()):
                # No need for GANE locations
                LOG.info("Place has high quality location(s), continuing...")
                continue

            # Let's take the most accurate coordinates and roll all the
            # periods into one Location.
            points = sorted(filter(
                        lambda t: t[0] in '01234567' and t[2].get('extent'),
                        [(get_accuracy(v), k, v) for 
                            k, v in [(pk, primary)] + cluster.items()] ))
            if len(points) < 1:
                LOG.info("No accurate location found, continuing...")
                continue

            all_periods = set(
                chain(*[(n.get('periods') or []) for n in [primary] + cluster.values()]))

            accuracy, gid, gname = points[0]

            text = "GANE OBJECT %s\nMap: %s\nCorner Coordinates: %s\n" % (
                gname['GANEid'],
                gname['main-map'].get('map'),
                gname.get('extent', {'coordinates': None}).get('coordinates'))

            rating = 1
            if accuracy == '0':
                accuracy = '1'

            extent = gname.get('extent')
            if not extent:
                LOG.info("No extent found, continuing...")
                continue
                
            # find the capgrid containing this point
            if extent['type'] == 'Point':
                b = extent['coordinates']
                b[0] += 0.05
                b[1] += 0.05
                b = b + b
            elif extent['type'] == 'Polygon':
                xs, ys = zip(*extent['coordinates'])
                b = min(xs), min(ys), max(xs), max(ys)
            
            hits = list(cap_tree.likely_intersection(b))

            placeTypes = ['settlement']

            lid = place.invokeFactory(
                'Location',
                'gane-location-%s' % gname['GANEid'],
                title="GANE Location %s" % gname['GANEid'],
                description="Approximate location from the TAVO index",
                text=text,
                featureType=placeTypes,
                creators=creators,
                contributors=contributors,
                initialProvenance='TAVO Index'
                )
            ob = place[lid]
            
            if hits:
                area = 1000000.0
                val = None
                for hit in hits:
                    mapgrid = cap_keys[hit]
                    mapnum, grid = mapgrid.split("/")
                    b = box(mapnum, grid)
                    hit_area = (b[2]-b[0])*(b[3]-b[1])
                    x, y = extent['coordinates']
                    if b[0] <= x <= b[2] and b[1] <= y <= b[3] and hit_area < area:
                        area = hit_area
                        val = mapgrid
                if val:
                    LOG.info("Setting grid location of %s/%s: %s", pid, lid, val)
                    ob.setLocation('http://atlantides.org/capgrids/' + val)
                else:
                    LOG.warn("Grid location of %s/%s unset", pid, lid)

            mdid = "tavo-%s" % accuracy
            metadataDoc = context['features']['metadata'][mdid]
            ob.addReference(metadataDoc, 'location_accuracy')

            atts = [dict(
                confidence='confident', 
                timePeriod=period_map[p]
                ) for p in all_periods if p in period_map]
            field = ob.getField('attestations')
            field.resize(len(atts), ob)
            ob.setAttestations(atts)

            citations= [dict(
                identifier="http://www.worldcat.org/oclc/32624915",
                range="TAVO Index (Vol. %s, p. %s)" % (
                    gname['reference']['index-volume'],
                    gname['reference']['index-page'] ),
                type="cites" )]

            # Possible Wikipedia and other links
            for link in gname.get('externalURIs') or []:
                if ("wikipedia" in link['uri'] and 
                    link['uri'] not in [c['identifier'] for c in place_citations]):
                    label = 'Wikipedia "%s."' % link.get('title')
                    place_citations.append(dict(
                        identifier=link['uri'],
                        range=label,
                        type="seeAlso"))
                else:
                    label = link.get('title', "Untitled GANE Link")
                    citations.append(dict(
                        identifier=link['uri'],
                        range=label,
                        type="seeAlso"))

            field = ob.getField('referenceCitations')
            field.resize(len(citations), ob)
            ob.setReferenceCitations(citations)

            now = DateTime(datetime.datetime.now().isoformat())
            ob.setModificationDate(now)
            repo.save(ob, MESSAGE)
            
            LOG.info("Created and archived Location, GANE id: %s, Pleiades id: %s", gid, pid)
            
            wftool.doActionFor(ob, action='submit')
            LOG.info("Submitted Location, GANE id: %s, Pleiades id: %s", gid, pid)
            
            wftool.doActionFor(ob, action='publish')
            LOG.info("Published Location, GANE id: %s, Pleiades id: %s", gid, pid)
            
        except Exception, e:
            savepoint.rollback()
            LOG.exception("Rolled back after catching exception: %s in %s" % (e, pk))

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

    app = spoofRequest(app)
    site = getSite(app)

    setup_cmfuid(site)
    secure(site, opts.user or 'admin')
    
    main(site, data, period_map)

    app._p_jar.sync()


