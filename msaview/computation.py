import threading
import urllib2 
import xml.etree.ElementTree as etree

import gobject

from action import (Action,
                    register_action)

# Threaded download helpers require threads to be inited. 
# There is no sane reason not to init them, says ronny @ #pygtk IRC, because
# the overhead of having needlessly inited threads in low level applications
# is in this case already impacted by using python.  
gobject.threads_init()

from preset import NamespaceIgnorantXMLTreeBuilder

class ComputeJob(object):
    def __init__(self, source_id, fcn, args=None):
        if args is None:
            args = ()
        self.source_id = source_id
        self.fcn = fcn
        self.args = args

class BackgroundTask(gobject.GObject):
    __gsignals__ = dict(
        progress = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            (gobject.TYPE_FLOAT, # Fraction of work completed so far, 0.0--1.0. 
             gobject.TYPE_BOOLEAN, # True if the task is finished? 
             gobject.TYPE_PYOBJECT # Any results from this part of the task, or None.
             )),
        error = (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            (gobject.TYPE_STRING, # one of 'error' or 'abort' 
             gobject.TYPE_PYOBJECT, # error data (any type of object) or None. 
             )))
    def __init__(self):
        gobject.GObject.__init__(self)
        self._abort = False
        
    def run(self):
        """Process one part of the task. Override to do something useful."""
        if self._abort:
            return False
        error = False
        if error:
            error_data = None
            self.emit('error', 'error', error_data)
        progress = 1.0
        finished = True
        part_results = None
        self.emit('progress', progress, finished, part_results)
        return not finished
    
    def abort(self):
        self.emit('error', 'abort', None)
        self._abort = True

class ComputeManager(object):
    def __init__(self, jobs=None, counter=0):
        if jobs is None:
            jobs = {}
        self.jobs = jobs
        self.counter = counter
    
    def _wrap(self, fcn, id):
        def wrapper(*args, **kw):
            b = fcn(*args, **kw)
            if not b:
                self.source_remove(id)
            return b
        return wrapper
        
    def idle_add(self, fcn, *args, **kw):
        if isinstance(fcn, BackgroundTask):
            fcn = fcn.process
        counter = self.counter
        fcn = self._wrap(fcn, counter)
        source_id = gobject.idle_add(fcn, *args, **kw)
        job = ComputeJob(source_id, fcn, args)
        self.jobs[counter] = job
        self.counter += 1
        return counter
        
    def timeout_add(self, interval, fcn, *args, **kw):
        if isinstance(fcn, BackgroundTask):
            fcn = fcn.process
        counter = self.counter
        fcn = self._wrap(fcn, counter)
        source_id = gobject.timeout_add(interval, fcn, *args, **kw)
        job = ComputeJob(source_id, fcn, args)
        self.jobs[counter] = job
        self.counter += 1
        return counter
        
    def source_remove(self, id):
        try:
            job = self.jobs.pop(id)
        except:
            return
        gobject.source_remove(job.source_id)
        
    def computing(self):
        return bool(self.jobs)
    
    def compute_all(self):
        while self.jobs:
            for id, job in self.jobs.items():
                job.fcn(*job.args)

    def abort_all(self):
        for id, job in self.jobs.items():
            if isinstance(job, BackgroundTask):
                job.abort()
            self.source_remove(id)
        

# Integrated components should not use this compute manager, but 
# rather one from one of their ancestors. See Component.get_compute_manager().
global_compute_manager = ComputeManager()

# Threaded download helpers 

class Downloader(threading.Thread):
    def __init__(self, items=None):
        threading.Thread.__init__(self)
        if items is None:
            items = []
        self.items = items
        self.results = []
        self.error = None
        self._abort = False
    
    def parse(self, response):
        return response.read()
    
    def download(self, item):
        if isinstance(item, dict):
            return urllib2.urlopen(**item)
        if isinstance(item, str):
            return urllib2.urlopen(item)
        return urllib2.urlopen(*item)
    
    def run(self):
        try:
            for i, item in enumerate(self.items):
                if self._abort:
                    break
                self.results.append(self.parse(self.download(item)))
        except Exception, e:
            self.error = i, item, e
       
    def abort(self):
        self._abort = True
        
class ETreeDownloader(Downloader):
    parser_class = etree.XMLTreeBuilder
    def parse(self, response):
        return etree.parse(response, self.parser_class())

class SimpleETreeDownloader(ETreeDownloader):
    parser_class = NamespaceIgnorantXMLTreeBuilder
    
class DownloadTask(BackgroundTask):
    url = None
    downloader_class = Downloader
    batch_size = 100
    
    def __init__(self, msa=None, id_enumeration=None, batch_size=None, url=None):
        BackgroundTask.__init__(self)
        self.msa = msa
        if id_enumeration is None:
            id_enumeration = []
        self.id_enumeration = id_enumeration
        if batch_size is None:
            batch_size = self.__class__.batch_size
        self.batch_size = batch_size
        if url is None:
            url = self.__class__.url
        self.url = url
        self.progress = 0
        self.total = len(id_enumeration)
        self.downloader = None
        self.results = []
    
    def get_urls(self):
        return [self.url % id for i, id in self.id_enumeration[self.progress:self.progress+self.batch_size]]
    
    def download(self, block=False):
        self.downloader = self.downloader_class(self.get_urls())
        if block:
            self.downloader.run()
        else:
            self.downloader.daemon = True
            self.downloader.start()
        
    def parse_downloads(self, data):
        return data

    def update_progress(self, data):
        self.progress += len(data)
        if self.downloader.error:
            self.progress += 1 
        self.progress = min(self.progress, self.total)
        
    def process(self, block=False):
        if self._abort:
            return
        if not self.id_enumeration:
            self.emit('progress', 1.0, True, None)
            return
        if not self.downloader:
            self.download(block=block)
        if not block and self.downloader.is_alive():
            return True
        if self.downloader.error:
            i, id, e = self.downloader.error
            data = self.downloader.results[:i]
        else:
            data = self.downloader.results
        batch_results = self.parse_downloads(data)
        self.results.extend(batch_results)
        self.update_progress(data)
        finished = self.progress == self.total
        if batch_results:
            fraction = float(self.progress) / self.total
            self.emit('progress', fraction, finished, batch_results)
        if not finished:
            self.download()
        return not finished
    
    def abort(self):
        self._abort = True
        self.downloader.abort()

    def run(self):
        while self.process(block=True):
            pass
            
# Actions

class ComputeAll(Action):
    action_name = "compute-all"
    path = ['Computation', 'Compute all']
    tooltip = "Block until all background tasks have completed."
    
    @classmethod
    def applicable(cls, target, coord=None):
        cm = target.get_compute_manager()
        if not cm:
            return
        a = cls(target, coord)
        if not cm.computing():
            a.path = list(cls.path)
            a.path[-1] += ' (nothing to do)'
        return a
    
    def run(self):
        self.target.get_compute_manager().compute_all()
        
register_action(ComputeAll)

class AbortAllComputations(Action):
    action_name = "abort-all-computations"
    path = ['Computation', 'Abort all computations']
    tooltip = "Abort all running background tasks."
    
    @classmethod
    def applicable(cls, target, coord=None):
        cm = target.get_compute_manager()
        if not (cm and cm.computing()):
            return
        return cls(target, coord)
    
    def run(self):
        self.target.get_compute_manager().abort_all()
        
register_action(AbortAllComputations)