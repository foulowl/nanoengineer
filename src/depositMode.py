# Copyright (c) 2004 Nanorex, Inc.  All rights reserved.
"""
depositMode.py

BRUCE IS TEMPORARILY OWNING ALL MODE FILES for a few days starting 040922,
in order to fix mode-related bugs by revising the interface between modes.py,
all specific modes, and GLPane.py. During this period, please consult Bruce
before any changes to these files.

$Id$
"""
from Numeric import *
from modes import *
from VQT import *
from chem import *
import drawer

class depositMode(basicMode):
    """ This class is used to manually add atoms to create any structure
    """
    def __init__(self, glpane):
        basicMode.__init__(self, glpane, 'DEPOSIT')
	self.backgroundColor = 74/256.0, 187/256.0, 227/256.0
	self.gridColor = 74/256.0, 187/256.0, 227/256.0
	self.newMolecule = None
	self.makeMenus()

    def setMode(self):
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        basicMode.setMode(self)
        self.o.assy.unpickatoms()
        self.o.assy.unpickparts()
        self.saveDisp = self.o.display
        self.o.setDisplay(diTUBES)
        self.o.assy.selwhat = 0
        self.new = None
        self.o.singlet = None
        self.w.sketchAtomToolbar.show()

    def Done(self):
        basicMode.Done(self)
        self.o.display = self.saveDisp
        self.new = None
        self.o.singlet = None
        self.o.setMode('SELECT')
        self.w.sketchAtomToolbar.hide()

    def keyPress(self,key):
        for sym, code, num in self.w.elTab:
            if key == code: self.w.setElement(sym)

    def getCoords(self, event):
        """ Retrieve the object coordinates of the point on the screen
	with window coordinates(int x, int y) 
	"""
        x = event.pos().x()
        y = self.o.height - event.pos().y()

        p1 = A(gluUnProject(x, y, 0.0))
        p2 = A(gluUnProject(x, y, 1.0))
        at = self.o.assy.findpick(p1,norm(p2-p1),2.0)
        if at: pnt = at.posn()
        else: pnt = - self.o.pov
        k = (dot(self.o.lineOfSight,  pnt - p1) /
             dot(self.o.lineOfSight, p2 - p1))

        return p1+k*(p2-p1)

    def bareMotion(self, event):
        doPaint = 0
        if self.o.singlet:
            self.o.singlet.molecule.changeapp()
            self.o.singlet = None
            doPaint = 1
        p1, p2 = self.o.mousepoints(event)
        z = norm(p1-p2)
        x = cross(self.o.up,z)
        y = cross(z,x)
        mat = transpose(V(x,y,z))
        for mol in self.o.assy.molecules:
            if mol.display != diINVISIBLE:
                a = mol.findSinglets(p2, mat, TubeRadius, -TubeRadius)
                if a:
                    mol.changeapp()
                    self.o.singlet = a
                    doPaint = 1
                    break
        if doPaint: self.o.paintGL()        
	
    def leftDown(self, event):
        """Move the selected object(s) in the plane of the screen following
        the mouse.
        """
        self.o.SaveMouse(event)
        self.picking = True
        p1, p2 = self.o.mousepoints(event)
        self.dragdist = 0.0

    def leftDrag(self, event):
        """ Press left mouse button down to add an atom
	"""
       
        w=self.o.width+0.0
        h=self.o.height+0.0
        deltaMouse = V(event.pos().x() - self.o.MousePos[0],
                       self.o.MousePos[1] - event.pos().y(), 0.0)
        self.dragdist += vlen(deltaMouse)

        self.o.SaveMouse(event)

        self.o.paintGL()

    def leftUp(self, event):
        self.EndPick(event, 1)
        
    def EndPick(self, event, selSense):
        """bond atom if it's close to something
        """
        if not self.picking: return
        self.picking = False
        el =  PeriodicTable[self.w.Element]

        atomPos = self.getCoords(event)
        p1, p2 = self.o.mousepoints(event)

        if self.dragdist<70000: # let it drag
            # didn't move much, call it a click
            if selSense == 0:
                self.o.assy.pick(p1,norm(p2-p1))
                self.o.assy.kill()
            if selSense == 1:
                if self.o.singlet:
                    self.attach(el, self.o.singlet)
                elif not self.new:
                    oneUnbonded(el, self.o.assy, atomPos)
                self.new = None
            if selSense == 2: print '????'

        else:
            if not self.new:
                oneUnbonded(el, self.o.assy, atomPos)
            self.new = None
            
        self.o.paintGL()                  

    def leftDouble(self, event):
        """ End deposit mode
	"""
	self.Done()

    ###################################################################
    #  Oh, ye acolytes of klugedom, feast your eyes on the following  #
    ###################################################################

    # singlet is supposedly the lit-up singlet we're pointing to.
    # bond the new atom to it, and any other ones around you'd
    # expect it to form bonds with
    def attach(self, el, singlet):
        if not el.numbonds: return
        spot = self.findSpot(el, singlet)
        pl = []
        mol = singlet.molecule
        cr = el.rcovalent
        for s in mol.nearSinglets(spot, cr*1.5):
            pl += [(s, self.findSpot(el, s))]
        n = min(el.numbonds, len(pl))
        if n == 1:
            self.bond1(el, singlet, spot)
        elif n == 2:
            self.bond2(el,pl)
        elif n == 3:
            self.bond3(el,pl)
        elif n == 4:
            self.bond4(el,pl)
        else: print "too many bonds!"
        mol.shakedown()
        self.o.paintGL()

    # given an element and a singlet, find the place an atom of the
    # element would like to be if bonded at the singlet
    def findSpot(self, el, singlet):
        obond = singlet.bonds[0]
        a1 = obond.other(singlet)
        cr = el.rcovalent
        pos = singlet.posn() + cr*norm(singlet.posn()-a1.posn())
        return pos

    def bond1(self, el, singlet, pos):
        obond = singlet.bonds[0]
        a1 = obond.other(singlet)
        mol = a1.molecule
        a = atom(el.symbol, pos, mol)
        obond.rebond(singlet, a)
        del mol.atoms[singlet.key]
        if el.base:
            # There is at least one other bond
            # this rotates the atom to match the bond formed above
            r = singlet.posn() - pos           
            rq = Q(r,el.base)
            for q in el.quats:
                q = rq + q - rq
                x = atom('X', pos+q.rot(r), mol)
                mol.bond(a,x)
        
    def bond2(self, el, lis):
        s1, p1 = lis[0]
        s2, p2 = lis[1]
        pos = (p1+p2)/2.0
        opos = s2.posn()

        mol = s1.molecule
        a = atom(el.symbol, pos, mol)

        s1.bonds[0].rebond(s1, a)
        del mol.atoms[s1.key]
        s2.bonds[0].rebond(s2, a)
        del mol.atoms[s2.key]

        # this rotates the atom to match the bonds formed above
        r = s1.posn() - pos           
        rq = Q(r,el.base)
        # this moves the second bond to a possible position
        # note that it doesn't matter which bond goes where
        q1 = rq + el.quats[0] -rq
        b2p = q1.rot(r)
        # rotate it into place
        tw = twistor(r, b2p, opos-pos)
        # now for all the rest
        for q in el.quats[1:]:
            q = rq + q - rq + tw
            x = atom('X', pos+q.rot(r), mol)
            mol.bond(a,x)

    def bond3(self, el, lis):
        s1, p1 = lis[0]
        s2, p2 = lis[1]
        s3, p3 = lis[2]
        pos = (p1+p2+p3)/3.0
        opos =  (s1.posn() + s2.posn() + s3.posn())/3.0

        mol = s1.molecule
        a = atom(el.symbol, pos, mol)

        s1.bonds[0].rebond(s1, a)
        del mol.atoms[s1.key]
        s2.bonds[0].rebond(s2, a)
        del mol.atoms[s2.key]
        s3.bonds[0].rebond(s3, a)
        del mol.atoms[s3.key]

        opos = pos + el.rcovalent*norm(pos-opos)
        x = atom('X', opos, mol)
        mol.bond(a,x)

    def bond4(self, el, lis):
        s1, p1 = lis[0]
        s2, p2 = lis[1]
        s3, p3 = lis[2]
        s4, p4 = lis[3]
        pos = (p1+p2+p3+p4)/4.0
        opos =  (s1.posn() + s2.posn() + s3.posn() + s4.posn())/4.0

        mol = s1.molecule
        a = atom(el.symbol, pos, mol)

        s1.bonds[0].rebond(s1, a)
        del mol.atoms[s1.key]
        s2.bonds[0].rebond(s2, a)
        del mol.atoms[s2.key]
        s3.bonds[0].rebond(s3, a)
        del mol.atoms[s3.key]
        s4.bonds[0].rebond(s4, a)
        del mol.atoms[s3.key]


    def Draw(self):
        """ Draw a sketch plane to indicate where the new atoms will sit
	by default
	"""
	basicMode.Draw(self)
        if self.sellist: self.pickdraw()
        self.o.assy.draw(self.o)
        self.surface()

                           
    def surface(self):
        """The water's surface
	"""
	glDisable(GL_LIGHTING)
	glColor4fv(self.gridColor + (0.6,))
        glEnable(GL_BLEND)
        
	# the grid is in eyespace
	glPushMatrix()
	q = self.o.quat
	glTranslatef(-self.o.pov[0], -self.o.pov[1], -self.o.pov[2])
	glRotatef(- q.angle*180.0/pi, q.x, q.y, q.z)
        x = 1.5*self.o.scale
	glBegin(GL_QUADS)
        glVertex(-x,-x,0)
        glVertex(x,-x,0)
        glVertex(x,x,0)
        glVertex(-x,x,0)
	glEnd()
	glPopMatrix()
        glDisable(GL_BLEND)
	glEnable(GL_LIGHTING)
        return

        
    def makeMenus(self):
        
        self.Menu1 = self.makemenu([('Cancel', self.Flush),
                                    ('Restart', self.Restart),
                                    ('Backup', self.Backup),
                                    None,
                                    ('Move', self.move),
                                    ('Double bond', self.skip),
                                    ('Triple bond', self.skip)
                                    ])
        
        self.Menu2 = self.makemenu([('Carbon', self.w.setCarbon),
                                    ('Hydrogen', self.w.setHydrogen),
                                    ('Oxygen', self.w.setOxygen),
                                    ('Nitrogen', self.w.setNitrogen)
                                    ])
        
        self.Menu3 = self.makemenu([('Passivate', self.o.assy.modifyPassivate),
                                    ('Hydrogenate', self.o.assy.modifyHydrogenate),
                                    ('Separate', self.o.assy.modifySeparate)])

    def move(self):
        # go into move mode
        self.Done()
        self.o.setMode('MODIFY')
                                    
    def skip(self):
        pass
