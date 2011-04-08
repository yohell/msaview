import cairo

from color import Color, Gradient

# Helpers

def get_view_extents(area_position, area_length, area_total_length, total_items):
    scale = float(area_total_length) / total_items
    first_item = int(total_items * float(area_position) / area_total_length)
    last_item = int(total_items * float(area_position + area_length) / area_total_length)
    items_in_view = min(last_item + 1, total_items) - first_item
    return first_item, items_in_view, scale


CAIRO_VECTOR_SURFACES = tuple(getattr(cairo, s) for s in ['PDFSurface', 'PSSurface', 'SVGSurface', 'Win32Printing'] if hasattr(cairo, s))

def vector_based(cr):
    return isinstance(cr.get_target(), CAIRO_VECTOR_SURFACES)

# Fills

def stripes(fg, bg, width, spacing, flip=False):
    size = width + spacing 
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    cr.rectangle(0, 0, size, size)
    cr.clip()
    cr.set_source_rgba(*bg)
    cr.fill()
    cr.set_source_rgba(*fg)
    cr.set_line_width(width)
    if flip:
        cr.move_to(0, -0.5 * size)
        cr.line_to(1.5 * size, size)
        cr.move_to(-0.5 * size, 0)
        cr.line_to(size, 1.5 * size)
    else:
        cr.move_to(-0.5 * size, size)
        cr.line_to(size, -0.5 * size)
        cr.move_to(0, 1.5 * size)
        cr.line_to(1.5*size, 0)
    cr.stroke()
    pattern = cairo.SurfacePattern(surf)
    pattern.set_extend(cairo.EXTEND_REPEAT)
    return pattern

def circles(fg, bg, radius):
    size = 2 * radius + 2
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    cr.rectangle(0, 0, size, size)
    cr.clip()
    cr.set_source_rgba(*bg)
    cr.fill()
    cr.set_source_rgba(*fg)
    import math
    cr.arc(size*0.5, size*0.5, radius, 0, 2 * math.pi)
    cr.close_path()
    cr.fill()
    pattern = cairo.SurfacePattern(surf)
    pattern.set_extend(cairo.EXTEND_REPEAT)
    return pattern

def chequers(fg, bg, width):
    size = 2 * width
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    cr.rectangle(0, 0, size, size)
    cr.clip()
    cr.set_source_rgba(*bg)
    cr.fill()
    cr.rectangle(0, 0, width, width)
    cr.rectangle(width, width, size, size)
    cr.set_source_rgba(*fg)
    cr.fill()
    pattern = cairo.SurfacePattern(surf)
    pattern.set_extend(cairo.EXTEND_REPEAT)
    return pattern

def lines(fg, bg, width):
    size = 2 * width
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    cr.rectangle(0, 0, size, size)
    cr.clip()
    cr.set_source_rgba(*bg)
    cr.fill()
    cr.rectangle(0, 0, size, width)
    cr.set_source_rgba(*fg)
    cr.fill()
    pattern = cairo.SurfacePattern(surf)
    pattern.set_extend(cairo.EXTEND_REPEAT)
    return pattern


# Plotting functions:

def tick_lines(cr, color, alpha, tick_height, tick_positions, item_size, area_x, area_width):
    """Draw tick lines.
    
    cr is assumed to be clipped (and rotated) and translated to 
    (msa 0, line top) before calling this function.
    
    """
    pixels = not vector_based(cr)
    cr.set_line_width(0.5)
    offset = 0
    if pixels:
        cr.set_line_width(1)
        offset = -0.5
    for tick in tick_positions:
        x = tick * item_size
        if pixels:
            x = round(x)
        if x < area_x:
            continue
        if x > area_x + area_width:
            break
        cr.move_to(x + offset, 0)
        cr.line_to(x + offset, tick_height)
    cr.set_source_rgba(*color.with_alpha(alpha).rgba)
    cr.stroke()
    
