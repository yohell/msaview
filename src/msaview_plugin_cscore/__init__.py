__version__ = "0.9.0"

import os
import platform
import sys
import time

import cairo
import gobject
import numpy

from msaview import log
from msaview.color import (Color, 
                           ColorSetting,
                           Gradient, 
                           GradientSetting)
from msaview.component import (Change, 
                               Component,
                               prop)
from msaview.preset import (BoolSetting,
                            ComponentSetting,
                            FloatSetting,
                            FontSetting,
                            presets)
from msaview.options import GradientOption
from msaview.plotting import (bar,
                              quartile_guidelines,
                              scaled_image, 
                              scaled_image_rectangles, 
                              vector_based, 
                              v_bar, 
                              v_quartile_guidelines)
from msaview.renderers import (Labeler, 
                               PercentageTransform, 
                               Renderer, 
                               TransformList, 
                               integrate_ancestor_msa)

from msaview_plugin_scoring_matrix import get_matrix

module_logger = log.get_plugin_module_logger(__file__)

try:
    # Import extension module
    import _cscore
except:
    _cscore = None
    
presets.add_to_preset_path(__file__)

class CScore(Component):
    __gproperties__ = dict(
        msa = (
            gobject.TYPE_PYOBJECT,
            'msa',
            'the multiple sequence alignment to compute scores for',
            gobject.PARAM_READWRITE),
        cscores = (
            gobject.TYPE_PYOBJECT,
            'cscores for positions',
            'conservation scores for positions as a 1-dim numpy array of 0.0-1.0 numbers',
            gobject.PARAM_READABLE),
        divergences = (
            gobject.TYPE_PYOBJECT,
            'divergences',
            'normalized residue-to-centroid distances weighted by cscores and gap-penalized as a 2-dim numpy array of 0.0-1.0 numbers',
            gobject.PARAM_READABLE),
        sequence_cscores = (
            gobject.TYPE_PYOBJECT,
            'sequence cscores',
            '(1 - mean sequence divergence) as a 1-dim numpy array of 0.0-1.0 numbers',
            gobject.PARAM_READABLE),
        )

    job_size = 10

    msaview_classname = 'data.cscore'
    logger = log.get_logger(msaview_classname)
    
    def __init__(self):
        Component.__init__(self)
        self.scoring_matrix = get_matrix('gonnet250')
        self._worker = None
        self.divs = None
        
    cscores = prop('cscores', readonly=True)
    divergences = prop('divergences', readonly=True) 
    msa = prop('msa')
    sequence_cscores = prop('sequence_cscores', readonly=True) 

    def do_set_property_msa(self, pspec, msa):
        self.clear()
        self.update_change_handlers(msa=msa)
        self.propvalues['msa'] = msa
        self.update()

    def _reset_internals(self):
        if self._worker is not None:
            self.get_compute_manager().source_remove(self._worker)
        self._worker = None
        self._vectors = None
        self._centroids = None
        self._distances = None
        self._cscores = None
        self._divergences = None
        self._sequence_cscores = None
    
    def _update_cscores_worker_function(self):
        if not self.msa:
            return
        if not self._progress:
            iSeq = len(self.msa.sequences)
            iPos = len(self.msa)
            iRes = len(self.scoring_matrix)
            self._vectors = numpy.empty((iSeq, iPos, iRes))
            self._known = numpy.zeros(iPos)
            self._centroids = numpy.zeros((iPos, iRes))
            self._distances = numpy.empty((iSeq, iPos))
            self._cscores = numpy.empty(iPos)
            self._divergences = numpy.empty((iSeq, iPos))
            self._sequence_cscores = numpy.zeros(iSeq)
            self._progress = 0
        stop = min(self._progress + self.job_size, len(self.msa))
        if self._progress < stop:
            self._calculate_scores(self._progress, stop)
        self._progress = min(self._progress + self.job_size, len(self.msa))
        if self._progress < len(self.msa):
            # We're not done. Return True to be called again when there's time available.
            return True
        self.propvalues['cscores'] = self._cscores.round(5)
        self.propvalues['divergences'] = self._divergences.round(5)
        self.propvalues['sequence_cscores'] = self._sequence_cscores.round(5)
        self.emit('changed', Change('cscores'))

    def new_calculate_scores(self, cscores, divergences_t, conformances):
        self.divs = numpy.empty((len(self.msa), 256), float)
        column_uarray = numpy.frombuffer(self.msa.column_array.data, numpy.uint8)
        column_uarray.shape = self.msa.column_array.shape
        aas = self.scoring_matrix.residues()
        gaps = numpy.zeros(256, bool)
        gaps[[ord(aa) for aa in self.msa.gapchars]] = True
        indices = numpy.zeros(256, int)
        indices[:] = -1
        vector_length = len(self.scoring_matrix)
        indices[[ord(aa) for aa in aas]] = range(vector_length)
        scores = self.scoring_matrix.scores
        vectors = numpy.empty(scores.shape, float)
        diff = numpy.empty(vector_length, float)
        distance_sums = numpy.empty(vector_length, float)
        centroid = numpy.empty(vector_length, float)
        divs = numpy.empty(256, float)
        halfmax = self.scoring_matrix.max_distance / 2
        N = float(len(self.msa.sequences))
        N_1 = N - 1
        for pos in range(0, len(self.msa)):
            # Calculating counts, vectors and centroid.
            vectors[:] = 0 
            distance_sums[:] = 0 
            divs[:] = 0
            known = 0
            unknown = 0
            gapped = 0
            ungapped = 0
            counts = numpy.bincount(column_uarray[pos])
            for i in range(counts.size):
                count = counts[i]
                if count == 0:
                    continue
                index = indices[i]
                if index == -1:
                    unknown += count
                    if gaps[i]:
                        gapped += count
                    else:
                        ungapped += count
                    continue
                known += count
                ungapped += count
                vectors[index] = count * scores[index]
            if not known:
                cscore = 0
                cscores[pos] = cscore
            else:
                centroid[:] = vectors.sum(0) / known
                # Calculating distance_sums and cscore.
                for i in range(counts.size):
                    count = counts[i]
                    if count == 0:
                        continue
                    index = indices[i]
                    if index == -1:
                        continue
                    diff[:] = vectors[index] - count * centroid
                    distance_sums[index] = numpy.linalg.norm(diff)
                _cscore = 1 - sum(distance_sums) / halfmax / N - unknown / N_1
                cscore = max(min(_cscore, 1), 0)
                cscores[pos] = cscore
            # Calculating divergences and adding to conformances
            divs[:] = max(min(cscore + unknown / N_1, 1), 0)
            divs[[ord(aa) for aa in self.msa.gapchars]] = cscore
            for i in range(counts.size):
                count = counts[i]
                if count == 0:
                    continue
                index = indices[i]
                if index == -1:
                    continue
                # denominator is multiplied by count because distance_sums already are.
                # denominator is multiplied by 2 because we really want to divide by maxdist.
                div = cscore * distance_sums[index] / (2 * halfmax * count) + unknown / N_1
                divs[i] = max(min(div, 1), 0)
            self.divs[pos] = divs
            divergences_t[pos] = numpy.take(divs, column_uarray[pos])
            conformances += divergences_t[pos]
            
        #divergences = numpy.frombuffer(divergences_t.T.tostring(), float)  
        #divergences.shape = self.msa.sequence_array.shape  
            
    @log.trace
    def old_update(self):
        self._progress = 0
        if not (self.msa):
            return
        old = 'old' in os.environ.get('MSAVIEW_CSCORE_MODE', 'new')
        if old or not _cscore:
            self._worker = self.get_compute_manager().idle_add(self._update_cscores_worker_function)
            return
        self.logger.debug("calculating cscores, new style.")
        t = time.time()
        cscores = numpy.empty(len(self.msa), float)
        tmp_divergences = numpy.empty(self.msa.column_array.shape, float)
        conformances = numpy.zeros(len(self.msa.sequences), float)
        for i in range(len(self.msa)):
            _cscore.process_column(cscores, tmp_divergences, conformances, self.msa.column_array, i)
        conformances = 1 - conformances / len(self.msa)
        self.logger.debug("done in %.3fs.", time.time() - t)
        self._progress = len(self.msa)
        divergences = numpy.frombuffer(tmp_divergences.T.tostring(), dtype=float)
        divergences.shape = self.msa.sequence_array.shape
        self.propvalues.update(cscores=cscores, 
                               divergences=divergences, 
                               sequence_cscores=conformances)
        self.emit('changed', Change('cscores'))

    @log.trace
    def update(self):
        self._progress = 0
        if not (self.msa):
            return
        cscores = numpy.empty(len(self.msa), float)
        divergences_t = numpy.empty(self.msa.column_array.shape, float)
        conformances = numpy.zeros(len(self.msa.sequences), float)
        if False:#_cscore:
            for i in range(len(self.msa)):
                _cscore.process_column(cscores, divergences_t, conformances, self.msa.column_array, i)
        else:
            self.new_calculate_scores(cscores, divergences_t, conformances)
        conformances = 1 - conformances / len(self.msa)
        self._progress = len(self.msa)
        divergences = numpy.frombuffer(divergences_t.T.tostring(), dtype=float)
        divergences.shape = self.msa.sequence_array.shape
        self.propvalues.update(cscores=cscores, 
                               divergences=divergences, 
                               sequence_cscores=conformances)
        self.emit('changed', Change('cscores'))
        
    def clear(self):
        self._reset_internals()
        self.propvalues['cscores'] = None
        self.propvalues['divergences'] = None
        self.propvalues['sequence_cscores'] = None
        self.emit('changed', Change('cscores'))

    def handle_msa_change(self, msa, change):
        if change.has_changed('sequences'):
            self.clear()
            self.update()

    def _calculate_scores(self, start=None, stop=None):
        if start is None:
            start = 0
        if stop is None:
            stop = len(self.msa)
        halfmax = self.scoring_matrix.max_distance / 2
        N = len(self.msa.sequences)
        def bound(a, lower=None, upper=None):
            conditions = []
            choices = []
            if lower is not None:
                conditions.append(a < lower)
                choices.append(lower)
            if upper is not None:
                conditions.append(a > upper)
                choices.append(upper)
            return numpy.select(conditions, choices, default=a)
        for pos in range(start, stop):
            for seq, sequence in enumerate(self.msa.sequences):
                letter = sequence[pos] if pos < len(sequence) else '-'
                r = self.scoring_matrix.residue_index.get(letter) if letter else None
                if r is not None:
                    vector = self.scoring_matrix.scores[r]
                    self._vectors[seq,pos,:] = vector
                    self._centroids[pos] += vector
                    self._known[pos] += 1
                else:
                    self._vectors[seq,pos,:] = -10 * halfmax # Arbitrary large negative vector.
            if self._known[pos]:
                self._centroids[pos] /= float(self._known[pos])
            else:
                self._centroids[pos] = 10 * halfmax # Arbitrary large positive vector.
        tmp_distances = numpy.apply_along_axis(numpy.linalg.norm, 2, self._centroids[start:stop] - self._vectors[:, start:stop])
        self.logger.warning('improperly bounding distances.')
        self._distances[:, start:stop] = bound(tmp_distances, upper=halfmax)
        tmp_penalties = halfmax * (N - self._known[start:stop]) * (N / float(N-1) - 1)
        tmp_cscores = 1 - (self._distances[:, start:stop].sum(0) + tmp_penalties) / N / halfmax
        self._cscores[start:stop] = bound(tmp_cscores, lower=0, upper=1)

        tmp_conformity = 1 - self._distances[:,start:stop] * self._cscores[start:stop] / halfmax 
        tmp_conformity -= self.msa.ungapped[:,start:stop] * (N - self._known[start:stop]) / (N - 1)
        self._divergences[:,start:stop] = 1 - bound(tmp_conformity, lower=0, upper=1)
        self._sequence_cscores += tmp_conformity.sum(1) / len(self.msa)
        
    def integrate(self, ancestor, name=None):
        msa = integrate_ancestor_msa(self, ancestor)
        self.msaview_name = Component.integrate(self, msa, name)
        self.msa = msa
        return self.msaview_name

