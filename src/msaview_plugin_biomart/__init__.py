"""MSAView - Biomart support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides support for querying and retrieving data from Biomarts. 
 
If you have problems with this package, please contact the author.

Copyright
=========
 
The MIT License

Copyright (c) 2011 Joel Hedlund.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

__version__ = "0.9.0"

import urllib
import xml.etree.ElementTree as etree

from msaview.computation import (DownloadTask)

class BiomartQuery(object):
    url = None
    docinfo = '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE Query>'

    def __init__(self, root=None):
        if root is None:
            root = etree.Element('Query', dict(formatter='TSV', header='0', count="", uniqueRows='1'))
        self.root = root
        dataset = root.find('Dataset')
        if dataset is None:
            dataset = etree.SubElement(root, 'Dataset')
            #dataset.attrib['interface'] = 'default'
        self.dataset = dataset

    unique_rows = property(lambda s: bool(int(s.root.attrib['uniqueRows'])),
                           lambda s, v: s.root.attrib.setdefault('uniqueRows', str(int(bool(v)))))
        
    @classmethod
    def create_query(cls, dataset, attributes, parameters=None, filters=None):
        q = cls()
        q.set_dataset(dataset)
        if parameters:
            q.set_parameters(parameters)
        if filters:
            q.set_filters(filters)
        q.set_attributes(attributes)

    def set_dataset(self, name):
        self.dataset.attrib['name'] = name

    def add_filter(self, name, value):
        etree.SubElement(self.dataset, 'Filter', dict(name=name, value=str(value)))
        
    def add_filters(self, filters=None, **kw):
        if filters is not None:
            kw.update(filters)
        for name, value in kw.items():
            self.add_filter(name, value)
            
    def add_parameter(self, name, alias=None):
        if alias is None:
            alias = name
        value = '%%(%s)s' % alias
        self.add_filter(name, value)
            
    def add_parameters(self, *names, **kw):
        if names and isinstance(names[0], (list, tuple)):
            kw.update((name, name) for name in names[0])
            names = names[1:]
        kw.update((name, name) for name in names)
        for name, alias in kw.items():
            self.add_parameter(name, alias)

    def get_parameter_names(self):
        names = []
        for e in self.dataset.findall('Filter'):
            value = e.attrib['value']
            if value.startswith("%(") and value.endswith(")s"):
                names.append(value[2:-2])
        return names
    
    def add_attribute(self, name):
        etree.SubElement(self.dataset, 'Attribute', dict(name=name))
        
    def add_attributes(self, names, *args):
        if isinstance(names, str):
            names = [names]
        args = names + list(args)
        for name in args:
            self.add_attribute(name)
        
    def get_attribute_names(self):
        names = []
        for e in self.dataset.findall('Attribute'):
            names.append(e.attrib['name'])
        return names

    def to_xml(self, parameters=None, **kw):
        if parameters is not None:
            kw.update(parameters)
        if not kw:
            return self.docinfo + etree.tostring(self.root)
        return self.docinfo + etree.tostring(self.root) % kw
    
class BiomartResult(object):
    def __init__(self, attribute_names=None, rows=None):
        if attribute_names is None:
            attribute_names = []
        self.attribute_names = attribute_names
        if rows is None:
            rows = []
        self.rows = rows
       
    @classmethod 
    def from_query(cls, query, results=None):
        o = cls(query.get_attribute_names())
        if results is not None:
            o.parse_tsv(results)
        return o
    
    def parse_tsv(self, text):
        if isinstance(text, str):
            text = text.splitlines()
        for line in text:
            line = line.strip()
            if not line:
                continue
            row = line.split('\t')
            assert len(row) == len(self.attribute_names)
            self.rows.append(row)

    def iter_dict(self):
        for row in self.rows:
            yield dict(zip(self.attribute_names, row))

class BiomartTask(DownloadTask):
    url = None
    batch_size = 100

    def __init__(self, msa=None, id_enumeration=None, query=None, batch_size=None, url=None):
        DownloadTask.__init__(self, msa, id_enumeration, batch_size, url)
        self.query = query
        self.total = sum(len(items) for dataset, items in id_enumeration)
        self.dataset_index = 0
        self.dataset_progress = 0

    def get_urls(self):
        dataset, id_enumeration = self.id_enumeration[self.dataset_index]
        ids = [id for i, id in id_enumeration[self.dataset_progress:self.dataset_progress+self.batch_size]]
        self.query.set_dataset(dataset)
        xml = self.query.to_xml(ids=','.join(ids))
        post_data = urllib.urlencode(dict(query=xml))
        return [(self.url, post_data)]
        
    def parse_downloads(self, data):
        return [BiomartResult.from_query(self.query, data[0])]
    
    def update_progress(self, data):
        dataset, id_enumeration = self.id_enumeration[self.dataset_index]
        processed = min(self.batch_size, len(id_enumeration) - self.dataset_progress)
        self.progress += processed
        self.dataset_progress += processed
        if self.dataset_progress >= len(id_enumeration):
            self.dataset_index += 1
            self.dataset_progress = 0
            
