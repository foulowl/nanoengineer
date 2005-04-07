# Copyright (c) 2004 Nanorex, Inc.  All rights reserved.
"""
shape.py

Handle the freehand curves for selection and cookie-cutting

$Id$
"""
__author__ = "Josh"

from Numeric import array, zeros, logical_or

from VQT import *
from OpenGL.GL import glNewList, glEndList, glCallList, glGenLists
from OpenGL.GL import GL_COMPILE_AND_EXECUTE

from drawer import *
from constants import *

from debug import print_compact_traceback
import platform 

## color = [0.22, 0.35, 0.18, 1.0] # bruce 041214 thinks this is unused

class BBox:
    """ implement a bounding box in 3-space
    BBox(PointList)
    BBox(point1, point2)
    BBox(2dpointpair, 3dx&y, slab)
    data is stored hi, lo so we can use subtract.reduce
    """
    def __init__(self, point1=None, point2=None, slab = None):
        if slab:
            # convert from a 2d box and axes
            x=dot(A(point1),A(point2))
            dx = subtract.reduce(x)
            oc=x[1]+V(point2[0]*dot(dx,point2[0]),point2[1]*dot(dx,point2[1]))
            sq1 = cat(x,oc) + slab.normal*dot(slab.point, slab.normal)
            sq1 = cat(sq1, sq1+slab.thickness*slab.normal)
            self.data = V(maximum.reduce(sq1), minimum.reduce(sq1))
        elif point2:
            # just 2 3d points
            self.data = V(maximum(point1, point2),minimum(point1, point2))
        elif point1:
            # list of points
            self.data = V(maximum.reduce(point1) + 1.8, minimum.reduce(point1) - 1.8)
        else:
            # a null bbox
            self.data = None
        
            
            
    def add(self, point):
        vl = cat(self.data, point)
        self.data = V(maximum.reduce(vl), minimum.reduce(vl))

    def merge(self, bbox):
        if self.data and bbox.data: self.add(bbox.data)
        else: self.data = bbox.data

    def draw(self):
        if self.data:
            drawwirebox(black,add.reduce(self.data)/2,
                        subtract.reduce(self.data)/2)

    def center(self):
        if self.data: return add.reduce(self.data)/2.0
        else: return V(0,0,0)

    def isin(self, pt):
        return (minimum(pt,self.data[1]) == self.data[1] and
                maximum(pt,self.data[0]) == self.data[0])

    def scale(self):
        if not self.data: return 10.0
        #x=1.2*maximum.reduce(subtract.reduce(self.data))
        dd = 0.5*subtract.reduce(self.data)
        x = sqrt(dd[0]*dd[0] + dd[1]*dd[1] + dd[2]*dd[2])
        #return max(x, 2.0)
        return x

    def copy(self, offset=None):
        if offset: return BBox(self.data[0]+offset, self.data[1]+offset)
        return BBox(self.data[0], self.data[1])


############################
#         Slab             #
############################


class Slab:
    """ defines a slab in space which can tell you if a point is in the slab
    """
    def __init__(self, point, normal, thickness):
        self.point = point
        self.normal = norm(normal)
        self.thickness = thickness

    def isin(self, point):
        d = dot(point-self.point, self.normal)
        return d>=0 and d<= self.thickness

    def __str__(self):
        return '<slab of '+`self.thickness`+' at '+`self.point`+'>'


def fill(mat,p,dir):
    """ Fill a curve drawn in matrix mat in 1's on 0's with 1's.
    p is V(i,j) of a point to fill from. dir is 1 or -1 for the
    standard recursive fill algorithm
    """
    if mat[p]: return
    up = dn = 0
    o1 = array([1,0])
    od = array([0, dir])
    while not mat[p-od]: p -= od
    while not mat[p]:
        mat[p] = 1
        if mat[p-o1]:
            if up:
                fill(mat, p-[1,dir], -dir)
                up = 0
        else: up = 1
        if mat[p+o1]:
            if dn:
                fill(mat, p+[1,-dir], -dir)
                dn = 0
        else: dn = 1
        p += od
    fill(mat, p-od+o1, -dir)
    fill(mat, p-od-o1, -dir)


#bruce 041214 made a common superclass for curve and rectangle classes,
# so I can fix some bugs in a single place, and since there's a
# lot of common code. Some of it could be moved into class shape (for more
# efficiency when several curves in one shape), but I didn't do that, since
# I'm not sure we'll always want to depend on that agreement of coord systems
# for everything in one shape.