class CScoreSetting(ComponentSetting):
    component_class = CScore

presets.register_component_defaults(CScoreSetting)

presets.add_builtin('gradient:cscore_default', 
    Gradient.from_colorstops((0.0, presets.get_value('color:clustalx_red')), 
                             (1.0, presets.get_value('color:clustalx_yellow')),
                             (1.0, Color.from_str("#8ae3d4850000"))))

class CScoreRenderer(Renderer):
    __gproperties__ = dict(
        gradient = (
            gobject.TYPE_PYOBJECT,
            'gradient',
            'the colors for different bar heights in the plot',
            gobject.PARAM_READWRITE),
        cscore = (
            gobject.TYPE_PYOBJECT,
            'cscore',
            'the component that computes the cscores',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.pos.cscore'
        
    propdefaults = dict(alpha=1.0,
                        gradient=presets.get_setting('gradient:cscore_default'))

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and 
                (other.cscore.cscores == self.cscore.cscores and numpy.ones((1, 1))).all() and
                other.gradient == self.gradient)
        
    def __hash__(self):
        cscore_hash = None
        if self.cscore is not None and self.cscore.cscores is not None:
            step = max(len(self.cscore.cscores)/10, 1)
            sample = self.cscore.cscores[None:None:step]
            cscore_hash = reduce(lambda h, v: (h << 2) ^ hash(v), sample, 0)
        return hash((self.__class__, cscore_hash, self.gradient, self.alpha))

    gradient = prop('gradient') 
    cscore = prop('cscore') 

    def do_set_property_gradient(self, pspec, value):
        if value != self.gradient:
            self.propvalues['gradient'] = value
            self.emit('changed', Change('visualization'))
        
    def do_set_property_cscore(self, pspec, value):
        if value != self.cscore:
            self.update_change_handlers(cscore=value)
            self.propvalues['cscore'] = value
            self.handle_cscore_change(value, Change())

    def handle_cscore_change(self, cscore, change):
        if change.has_changed('cscores'):
            self.emit('changed', Change('visualization'))

    def render(self, cr, area):
        if self.cscore is None or self.cscore.cscores is None:
            return
        width = len(self.cscore.cscores)
        first_pos, x_offset = divmod(float(width * area.x) / area.total_width, 1)
        first_pos = int(first_pos)
        last_pos = min(int(width * float(area.x + area.width) / area.total_width), width - 1)
        n_pos = min(last_pos - first_pos + 1, width)
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip()
        cr.translate(0, -area.y)
        # Guide lines
        cr.set_source_rgba(*Color(215, 215, 215, self.alpha).rgba)
        quartile_guidelines(cr, area.width, area.x, area.total_width, area.total_height)
        # Bar plot
        bar(cr, self.gradient, self.alpha, self.cscore.cscores, first_pos, n_pos, area.x, area.total_width, area.total_height)
        # Bottom line
        cr.set_source_rgba(.7, .7, .7, self.alpha)
        cr.set_dash([])
        cr.set_line_width(0.5)
        offset = -0.25
        if not vector_based(cr):
            cr.set_line_width(1)
            offset = -0.5
        y = area.total_height + offset
        cr.move_to(-1, y)
        cr.line_to(area.width, y)
        cr.stroke()
        
    def get_detail_size(self):
        if self.cscore.cscores is not None:
            return len(self.cscore.cscores), 0
        return 0, 0

    def get_options(self):
        return Renderer.get_options(self) + [GradientOption(self, 'gradient')]

    def integrate(self, ancestor, name=None):
        self.msaview_name = Renderer.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        cscore = msa.find_descendant('data.cscore')
        if cscore is None:
            cscore = msa.integrate_descendant('data.cscore')
        self.cscore = cscore
        return self.msaview_name
    
class CScoreRendererSetting(ComponentSetting):
    component_class = CScoreRenderer
    setting_types = dict(alpha=FloatSetting,
                         gradient=GradientSetting)

presets.register_component_defaults(CScoreRendererSetting)

presets.add_builtin('gradient:cscore_residue_divergences', 
    Gradient.from_colorstops((0.5, presets.get_value('color:clustalx_red').with_alpha(0)),
                             (1, presets.get_value('color:clustalx_red')))) 

class DivergenceRenderer(Renderer):
    __gproperties__ = dict(
        gradient = (
            gobject.TYPE_PYOBJECT,
            'gradient',
            'how to colorize residue divergences',
            gobject.PARAM_READWRITE),
        cscore = (
            gobject.TYPE_PYOBJECT,
            'cscores',
            'the component that computes the residue divergences',
            gobject.PARAM_READWRITE),
        image = (
            gobject.TYPE_PYOBJECT,
            'image',
            'colors for the individual cells',
            gobject.PARAM_READWRITE)
        )
    
    msaview_classname='renderer.msa.cscore'
    logger = log.get_logger(msaview_classname)
    propdefaults = dict(gradient=presets.get_setting('gradient:cscore_residue_divergences'))

    def __init__(self):
        Renderer.__init__(self)
        self.array = None

    gradient = prop('gradient') 
    cscore = prop('cscore') 
    image = prop('image') 
    
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and 
                other.cscore.divergences == self.cscore.divergences and
                other.gradient == self.gradient)
        
    def __hash__(self):
        div_hash = None
        if self.cscore is not None and self.cscore.cscores is not None:
            step = max((self.cscore.divergences.shape[0] * self.cscore.divergences.shape[1])/10, 1)
            sample = self.cscore.divergences.flat[None:None:step]
            div_hash = reduce(lambda h, v: (h << 2) ^ hash(v), sample, 0)
        return hash((self.__class__, div_hash, self.gradient, self.alpha))

    def do_set_property_gradient(self, pspec, value):
        if value != self.gradient:
            self.propvalues['gradient'] = value
            self.image = self.colorize(self.cscore.divergences)
        
    def do_set_property_cscore(self, pspec, value):
        if value != self.cscore:
            self.update_change_handlers(cscore=value)
            self.propvalues['cscore'] = value
            self.handle_cscore_change(value, Change())
        
    def do_set_property_image(self, pspec, value):
        if value != self.image:
            self.propvalues['image'] = value
            if value is not None:
                self.array = numpy.frombuffer(value.get_data(), numpy.uint8)
                self.array.shape = (value.get_height(), value.get_width(), -1)
            else:
                self.array = None
            self.emit('changed', Change('visualization'))
        
    def handle_cscore_change(self, cscore, change):
        if change.has_changed('cscores'):
            if self.cscore.divergences is None:
                self.image = None
            else:
                self.image = self.colorize(self.cscore.divergences)

    @log.trace
    def colorize(self, divergences):
        if divergences is None:
            return
        image = cairo.ImageSurface(cairo.FORMAT_ARGB32, divergences.shape[1], divergences.shape[0])
        image.flush()
        if False: #_cscore:
            arr = numpy.frombuffer(image.get_data(), dtype=numpy.uint8)
            arr.shape = (divergences.shape[0], divergences.shape[1], -1)
            _cscore.divergences_renderer_colorize(arr, divergences, self.gradient)
            image.mark_dirty()
            return image
        column_array = self.cscore.msa.column_array
        arr = numpy.empty(column_array.shape + (4,), numpy.uint8)
        colormap = numpy.empty((256, 4), numpy.uint8)
        lookup = self.gradient.get_array_from_offset
        divs = self.cscore.divs
        for pos in range(arr.shape[0]):
            unknown = divs[pos, 0]
            colormap[:] = self.gradient.get_array_from_offset(unknown)
            for i in numpy.nonzero(divs[pos] != unknown)[0]:
                colormap[i] = lookup(divs[pos, i]) 
            arr[pos] = colormap[column_array[pos]]
        image = cairo.ImageSurface(cairo.FORMAT_ARGB32, column_array.shape[0], column_array.shape[1])
        b = numpy.frombuffer(arr.data, numpy.int32)
        b.shape = arr.shape[:-1]
        image.get_data()[:] = b.T.tostring()
        image.mark_dirty()
        return image

    def render(self, cr, area):
        if self.array is None:
            return
        if vector_based(cr):
            scaled_image_rectangles(cr, area, self.array, self.alpha)
        else:
            scaled_image(cr, area, self.image, self.alpha)

    def get_options(self):
        return Renderer.get_options(self) + [GradientOption(self)]

    def integrate(self, ancestor, name=None):
        self.msaview_name = Renderer.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        cscore = msa.find_descendant('data.cscore')
        if cscore is None:
            cscore = msa.integrate_descendant('data.cscore')
        self.cscore = cscore
        return self.msaview_name

