"""
calibre_plugins.comicvine - A calibre metadata source for comicvine
"""
# pylint: disable-msg=R0913,R0904
from functools import partial
import logging
from multiprocessing.pool import ThreadPool
from queue import Queue
import threading

from calibre import setup_cli_handlers
from calibre.ebooks.metadata.opf2 import metadata_to_opf
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.config import OptionParser
import calibre.utils.logging as calibre_logging
from calibre_plugins.comicvine import pycomicvine
from calibre_plugins.comicvine.config import PREFS
from calibre_plugins.comicvine import utils


class Comicvine(Source):
    """Metadata source implementation"""

    name = "Comicvine"
    description = "Downloads metadata and covers from Comicvine"
    author = "Russell Heilling/Bernardo Bandos"
    version = (0, 14, 2)
    minimum_calibre_version = (6, 0, 0)
    capabilities = frozenset(["identify", "cover"])
    touched_fields = frozenset(
        [
            "title",
            "authors",
            "comments",
            "publisher",
            "pubdate",
            "series",
            "identifiers:comicvine",
            "identifiers:comicvine-volume",
        ]
    )

    has_html_comments = True
    can_get_multiple_covers = True

    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger("urls")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(utils.CalibreHandler(logging.DEBUG))
        self._qlock = threading.RLock()
        Source.__init__(self, *args, **kwargs)

    def initialize(self):
        self.token_bucket = utils.TokenBucket()
        pycomicvine.hook_register("pre_request_hook", self.token_bucket.consume)

    def config_widget(self):
        from calibre_plugins.comicvine.config import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()

    def is_configured(self):
        return bool(PREFS.get("api_key"))

    def _print_result(self, result, ranking, opf=False):
        if opf:
            result_text = metadata_to_opf(result)
        else:
            if result.pubdate:
                pubdate = str(result.pubdate.date())
            else:
                pubdate = "Unknown"
            result_text = "(%04d) - %s: %s [%s]" % (
                ranking(result),
                result.identifiers["comicvine"],
                result.title,
                pubdate,
            )
        print(result_text)

    def cli_main(self, args):
        "Perform comicvine lookups from the calibre-debug cli"

        def option_parser():
            "Parse command line options"
            parser = OptionParser(usage="Comicvine [t:title] [a:authors] [i:id]")
            parser.add_option("--opf", "-o", action="store_true", dest="opf")
            parser.add_option(
                "--verbose", "-v", default=False, action="store_true", dest="verbose"
            )
            parser.add_option(
                "--debug_api", default=False, action="store_true", dest="debug_api"
            )
            return parser

        opts, args = option_parser().parse_args(args)
        if opts.debug_api:
            calibre_logging.default_log = calibre_logging.Log(
                level=calibre_logging.DEBUG
            )
        if opts.verbose:
            level = "DEBUG"
        else:
            level = "INFO"
        setup_cli_handlers(logging.getLogger("comicvine"), getattr(logging, level))
        log = calibre_logging.ThreadSafeLog(level=getattr(calibre_logging, level))

        (title, authors, ids) = (None, [], {})
        for arg in args:
            if arg.startswith("t:"):
                title = arg.split(":", 1)[1]
            if arg.startswith("a:"):
                authors.append(arg.split(":", 1)[1])
                authors = authors[0].split("&")
            if arg.startswith("i:"):
                (idtype, identifier) = arg.split(":", 2)[1:]
                ids[idtype] = int(identifier)
        result_queue = Queue()
        self.identify(
            log, result_queue, False, title=title, authors=authors, identifiers=ids
        )
        ranking = self.identify_results_keygen(title, authors, ids)
        for result in sorted(result_queue.queue, key=ranking):
            self._print_result(result, ranking, opf=opts.opf)
            if opts.opf:
                break

    def enqueue(self, log, result_queue, shutdown, issue):
        "Add a result entry to the result queue"
        if shutdown.is_set():
            raise threading.ThreadError
        log.debug("Adding Issue(%d) to queue" % issue.id)
        metadata = utils.build_meta(log, issue)
        if metadata:
            self.clean_downloaded_metadata(metadata)
            with self._qlock:
                result_queue.put(metadata)
            log.debug("Added Issue(%s) to queue" % metadata.title)

    def identify_results_keygen(self, title=None, authors=None, identifiers=None):
        "Provide a keying function for result comparison"
        if not isinstance(title, str):
            title = ""
            issue_number = 0
            title_tokens = ""
        else:
            (issue_number, title_tokens) = utils.normalised_title(self, title)
        return partial(
            utils.keygen,
            title=title,
            authors=authors,
            identifiers=identifiers,
            issue_number=issue_number,
            title_tokens=title_tokens,
        )

    def identify(
        self,
        log,
        result_queue,
        abort,
        title=None,
        authors=None,
        identifiers=None,
        timeout=30,
    ):
        """Attempt to identify comicvine Issue matching given parameters"""
        volume_id = None

        # Do a simple lookup if comicvine identifier present
        if identifiers:
            comicvine_id = identifiers.get("comicvine")
            if comicvine_id is not None:
                log.debug("Looking up Issue(%d)" % int(comicvine_id))
                issue = pycomicvine.Issue(
                    int(comicvine_id),
                    field_list=[
                        "id",
                        "name",
                        "volume",
                        "issue_number",
                        "person_credits",
                        "description",
                        "store_date",
                        "cover_date",
                    ],
                )
                self.enqueue(log, result_queue, threading.Event(), issue)
                return None
            # get the volume id if present
            comicvine_id = identifiers.get("comicvine-volume")
            if comicvine_id is not None:
                log.debug("We have a Volume(%d)" % int(comicvine_id))
                volume_id = int(comicvine_id)

        if title:
            # Look up candidate volumes based on title
            (issue_number, candidate_volumes) = utils.find_title(
                self, title, log, volume_id
            )

            # Look up candidate authors
            candidate_authors = None
            if authors:
                candidate_authors = utils.find_authors(self, authors, log)

            # Look up candidate issues
            candidate_issues = utils.find_issues(candidate_volumes, issue_number, log)

            # if no issues returned when issue_number is specified, query again without it
            if not candidate_issues:
                candidate_issues = utils.find_issues(candidate_volumes, None, log)

            # Refine issue selection based on authors
            if candidate_authors:
                issues = set()
                for author in candidate_authors:
                    issues.update(set(author.issues))
                candidate_issues = issues.intersection(candidate_issues)
            # Queue candidates
            pool = ThreadPool(PREFS.get("worker_threads"))
            shutdown = threading.Event()
            enqueue = partial(self.enqueue, log, result_queue, shutdown)
            try:
                pool.map(enqueue, [issue for issue in candidate_issues])
            finally:
                shutdown.set()

        return None

    def download_cover(
        self,
        log,
        result_queue,
        abort,
        title=None,
        authors=None,
        identifiers=None,
        timeout=30,
        get_best_cover=False,
    ):
        if identifiers and "comicvine" in identifiers:
            for url in utils.cover_urls(identifiers["comicvine"], get_best_cover):
                #        url = 'http://static.comicvine.com' + url
                browser = self.browser
                log("Downloading cover from:", url)
                try:
                    cdata = browser.open_novisit(url, timeout=timeout).read()
                    result_queue.put((self, cdata))
                except:
                    log.exception("Failed to download cover from:", url)
