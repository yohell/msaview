__version__ = "0.9.0"

import gio
import gobject

from msaview import log
from msaview.color import ColorSetting
from msaview.action import (Action,
                            register_action)
from msaview.component import (Change,
                               prop)
from msaview.preset import (BoolSetting,
                            ComponentSetting,
                            FloatSetting,
                            FontSetting,
                            presets)
from msaview.plotting import (chequers,
                              get_view_extents,
                              vector_based,
                              v_bar)
from msaview.renderers import (Labeler,
                               integrate_ancestor_msa)
from msaview.selection import Region
from msaview.sequence_information import SequenceInformation

from msaview_plugin_biomart import (BiomartTask,
                                    BiomartQuery,
                                    BiomartResult)
from msaview_plugin_uniprot import (UniprotID,
                                    dbfetch_uniprot_xml_for_sequence)

presets.add_to_preset_path(__file__)

class EnsemblIDs(SequenceInformation):
    category = 'ensembl-ids'
    def __init__(self, sequence_index, sequence_id=None, organism=None, gene_id=None, transcript_id=None, protein_id=None):
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        self.organism = organism
        self.gene_id = gene_id
        self.transcript_id = transcript_id
        self.protein_id = protein_id
        
    @classmethod
    def from_uniprot_etree(cls, entry):
        if (entry and entry.root) is None:
            return
        sequence_index = entry.sequence_index
        sequence_id = entry.sequence_id
        for e in entry.root.findall('dbReference'):
            if e.attrib['type'] != 'Ensembl':
                continue
            transcript_id = e.attrib['id']
            for property in e.findall('property'):
                if property.attrib['type'] == 'protein sequence ID':
                    protein_id = property.attrib['value'] 
                if property.attrib['type'] == 'gene designation':
                    gene_id = property.attrib['value']
                if property.attrib['type'] == 'organism name':
                    organism = property.attrib['value']
            break 
        else:
            return cls(sequence_index, sequence_id)
        return cls(sequence_index, sequence_id, organism, gene_id, transcript_id, protein_id)
    
def get_populated_ensembl_ids_category(msa):
    ensembl_ids_category = msa.sequence_information.setdefault('ensembl-ids')
    new_entries = []
    for i, etree_entry in enumerate(msa.sequence_information.categories.get('uniprot-etree', [])):
        if ensembl_ids_category[i]:
            continue
        entry = EnsemblIDs.from_uniprot_etree(etree_entry)
        if entry:
            new_entries.append(entry)
    msa.sequence_information.add_information(new_entries)
    return ensembl_ids_category

class GeneLocation(SequenceInformation):
    category = 'gene-location'
    def __init__(self, sequence_index, sequence_id=None, chromosome=None, region=None, strand=None):    
        self.sequence_index = sequence_index
        self.sequence_id = sequence_id
        self.chromosome = chromosome
        self.region = region
        self.strand = strand

class EnsemblBiomartTask(BiomartTask):
    url = 'http://www.ensembl.org/biomart/martservice'
    @classmethod
    def get_dataset_name(cls, organism):
        words = organism.split()[:2]
        name = words[0][0] + words[1]
        return name.lower() + '_gene_ensembl'
    
    @classmethod
    def create_id_enumerations(cls, ensembl_ids_entries, id_type='gene'):
        enumerations = {}
        for entry in ensembl_ids_entries:
            id = getattr(entry, id_type + '_id', None)
            if not (entry and id and entry.organism):
                continue
            dataset = cls.get_dataset_name(entry.organism)
            enumerations.setdefault(dataset, []).append((entry.sequence_index, id))
        return enumerations.items()

    def handle_id_category_changed(self, sequence_information, change):
        if change.has_changed('ensembl-ids'):
            self.abort()
        
class GeneLocationTask(EnsemblBiomartTask):
    @classmethod
    def from_ensembl_ids_entries(cls, msa, entries):
        id_enumerations = cls.create_id_enumerations(entries)
        query = BiomartQuery()
        query.add_parameters(ensembl_gene_id='ids')
        query.add_attributes("ensembl_gene_id",
                             "chromosome_name",
                             "start_position",
                             "end_position",
                             "strand")
        return cls(msa, id_enumerations, query)

    def parse_downloads(self, data):
        biomart_result = BiomartResult.from_query(self.query, data[0])
        id_enumeration = self.id_enumeration[self.dataset_index][1]
        entries = []
        for row in biomart_result.iter_dict():
            for sequence_index, gene_id in id_enumeration[self.dataset_progress:self.dataset_progress+self.batch_size]:
                if row['ensembl_gene_id'] == gene_id:
                    start = int(row['start_position']) - 1
                    region = Region(start, int(row['end_position']) - start)
                    entry = GeneLocation(sequence_index, gene_id, row['chromosome_name'], region, int(row['strand']))
                    entries.append(entry)
        return entries