class CScoreDivergenceRendererSetting(ComponentSetting):
    component_class = DivergenceRenderer
    setting_types = dict(alpha=FloatSetting,
                         gradient=GradientSetting)

presets.register_component_defaults(CScoreDivergenceRendererSetting)

presets.add_builtin('gradient:seq_cscore', 
    Gradient.from_colorstops((0.6, presets.get_value('color:clustalx_red')), 
                             (0.9, presets.get_value('color:clustalx_yellow'))))

class SequenceConformancesRenderer(Renderer):
    __gproperties__ = dict(
        gradient = (
            gobject.TYPE_PYOBJECT,
            'gradient',
            'the colors for different bar widths in the plot',
            gobject.PARAM_READWRITE),
        cscore = (
            gobject.TYPE_PYOBJECT,
            'cscore',
            'the component that computes the cscores',
            gobject.PARAM_READWRITE))
    
    msaview_classname = 'renderer.seq.cscore'
    
    propdefaults = dict(alpha=1.0,
                        gradient=presets.get_setting('gradient:seq_cscore'))
    
    def __eq__(self, other):
        return (isinstance(other, self.__class__) and 
                other.cscore.sequence_cscores == self.cscore.sequence_cscores and
                other.gradient == self.gradient)
        
    def __hash__(self):
        div_hash = None
        if self.cscore is not None and self.cscore.cscores is not None:
            step = max(len(self.cscore.sequence_cscores)/10, 1)
            sample = self.cscore.sequence_cscores[None:None:step]
            div_hash = reduce(lambda h, v: (h << 2) ^ hash(v), sample, 0)
        return hash((self.__class__, div_hash, self.gradient, self.alpha))

    gradient = prop('gradient') 
    cscore = prop('cscore') 

    def do_set_property_gradient(self, pspec, value):
        if value != self.gradient:
            self.propvalues['gradient'] = value
            self.emit('changed', Change('visualization'))
        
    def do_set_property_cscore(self, pspec, value):
        if value != self.cscore:
            self.update_change_handlers(cscore=value)
            self.propvalues['cscore'] = value
            self.handle_cscore_change(value, Change())

    def handle_cscore_change(self, cscore, change):
        if change.has_changed('cscores'):
            self.emit('changed', Change('visualization'))

    def render(self, cr, area):
        if self.cscore is None or self.cscore.sequence_cscores is None:
            return
        height = len(self.cscore.sequence_cscores)
        first_seq, y_offset = divmod(float(height * area.y) / area.total_height, 1)
        first_seq = int(first_seq)
        last_seq = min(int(height * float(area.y + area.height) / area.total_height), height - 1)
        n_seq = min(last_seq - first_seq + 1, height)
        cr.rectangle(0, 0, area.width, area.height)
        cr.clip()
        cr.translate(-area.x, 0)
        # Guide lines
        cr.set_source_rgba(*Color(215, 215, 215, self.alpha).rgba)
        v_quartile_guidelines(cr, area.height, area.y, area.total_width, area.total_height)
        # Bar plot
        v_bar(cr, self.gradient, self.alpha, self.cscore.sequence_cscores, first_seq, n_seq, area.y, area.total_width, area.total_height)
        # Bottom line
        cr.set_source_rgba(.7, .7, .7, self.alpha)
        cr.set_dash([])
        cr.set_line_width(0.5)
        x = 0.25
        if not vector_based(cr):
            cr.set_line_width(1)
            x = 0.5
        cr.move_to(x, -1)
        cr.line_to(x, area.height)
        cr.stroke()
        
    def get_detail_size(self):
        if self.cscore.sequence_cscores is not None:
            return 0, len(self.cscore.sequence_cscores)
        return 0, 0

    def get_options(self):
        return Renderer.get_options(self) + [GradientOption(self, 'gradient')]

    def integrate(self, ancestor, name=None):
        self.msaview_name = Renderer.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        cscore = msa.find_descendant('data.cscore')
        if cscore is None:
            cscore = msa.integrate_descendant('data.cscore')
        self.cscore = cscore
        return self.msaview_name