class simple_shape_2d: 
    "common code for selection curve and selection rectangle"
    def __init__(self, shp, ptlist, origin, logic, opts):
        """ptlist is a list of 3d points describing a selection
        (in a subclass-specific manner).
        origin is the center of view, and shp.normal gives the direction
        of the line of light.
        """
        # store orthonormal screen-coordinates from shp
        self.right = shp.right
        self.up = shp.up
        self.normal = shp.normal
        
        # store other args
        self.ptlist = ptlist
        self.org = origin + 0.0
        self.logic = logic
        self.slab = opts.get('slab', None) # how thick in what direction
        self.eyeball = opts.get('eye', None) # for projecting if not in ortho mode
        
        # project the (3d) path onto the plane. Warning: arbitrary 2d origin!
        # Note: original code used project_2d_noeyeball, and I think this worked
        # since the points were all in the same screen-parallel plane as
        # self.org (this is a guess), but it seems better to not require this
        # but just to use project_2d here (taking eyeball into account).
        self._computeBBox()
        
    def _computeBBox(self):
        """ Construct the 3d bounding box for the area """  
        # compute bounding rectangle (2d)
        self.pt2d = map( self.project_2d, self.ptlist)
        assert not (None in self.pt2d)
        
        self.bboxhi = reduce(maximum, self.pt2d)
        self.bboxlo = reduce(minimum, self.pt2d)
        bboxlo, bboxhi = self.bboxlo, self.bboxhi
        
        # compute 3d bounding box
        if self.slab:
            x, y = self.right, self.up
            self.bbox = BBox(V(bboxlo, bboxhi), V(x,y), self.slab)
        else:
            self.bbox = BBox()
        return

    def project_2d_noeyeball(self, pt):
        """Project a point into our plane (ignoring eyeball).
           Warning: arbitrary origin!
        """
        x, y = self.right, self.up
        return V(dot(pt, x), dot(pt, y))

    def project_2d(self, pt):
        """like project_2d_noeyeball, but take into account self.eyeball;
        return None for a point that is too close to eyeball to be projected
        [in the future this might include anything too close to be drawn #e]
        """
        p = self.project_2d_noeyeball(pt)
        if self.eyeball:
            # bruce 041214: use "pfix" to fix bug 30 comment #3
            pfix = self.project_2d_noeyeball(self.org)
            p -= pfix
            try:
                ###e we recompute this a lot; should cache it in self or self.shp
                p = p / (dot(pt - self.eyeball, self.normal) / 
                         vlen(self.org - self.eyeball))
            except:
                # bruce 041214 fix of unreported bug:
                # point is too close to eyeball for in-ness to be determined!
                # [More generally, do we want to include points which are
                #  projectable without error, but too close to the eyeball
                #  to be drawn? I think not, but I did not fix this yet
                #  (or report the bug). ###e]
                if platform.atom_debug:
                    print_compact_traceback("atom_debug: ignoring math error for point near eyeball: ")
                return None
            p += pfix
        return p

    def isin_bbox(self, pt):
        "say whether a point is in the optional slab, and 2d bbox (uses eyeball)"
        # this is inlined and extended by curve.isin
        if self.slab and not self.slab.isin(pt):
            return False
        p = self.project_2d(pt)
        if p == None:
            return False
        return p[0]>=self.bboxlo[0] and p[1]>=self.bboxlo[1] \
            and p[0]<=self.bboxhi[0] and p[1]<=self.bboxhi[1]

    pass # end of class simple_shape_2d


class rectangle(simple_shape_2d): # bruce 041214 factored out simple_shape_2d
    "selection rectangle"
    def __init__(self, shp, pt1, pt2, origin, logic, **opts):
        simple_shape_2d.__init__( self, shp, [pt1, pt2], origin, logic, opts)        
    def isin(self, pt):
        return self.isin_bbox(pt)
    def draw(self):
        """Draw the rectangle"""
        color = logicColor(self.logic)
        drawrectangle(self.ptlist[0], self.ptlist[1], self.right, self.up, color)
    pass