def commafy_integer(integer):
    s = str(integer)
    result = []
    start = len(s) % 3
    if start:
        result.append(s[:start])
    result.extend(s[i:i+3] for i in range(start, len(s), 3))
    return ','.join(result)

class GeneLocationRenderer(Labeler):
    __gproperties__ = dict(
        sequence_information = (gobject.TYPE_PYOBJECT,
            'sequence_information',
            'the msa to visualize',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.seq.gene_location'
    logger = log.get_logger(msaview_classname)
    
    def __init__(self):
        Labeler.__init__(self)
        self.propvalues['label_transforms'] = None #ABBREVIATE_KNOWN_ID_FORMATS
        self._data = tuple()

    sequence_information = prop('sequence_information')
    
    def __hash__(self):
        return hash((self.__class__, self._data, self.pango_context, self.color, self.font, self.transform_labels, self.label_transforms, self._label_size, self.alpha))
    
    def __eq__(self, other):
        if other is self:
            return True
        return (isinstance(other, self.__class__) and
                self._data == other._data and
                self.pango_context == other.pango_context and
                self.color == other.color and
                self.font == other.font and
                self.transform_labels == other.transform_labels and
                self.label_transforms == other.label_transforms and
                self.resize_seqview_to_fit == other.resize_seqview_to_fit and
                self._label_size == other._label_size and
                self.alpha == other.alpha)
         
    def do_set_property_sequence_information(self, pspec, sequence_information):
        if sequence_information == self.sequence_information:
            return
        self.update_change_handlers(sequence_information=sequence_information)
        self.propvalues.update(sequence_information=sequence_information)
        self.handle_sequence_information_change(sequence_information, Change())

    def handle_sequence_information_change(self, sequence_information, change):
        if not change.has_changed('gene-location'):
            return
        self._data = tuple(self.get_data() or [])
        self.update_label_size()

    def get_data(self):
        if not self.sequence_information.msa:
            return 
        entries = self.sequence_information.setdefault('gene-location')
        def format_gene_location(entry):
            if not entry:
                return ''
            return "%s[%+d] %sbp" % (entry.chromosome,
                                       entry.strand, 
                                       commafy_integer(entry.region.start))
        return [format_gene_location(e) for e in entries]

    def render(self, cr, area):
        if self._label_size is None:
            return
        detail = self.get_detail_size()
        if area.total_height >= detail[1]:
            return Labeler.render(self, cr, area)
        # If we don't have enough space to draw legible labels we can at least do a label sized shading. 
        values = [float(i)/area.total_width for i in self._label_widths]
        first_label, n_labels, yscale = get_view_extents(area.y, area.height, area.total_height, len(self.get_data()))
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip()
        cr.translate(-area.x + 1, 0)
        v_bar(cr, None, None, values, first_label, n_labels, area.y, area.total_width, area.total_height)
        if vector_based(cr):
            cr.set_source_rgba(.85, .85, .85, self.alpha)
        else:
            cr.set_source(chequers((.5, .5, .5, self.alpha), (0, 0, 0, 0), 1))
        cr.fill()

    def get_tooltip(self, coord):
        if not self.sequence_information:
            return
        entry = self.sequence_information.get_entry('gene-location', coord.sequence)
        if not entry:
            return
        template = "Gene=%s chromosome=%s strand=%+d location=%sbp length=%sbp"
        return template % (entry.sequence_id,
                           entry.chromosome,
                           entry.strand, 
                           commafy_integer(entry.region.start),
                           commafy_integer(entry.region.length))

    def integrate(self, ancestor, name=None):
        self.msaview_name = Labeler.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        self.sequence_information = msa.sequence_information
        return self.msaview_name 
        
        
class GeneLocationRendererSetting(ComponentSetting):
    component_class = GeneLocationRenderer
    setting_types = dict(alpha=FloatSetting,
                         color=ColorSetting,
                         font=FontSetting,
                         transform_labels=BoolSetting,
                         resize_seqview_to_fit=BoolSetting)

presets.register_component_defaults(GeneLocationRendererSetting)
    
class FindEnsemblIDsForUniprotSequences(Action):
    action_name = 'find-ensembl-ids'
    path = ['Import', 'Sequence information', 'Find Ensembl links']
    tooltip = 'Extract Ensembl links from already imported UniProtKB XML data.'
    
    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        etree_category = target.sequence_information.categories.get('uniprot-etree', [None])
        try:
            (e for e in etree_category if (e and e.root) is not None).next()
        except StopIteration:
            return
        return cls(target, coord)

    def run(self):
        ensembl_ids_category = self.target.sequence_information.setdefault('ensembl-ids')
        new_entries = []
        for i, etree_entry in enumerate(self.target.sequence_information.categories['uniprot-etree']):
            if ensembl_ids_category[i]:
                continue
            entry = EnsemblIDs.from_uniprot_etree(etree_entry)
            if entry:
                new_entries.append(entry)
        self.target.sequence_information.add_entries(new_entries)
        
register_action(FindEnsemblIDsForUniprotSequences)

class ImportEnsemblIDsForUniprotSequence(Action):
    action_name = 'import-ensembl-ids-for-sequence'
    path = ['Import', 'Sequence information', 'Download Ensembl links (single sequence)']
    tooltip = 'Download Ensembl links from UniProtKB XML data for the sequence.'
    
    url = 'http://www.uniprot.org/uniprot/' 

    @classmethod
    def applicable(cls, target, coord=None):
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        etree_entry = target.sequence_information.get_entry('uniprot-etree', coord.sequence)
        if etree_entry:
            if etree_entry.root is None:
                return
            return cls(target, coord)
        id_entry = target.sequence_information.get_entry('uniprot-id', coord.sequence)
        if not id_entry:
            id_entry = UniprotID.from_msa_sequence(target, coord.sequence)
        if not id_entry.sequence_id:
            return
        return cls(target, coord)

    def run(self):
        sequence_index = self.coord.sequence
        etree_category = self.target.sequence_information.setdefault('uniprot-etree')
        etree_entry = etree_category[sequence_index]
        if not etree_entry:
            id_category = self.target.sequence_information.setdefault('uniprot-id')
            id_entry = id_category[sequence_index]
            if not id_entry:
                id_entry = UniprotID.from_msa_sequence(self.target, self.coord.sequence)
                self.target.sequence_information.add_entries(id_entry)
            etree_entry = dbfetch_uniprot_xml_for_sequence(self.target, sequence_index)
            self.target.sequence_information.add_entries(etree_entry)
        ensembl_entry = EnsemblIDs.from_uniprot_etree(etree_entry)
        self.target.sequence_information.setdefault('ensembl-ids')
        self.target.sequence_information.add_entries(ensembl_entry)
        
register_action(ImportEnsemblIDsForUniprotSequence)

class ShowSequenceInEnsemblWebInterface(Action):
    action_name = 'show-sequence-in-ensembl-web-interface'
    path = ['Web interface', 'Ensembl', 'Show %s']
    tooltip = 'Show structure in the PDB web interface.'
    
    urls = dict(gene='http://www.ensembl.org/Homo_sapiens/Gene/Summary?g=%s',
                transcript='http://www.ensembl.org/Homo_sapiens/Transcript/Summary?t=%s',
                protein='http://www.ensembl.org/Homo_sapiens/Transcript/ProteinSummary?t=%s',
                location='http://www.ensembl.org/Homo_sapiens/Location/View?g=%s') 
    
    @classmethod
    def applicable(cls, target, coord=None):
        if not coord or coord.sequence is None:
            return
        if target.msaview_classname != 'data.msa':
            return
        entry = target.sequence_information.get_entry('ensembl-ids', coord.sequence)
        if not entry:
            return
        actions = []
        for name in ('location', 'gene', 'transcript', 'protein'):
            try:
                id = getattr(entry, name + '_id')
            except AttributeError:
                id = entry.gene_id
            if not id:
                continue
            action = cls(target, coord)
            action.path = list(cls.path)
            url_id = id
            if name == 'protein':
                url_id = entry.transcript_id
            if name == 'location':
                action.path[-1] = 'Show location for %s' % entry.gene_id
            else:
                action.path[-1] = 'Show %s %s' % (name, id)
            action.params['url'] = cls.urls[name] % url_id
            actions.append(action)
        if actions:
            return actions
    
    def run(self):
        gio.app_info_get_default_for_uri_scheme('http').launch_uris([self.params['url']])

register_action(ShowSequenceInEnsemblWebInterface)

class ImportEnsemblGeneLocations(Action):
    action_name = 'import-ensembl-gene-locations'
    path = ['Import', 'Sequence information', 'Ensembl gene locations']
    tooltip = 'Download gene locations from Ensembl biomart.'

    @classmethod
    def applicable(cls, target, coord=None):
        if target.msaview_classname != 'data.msa':
            return
        id_entries = target.sequence_information.categories.get('ensembl-ids', [])
        try:
            (True for e in id_entries if (e and e.gene_id and e.organism)).next()
        except StopIteration:
            return
        return cls(target, coord)
    
    def run(self):
        self.target.sequence_information.setdefault('gene-location')
        id_entries = self.target.sequence_information.categories['ensembl-ids']
        task = GeneLocationTask.from_ensembl_ids_entries(self.target, id_entries)
        task.connect('progress', lambda t, progress, finished, entries: self.target.sequence_information.add_entries(entries or []))
        self.target.sequence_information.connect('changed', task.handle_id_category_changed)
        m = self.target.find_ancestor('msaview')
        self.target.get_compute_manager().timeout_add(100, task)
        return task

register_action(ImportEnsemblGeneLocations)