class SequenceConformancesRendererSetting(ComponentSetting):
    component_class = SequenceConformancesRenderer
    setting_types = dict(alpha=FloatSetting,
                         gradient=GradientSetting)

presets.register_component_defaults(SequenceConformancesRendererSetting)

class SequenceConformancesNumbers(Labeler):
    __gproperties__ = dict(
        cscore = (
            gobject.TYPE_PYOBJECT,
            'cscore',
            'the component that computes the cscores',
            gobject.PARAM_READWRITE))

    msaview_classname = 'renderer.seq.cscore_numbers'
    logger = log.get_logger(msaview_classname)
    
    propdefaults = dict(Labeler.propdefaults, 
                        transform_labels=True)
    
    def __init__(self, pango_context=None):
        Labeler.__init__(self)
        self.label_transforms = TransformList([PercentageTransform('percentages', '%d')])

    cscore = prop('cscore')
    
    def do_set_property_cscore(self, pspec, value):
        if value != self.cscore:
            self.propvalues['cscore'] = value
            self.update_change_handlers(cscore=value)
            self.handle_cscore_change(value, Change())
    
    def handle_cscore_change(self, cscore, change):
        if change.has_changed('cscores'):
            self.update_label_size()
            self.emit('changed', Change('visualization'))
            
    def get_data(self):
        if self.cscore:
            return self.cscore.sequence_cscores
    
    def integrate(self, ancestor, name=None):
        self.msaview_name = Renderer.integrate(self, ancestor, name)
        msa = integrate_ancestor_msa(self, ancestor)
        cscore = msa.find_descendant('data.cscore')
        if cscore is None:
            cscore = msa.integrate_descendant('data.cscore')
        self.cscore = cscore
        return self.msaview_name

class SequenceConformancesNumbersSetting(ComponentSetting):
    component_class = SequenceConformancesNumbers
    setting_types = dict(alpha=FloatSetting,
                         color=ColorSetting,
                         font=FontSetting,
                         transform_labels=BoolSetting,
                         resize_seqview_to_fit=BoolSetting)

presets.register_component_defaults(SequenceConformancesNumbersSetting)