class curve(simple_shape_2d): # bruce 041214 factored out simple_shape_2d
    """Represents a single closed curve in 3-space, projected to a
    specified plane.
    """
    def __init__(self, shp, ptlist, origin, logic, **opts):
        """ptlist is a list of 3d points describing a selection.
        origin is the center of view, and normal gives the direction
        of the line of light. Form a structure for telling whether
        arbitrary points fall inside the curve from the point of view.
        """
        # bruce 041214 rewrote some of this method
        simple_shape_2d.__init__( self, shp, ptlist, origin, logic, opts)
        
        # bounding rectangle, in integers (scaled 8 to the angstrom)
        ibbhi = array(map(int,ceil(8*self.bboxhi)+2))
        ibblo = array(map(int,floor(8*self.bboxlo)-2))
        bboxlo = self.bboxlo

        # draw the curve in these matrices and fill it
        # [bruce 041214 adds this comment: this might be correct but it's very
        # inefficient -- we should do it geometrically someday. #e]
        mat = zeros(ibbhi-ibblo)
        mat1 = zeros(ibbhi-ibblo)
        mat1[0,:] = 1
        mat1[-1,:] = 1
        mat1[:,0] = 1
        mat1[:,-1] = 1
        pt2d = self.pt2d
        pt0 = pt2d[0]
        for pt in pt2d[1:]:
            l=ceil(vlen(pt-pt0)*8)
            if l<0.01: continue
            v=(pt-pt0)/l
            for i in range(1+int(l)):
                ij=2+array(map(int,floor((pt0+v*i-bboxlo)*8)))
                mat[ij]=1
            pt0 = pt
        mat1 += mat
        fill(mat1,array([1,1]),1)
        mat1 -= mat
        
        # boolean raster of filled-in shape
        self.matrix = mat1
        # where matrix[0,0] is in x,y space
        self.matbase = ibblo

        # axes of the plane; only used for debugging
        self.x = self.right
        self.y = self.up
        self.z = self.normal

    def isin(self, pt):
        """Project pt onto the curve's plane and return 1 if it falls
        inside the curve.
        """
        # this inlines some of isin_bbox, since it needs an
        # intermediate value computed by that method
        if self.slab and not self.slab.isin(pt):
            return False
        p = self.project_2d(pt)
        if p == None:
            return False
        in_bbox = p[0]>=self.bboxlo[0] and p[1]>=self.bboxlo[1] \
               and p[0]<=self.bboxhi[0] and p[1]<=self.bboxhi[1]
        if not in_bbox:
            return False
        ij = map(int,p*8)-self.matbase
        return not self.matrix[ij]

    def xdraw(self):
        """draw the actual grid of the matrix in 3-space.
        Used for debugging only.
        """
        col=(0.0,0.0,0.0)
        dx = self.x/8.0
        dy = self.y/8.0
        for i in range(self.matrix.shape[0]):
            for j in range(self.matrix.shape[1]):
                if not self.matrix[i,j]:
                    p= (V(i,j)+self.matbase)/8.0
                    p=p[0]*self.x + p[1]*self.y + self.z
                    drawline(col,p,p+dx+dy)
                    drawline(col,p+dx,p+dy)

    def draw(self):
        """Draw two projections of the curve at the limits of the
        thickness that defines the cookie volume.
        The commented code is for debugging.
        [bruce 041214 adds comment: the code looks like it
        only draws one projection.]
        """
        color = logicColor(self.logic)
        pl = zip(self.ptlist[:-1],self.ptlist[1:])
        for p in pl:
            drawline(color,p[0],p[1])
        
        # for debugging
        #self.bbox.draw()
        #if self.eyeball:
        #    for p in self.ptlist:
        #        drawline(red,self.eyeball,p)
        #drawline(white,self.org,self.org+10*self.z)
        #drawline(white,self.org,self.org+10*self.x)
        #drawline(white,self.org,self.org+10*self.y)

    pass # end of class curve

class Circle(simple_shape_2d):
    """Represents the area of a circle ortho projection intersecting with a slab. """
    def __init__(self, shp, ptlist, origin, logic, **opts):
        """<Param> ptlist: the circle center and a point on the perimeter """
        simple_shape_2d.__init__( self, shp, ptlist, origin, logic, opts)
            
    def draw(self):
        """the profile circle draw"""
        color =  logicColor(self.logic)
        drawCircle(color, self.ptlist[0], self.rad, self.slab.normal)
        
    def isin(self, pt):
        """Test if a point is in the area """
        if self.slab and not self.slab.isin(pt):
            return False
            
        p2d = self.project_2d(pt)
        dist = vlen(p2d - self.cirCenter)
        if dist <= self.rad :
            return True
        else:
            return False
   
    def _computeBBox(self):
        """Construct the 3D bounding box for this volume. """
        self.rad = vlen(self.ptlist[1] - self.ptlist[0])
        self.cirCenter = self.project_2d(self.ptlist[0])
        
        bbhi = self.cirCenter + V(self.rad, self.rad)
        bblo = self.cirCenter - V(self.rad, self.rad)
        
        x, y = self.right, self.up
        self.bbox = BBox(V(bblo, bbhi), V(x,y), self.slab)
        
    