def tick_labels(cr, layout, color, alpha, tick_positions, item_size, area_x, area_width):
    """Draw tick labels.
    
    cr is assumed to be clipped (and rotated) and translated to 
    (msa 0, label top) before calling this function.
    
    """
    # The intricate return values from ...get_pixel_extents():
    #ink, logic = layout.get_line(0).get_pixel_extents()
    #ink_xbearing, ink_ybearing, ink_w, ink_h = ink
    #log_xbearing, log_ybearing, log_w, log_h = logic
    margin = 2
    cr.set_source_rgba(*color.with_alpha(alpha).rgba)
    for tick in tick_positions:
        if int(tick * item_size) < area_x:
            continue
        layout.set_text(str(tick))
        label_width = layout.get_line(0).get_pixel_extents()[1][2]
        x = int(tick * item_size) - label_width - margin
        if x > area_x + area_width:
            break
        cr.move_to(x, 0)
        cr.show_layout(layout)

def bar(cr, color, alpha, values, first_pos, n_pos, x_offset, total_width, total_height):
    gradient = isinstance(color, Gradient)
    length = len(values)
    for pos in range(first_pos, first_pos + n_pos):
        #x_start = int(round(float(pos) / length * total_width - x_offset))
        #x_stop = int(round(float(pos + 1) / length * total_width - x_offset))
        #x_stop = max(x_stop, x_start + 1)
        bar_height = int(round(total_height * values[pos])) 
        x_start = float(pos) / length * total_width - x_offset
        x_stop = float(pos + 1) / length * total_width - x_offset
        cr.rectangle(x_start, total_height - bar_height, x_stop - x_start, bar_height)
        if gradient:
            c = color.get_color_from_offset(values[pos])
            cr.set_source_rgba(*c.with_alpha(alpha).rgba)
            cr.fill()
    if color is None:
        return
    if not gradient:
        cr.set_source_rgba(*color.with_alpha(alpha).rgba)
        cr.fill()
    
def v_bar(cr, color, alpha, values, first_seq, n_seq, y_offset, total_width, total_height):
    gradient = isinstance(color, Gradient)
    length = len(values)
    for seq in range(first_seq, first_seq + n_seq):
        #y_start = int(round(float(seq) / length * total_height - y_offset))
        #y_stop = int(round(float(seq + 1) / length * total_height - y_offset))
        #y_stop = max(y_stop, y_start + 1)
        y_start = float(seq) / length * total_height - y_offset
        y_stop = float(seq + 1) / length * total_height - y_offset
        bar_width = int(round(total_width * values[seq])) 
        cr.rectangle(0, y_start, bar_width, y_stop - y_start)
        if gradient:
            c = color.get_color_from_offset(values[seq])
            cr.set_source_rgba(*c.with_alpha(alpha).rgba)
            cr.fill()
    if color is None:
        return
    if not gradient:
        cr.set_source_rgba(*color.with_alpha(alpha).rgba)
        cr.fill()
    
def quartile_guidelines(cr, width, x_offset, total_width, total_height):
    cr.save()
    cr.set_line_width(0.5)
    y = 0.25
    if not vector_based(cr):
        cr.set_line_width(1)
        y = 0.5
    # Top
    cr.move_to(-1, y)
    cr.line_to(width, y)
    cr.stroke()
    # Half
    cr.set_dash([2, 2], x_offset % 4)
    y = int(0.5 * total_height) - 0.5
    cr.move_to(-1, y)
    cr.line_to(width, y)
    cr.stroke()
    # Quartiles
    cr.set_dash([1, 1], x_offset % 2)
    for n in [.25, .75]:
        y = int(total_height * n) - 0.5
        cr.move_to(-1, y)
        cr.line_to(width, y)
    cr.stroke()
    cr.restore()

def v_quartile_guidelines(cr, height, y_offset, total_width, total_height):
    cr.save()
    cr.set_line_width(0.5)
    x = 0.25
    if not vector_based(cr):
        cr.set_line_width(1)
        x = 0.5
    # Left
    cr.move_to(x, -1)
    cr.line_to(x, height)
    cr.stroke()
    # Half
    cr.set_dash([2, 2], y_offset % 4)
    x = int(0.5 * total_width) - 0.5
    cr.move_to(x, -1)
    cr.line_to(x, height)
    cr.stroke()
    # Quartiles
    cr.set_dash([1, 1], y_offset % 2)
    for n in [.25, .75]:
        x = int(total_width * n) - 0.5
        cr.move_to(x, -1)
        cr.line_to(x, height)
    cr.stroke()
    cr.restore()
    