class shape:
    """Represents a sequence of curves, each of which may be
    additive or subtractive.
    [This class should be renamed, since there is also an unrelated
    Numeric function called shape().]
    """
    def __init__(self, right, up, normal):
        """A shape is a set of curves defining the whole cutout.
        """
        self.curves = []
        self.bbox = BBox()

        # These arguments are required to be orthonormal:
        self.right = right
        self.up = up
        self.normal = normal
    
    def pickline(self, ptlist, origin, logic, **xx):
            """Add a new curve to the shape.
            Args define the curve (see curve) and the logic operator
            for the curve telling whether it adds or removes material.
            """
            c = curve(self, ptlist, origin, logic, **xx)
            #self.curves += [c]
            #self.bbox.merge(c.bbox)
            return c
            
    def pickrect(self, pt1, pt2, org, logic, **xx):
            c = rectangle(self, pt1, pt2, org, logic, **xx)
            #self.curves += [c]
            #self.bbox.merge(c.bbox)
            return c

    def __str__(self):
        return "<Shape of " + `len(self.curves)` + ">"

    pass # end of class shape
    
class SelectionShape(shape):
        """This is used to construct shape for atoms/chunks selection. A curve or rectangle will be created, which is used as an area selection of all the atoms/chunks """
        def pickline(self, ptlist, origin, logic, eyeBall):
            self.curve = shape.pickline(self, ptlist, origin, logic, eye=eyeBall)
   
        def pickrect(self, pt1, pt2, org, logic, eyeBall):
            self.curve = shape.pickrect(self, pt1, pt2, org, logic, eye=eyeBall)
            
        def select(self, assy):
            """Loop thru all the atoms that are visible and select any
                that are 'in' the shape, ignoring the thickness parameter.
            """
        #bruce 041214 conditioned this on a.visible() to fix part of bug 235;
        # also added .hidden check to the last of 3 cases. Left everything else
        # as I found it. This code ought to be cleaned up to make it clear that
        # it uses the same way of finding the selection-set of atoms, for all
        # three logic cases in each of select and partselect. If anyone adds
        # back any differences, this needs to be explained and justified in a
        # comment; lacking that, any such differences should be considered bugs.
        # (BTW I don't know whether it's valid to care about logic of only the
        # first curve in the shape, as this code does.)
        
            if assy.selwhat:
                self._chunksSelect(assy)
            else:
                self._atomsSelect(assy)   
        
        
        def _atomsSelect(self, assy):
            """Select all atoms inside the curve, ignoring thickness"""    
            c=self.curve
            if c.logic == 1:
                for mol in assy.molecules:
                    if mol.hidden: continue
                    disp = mol.get_dispdef()
                    for a in mol.atoms.itervalues():
                        if c.isin(a.posn()) and a.visible(disp):
                            a.pick()
            elif c.logic == 2:
                for mol in assy.molecules:
                    if mol.hidden: continue
                    disp = mol.get_dispdef()
                    for a in mol.atoms.itervalues():
                        if c.isin(a.posn()) and a.visible(disp):
                            a.pick()
                        else:
                            a.unpick()
            else:
                for a in assy.selatoms.values():
                    if a.molecule.hidden: continue #bruce 041214
                    if c.isin(a.posn()) and a.visible():
                        a.unpick()

        def _chunksSelect(self, assy):
            """Loop thru all the atoms that are visible and select any
            that are 'in' the shape, ignoring the thickness parameter.
            pick the parts that contain them
            """
        #bruce 041214 conditioned this on a.visible() to fix part of bug 235;
        # also added .hidden check to the last of 3 cases. Same in self.select().
            c=self.curve
            if c.logic == 2:
                # drag selection: unselect any selected molecule not in the area, 
                # modified by Huaicai to fix the selection bug 10/05/04
                for m in assy.selmols[:]:
                    m.unpick()
                            
            if c.logic == 1 or c.logic == 2 : # shift drag selection
                for mol in assy.molecules:
                    if mol.hidden: continue
                    disp = mol.get_dispdef()
                    for a in mol.atoms.itervalues():
                        if c.isin(a.posn()) and a.visible(disp):
                                a.molecule.pick()
                                break
    
            if c.logic == 0:  # Ctrl drag slection --everything selected inside dragging area unselected
                for m in assy.selmols[:]:
                    if m.hidden: continue #bruce 041214
                    disp = m.get_dispdef()
                    for a in m.atoms.itervalues():
                            if c.isin(a.posn()) and a.visible(disp):
                                    m.unpick()
                                    break   