def scaled_image(cr, area, image, alpha):
    width = image.get_width()
    height = image.get_height()
    first_pos, x_offset = divmod(float(width * area.x) / area.total_width, 1)
    first_seq, y_offset = divmod(float(height * area.y) / area.total_height, 1)
    first_pos = int(first_pos)
    first_seq = int(first_seq)
    last_pos = int(width * float(area.x + area.width) / area.total_width)
    last_seq = int(height * float(area.y + area.height) / area.total_height)
    n_pos = min(last_pos - first_pos + 1, width)
    n_seq = min(last_seq - first_seq + 1, height)
    temp = cairo.ImageSurface(cairo.FORMAT_ARGB32, n_pos, n_seq)
    temp_cr = cairo.Context(temp)
    temp_cr.rectangle(0, 0, n_pos, n_seq)
    temp_cr.clip()
    temp_cr.translate(-first_pos, -first_seq)
    temp_cr.set_source_surface(image, 0, 0)
    temp_cr.paint_with_alpha(alpha)
    cr.rectangle(0, 0, area.width, area.height)
    cr.clip()
    cr.scale(area.total_width / float(width), area.total_height / float(height))
    cr.translate(-x_offset, -y_offset)
    pattern = cairo.SurfacePattern(temp)
    pattern.set_filter(cairo.FILTER_NEAREST)
    cr.set_source(pattern)
    cr.rectangle(0, 0, n_pos, n_seq)
    cr.fill()
    
def scaled_image_rectangles(cr, area, array, alpha):
    height, width = array.shape[:2]
    (first_pos, n_pos, xscale), (first_seq, n_seq, yscale) = area.item_extents(width, height)
    cr.rectangle(0, 0, area.width, area.height)
    cr.clip()
    cr.translate(-area.x, -area.y)
    for seq in range(first_seq, first_seq + n_seq):
        for pos in range(first_pos, first_pos + n_pos):
            b, g, r, a = array[seq,pos]/255.0
            cr.set_source_rgba(r, g, b, a * alpha)
            x = pos * xscale
            y = seq*yscale
            xstop = (pos + 1) * xscale
            ystop = (seq + 1) * yscale
            cr.rectangle(x, y, xscale, yscale)
            cr.fill()

def outlined_regions(cr, area, n_positions, n_sequences, features, linewidth, color, alpha, merged=False):
    first_pos, n_pos, x_scale = area.item_extents_for_axis(n_positions, 'width')
    first_seq, n_seq, y_scale = area.item_extents_for_axis(n_sequences, 'height')
    cr.save()
    cr.translate(-area.x, -area.y)
    cr.set_line_width(linewidth)
    cr.set_source_rgba(*color.rgba)
    def draw_outline(seq, region):
        x = int(region.start * x_scale)
        w = round((region.start + region.length) * x_scale) - x
        y = int(seq * y_scale)
        h = round((seq + 1) * y_scale) - y
        r = (x + linewidth/2.0, y + linewidth/2.0, w - linewidth, h - linewidth)
        if not ((region.start >= first_pos + n_pos) or (region.start + region.length < first_pos)):
            cr.rectangle(*r)
        return r
    for feature in features:
        if not (first_seq <= feature.sequence_index < first_seq + n_seq):
            continue
        if merged:
            draw_outline(feature.sequence_index, feature.mapping)
            continue
        previous = None
        for part in feature.mapping.parts:
            r = draw_outline(feature.sequence_index, part)
            if previous:
                midpoint = (previous[0] + previous[2] + r[0]) * 0.5 
                cr.move_to(previous[0] + previous[2], r[1] + 0.55 * r[3])
                cr.line_to(midpoint, r[1] + 0.75 * r[3])
                cr.line_to(r[0], r[1] + 0.55 * r[3])
            previous = r
        cr.stroke()
    cr.restore()