class CookieShape(shape):
    """ This class is used to create cookies. It supports multiple parallel layers, each curve sits
         on a particular layer."""
    def __init__(self, right, up, normal, mode, latticeType):
            shape.__init__(self, right, up, normal)
            ##Each element is a dictionary object storing "carbon" info for a layer
            self.carbonPostDict = {} 
            self.bondLayers = {} ##Each element is a dictionary for the bonds info for a layer
            self.displist = glGenLists(1)
            self.havelist = 0
            self.dispMode = mode
            self.latticeType = latticeType
            self.layerThickness = {}
            self.layeredCurves = {} #A list of (merged bb, curves) for each layer

    def pushdown(self, lastLayer):
            """Put down one layer from last layer """
            th, n = self.layerThickness[lastLayer]
            print "th, n", th, n
            return th*n

    def _saveMaxThickness(self, layer, thickness, normal):
            if layer not in self.layerThickness:
                self.layerThickness[layer] = (thickness, normal)
            elif thickness > self.layerThickness[layer][0]:
                self.layerThickness[layer] = (thickness, normal)
    
    def isin(self, pt, curves=None):
        """returns 1 if pt is properly enclosed by the curves.
        curve.logic = 1 ==> include if inside
        curve.logic = 0 ==> remove if inside
        curve.logic = 2 ==> remove if outside
        """
        # bruce 041214 comment: this might be a good place to exclude points
        # which are too close to the screen to be drawn. Not sure if this
        # place would be sufficient (other methods call c.isin too).
        # Not done yet. ###e
        val = 0
        if not curves: curves = self.curves
        for c in curves:
            if c.logic == 1: val = val or c.isin(pt)
            elif c.logic == 2: val = val and c.isin(pt)
            elif c.logic == 0: val = val and not c.isin(pt)
        return val
    
    def pickCircle(self, ptlist, origin, logic, layer, slabC):
        """Add a new circle to the shape. """
        c = Circle(self, ptlist, origin, logic, slab=slabC)
        self._saveMaxThickness(layer, slabC.thickness, slabC.normal)
        self._addCurve(layer, c)
    
    def pickline(self, ptlist, origin, logic, layer, slabC):
        """Add a new curve to the shape.
        Args define the curve (see curve) and the logic operator
        for the curve telling whether it adds or removes material.
        """
        c = shape.pickline(self, ptlist, origin, logic, slab=slabC)
        self._saveMaxThickness(layer, slabC.thickness, slabC.normal)
        #self._cutCookie(layer, c)
        self._addCurve(layer, c)
        
    def pickrect(self, pt1, pt2, org, logic, layer, slabC):
        """Add a new rectangle to the shape.
        Args define the rectangle and the logic operator
        for the curve telling whether it adds or removes material.
        """
        c = shape.pickrect(self, pt1, pt2, org, logic, slab=slabC)
        self._saveMaxThickness(layer, slabC.thickness, slabC.normal)
        #self._cutCookie(layer, c)
        self._addCurve(layer, c)

    def _updateBBox(self, curveList):
        """Re-compute the bounding box for the list of curves"""
        bbox = BBox()
        for c in curveList[1:]:
            bbox.merge(c.bbox)
        curveList[0] = bbox
        
    
    def undo(self, currentLayer):
        """This would work for shapes, if anyone called it.
        """
        curves = self.layeredCurves[currentLayer]
        if len(curves) > 1: 
            curves = curves[:-1]
        self._updateBBox(curves)
        self.layeredCurves[currentLayer] = curves
        self.havelist = 0

    def clear(self, currentLayer):
        """This would work for shapes, if anyone called it.
        """
        curves = self.layeredCurves[currentLayer]
        curves = []
        self.layeredCurves[currentLayer] = curves
        self.havelist = 0

    def combineLayers(self):
        """Experimental code to add all curves and bbox together to make themolmake wokring. It may be removed later. """
        for cbs in self.layeredCurves.values():
            if cbs:
                self.bbox.merge(cbs[0])
                self.curves += cbs[1:]
   
    def _hashAtomPos(self, pos):
        return int(dot(V(1000000, 1000,1),floor(pos*1.2)))
    
    def _addCurve(self, layer, c):
        """Add curve into its own layer, update the bbox"""
        self.havelist = 0
        
        if not layer in self.layeredCurves:
            bbox = BBox()
            self.layeredCurves[layer] = [bbox, c]
        else: self.layeredCurves[layer] += [c]
        self.layeredCurves[layer][0].merge(c.bbox)
    
    def _cellDraw(self, color, p0, p1):
        hasSinglet = False
        if type(p1) == type((1,)): 
                v1 = p1[0]
                hasSinglet = True
        else: v1 = p1
        if self.dispMode == 'Tubes':
             drawcylinder(color, p0, v1, 0.2)
        else:
            drawsphere(color, p0, 0.5, 1)
            if hasSinglet:
                drawsphere(color, v1, 0.2, 1)
            else:    
                drawsphere(color, v1, 0.5, 1)
            drawline(white, p0, v1)
    
    def _anotherDraw(self, layerColor):
        """The original way of selecting cookies, but do it layer by layer, so we can control how to display each layer. """
        if self.havelist:
            glCallList(self.displist)
            return
        glNewList(self.displist, GL_COMPILE_AND_EXECUTE)
        for layer in self.layeredCurves.keys():
            bbox = self.layeredCurves[layer][0]
            curves = self.layeredCurves[layer][1:]
            if not curves: continue
            color = layerColor[layer]
            for c in curves: c.draw()
            try:
                bblo, bbhi = bbox.data[1], bbox.data[0]
                allCells = genDiam(bblo, bbhi, self.latticeType)
                for cell in allCells:
                    for pp in cell:
                        p1 = p2 = None
                        if self.isin(pp[0], curves):
                            if self.isin(pp[1], curves):
                                p1 = pp[0]; p2 = pp[1]
                            else: 
                                p1 = pp[0]; p2 = ((pp[1]+pp[0])/2,)
                        elif self.isin(pp[1], curves):
                                p1 = pp[1]; p2 = ((pp[1]+pp[0])/2, )
                        if p1 and p2: self._cellDraw(color, p1, p2) 
            except:
            # bruce 041028 -- protect against exceptions while making display
            # list, or OpenGL will be left in an unusable state (due to the lack
            # of a matching glEndList) in which any subsequent glNewList is an
            # invalid operation. (Also done in chem.py; see more comments there.)
                print_compact_traceback( "bug: exception in shape.draw's displist; ignored: ")
        glEndList()
        self.havelist = 1 #
    
    
    def _cutCookie(self, layer, c):
        """For each user defined curve, cut the cookie for it, store carbon postion into a global dictionary, store the bond information into each layer. """
        self.havelist = 0
        
        bblo, bbhi = c.bbox.data[1], c.bbox.data[0]
        griderator = genDiam(bblo, bbhi)
        if c.logic == 0: ##Remove if inside
            if not self.bondLayers[layer]: return
            else:
                bonds = self.bondLayers[layer]
                carbons = self.carbonPostDict[layer]
                pp=griderator.next()
                while (pp):
                       for p in pp:
                            if not c.isin(p): continue
                            pph = self._hashAtomPos(p)
                            if bonds.has_key(pph):
                                del bonds[pph]
                            if carbons.has_key(pph):
                                del carbons[pph]
                       pp=griderator.next()
        elif c.logic == 2: ##Remove if outside
            for la in self.bondLayers.keys():
                if la != layer:        
                        del self.bondLayers[la]
                        del self.carbonPostDict[la]
            if not self.bondLayers.has_key(layer): return
            bonds = self.bondLayers[layer]
            carbons = self.carbonPostDict[layer]
            pp=griderator.next()
            while (pp):
                for p in pp:
                    if c.isin(p): continue
                    pph = self._hashAtomPos(p)
                    if carbons.has_key(pph):
                       del carbons[pph]
                       del bonds[pph]
                pp=griderator.next()
        elif c.logic == 1: ##Include if inside
            if self.bondLayers.has_key(layer):
                bonds = self.bondLayers[layer]
                carbons = self.carbonPostDict[layer]
            else:
                bonds = {}
                carbons = {}
            pp=griderator.next()
            while (pp):
                pph=[None, None]
                for p, ii in zip(pp, (0,1)):
                   if c.isin(p):
                      pph[ii] = self._hashAtomPos(p)
                      if not pph[ii] in carbons:
                         carbons[pph[ii]] = p
                if pph[0] and pph[1]: 
                    self._saveBonds(bonds, pph[0], pph[1])
                elif pph[0]:
                    p1h = self._hashAtomPos(pp[1])
                    self._saveBonds(bonds, pph[0], (p1h,pp[1]))
                elif pph[1]:
                    p0h = self._hashAtomPos(pp[0])
                    self._saveBonds(bonds, pph[1], (p0h,pp[0]))
                pp=griderator.next()
            self.bondLayers[layer] = bonds    
            self.carbonPostDict[layer] = carbons
            
        self.havelist = 1
        
            
    def _saveBonds(self, dict, key, value):
            """ """
            if not key in dict:
                   dict[key] = [value]
            else:
                values = dict[key]
                #print "key, value, all values:", key, value,values       
                if not value in values :
                   if type(value) ==type((1,1)):
                       for v in values: 
                            if v==value: 
                                 v=value[0]; break
                   #print "key, value: ", key, value
                else: values += [value]
   
   
    def changeDisplayMode(self, mode):
        self.dispMode = mode
        self.havelist = 0
        
   
    def draw(self, win, layerColor):
        """Draw the shape. win, not used, is for consistency among
        drawing functions (and may be used if drawing logic gets
        more sophisticated.

        Find  binding box for the curve and check the position each
        carbon atom in a diamond lattice would occupy for being 'in'
        the shape. A tube representation of the atoms thus selected is
        saved as a GL call list for fast drawing.
        
        This method is only for cookie-cutter mode. --Huaicai
        """
        if 1: 
            self._anotherDraw(layerColor)
            return
            
        if self.havelist:
            glCallList(self.displist)
            return
        glNewList(self.displist, GL_COMPILE_AND_EXECUTE)
        try:
            for layer, bonds in self.bondLayers.items():
                color = layerColor[layer]
                carbons = self.carbonPostDict[layer]
                if self.dispMode == 'Spheres':
                    for cP in carbons.values():
                        drawsphere(color, cP, 0.5, 1)
                for cK, bList in bonds.items():
                   hasSinglet = False
                   p0 = carbons[cK]
                   for b in bList:
                       if type(b) == type(1):
                           p1 = carbons[b]
                       else: 
                            p1 = (p0 + b[1])/2.0
                            if self.dispMode == 'Spheres': drawsphere(color, p1, 0.2, 1)
                       if self.dispMode == 'Tubes':
                            drawcylinder(color, p0, p1, 0.2)
                       else:
                            drawline(white, p0, p1)    
        except:
            # bruce 041028 -- protect against exceptions while making display
            # list, or OpenGL will be left in an unusable state (due to the lack
            # of a matching glEndList) in which any subsequent glNewList is an
            # invalid operation. (Also done in chem.py; see more comments there.)
            print_compact_traceback( "bug: exception in shape.draw's displist; ignored: ")
        glEndList()
        self.havelist = 1 # always set this flag, even if exception happened.
    
    def buildChunk(self, assy):
        """Build molecules for the cookie """
        from chunk import molecule
        from chem import gensym, atom
        
        allCarbons = {}
        mol = molecule(assy, gensym("Cookie."))
        for layer, bonds in self.bondLayers.items():
            carbons = self.carbonPostDict[layer]
            for cK, cP in carbons.items():
                if not cK in allCarbons:
                    atomCell = atom("C", cP, mol) 
                    allCarbons[cK] = atomCell
            for cK, cB in bonds.items():
                a1 = allCarbons[cK]
                for bb in cB:
                    if type(bb) == type(1):
                        a2 = allCarbons[bb]
                    else:
                        a2 = atom("X", bb, mol)
                    mol.bond(a1, a2)
        if len(mol.atoms) > 0:
        #bruce 050222 comment: much of this is not needed, since mol.pick() does it.
            assy.addmol(mol)
            assy.unpickatoms()
            assy.unpickparts()
            assy.selwhat = 2
            mol.pick()
            assy.mt.mt_update()                