# Copyright 2007 Nanorex, Inc.  See LICENSE file for details. 
"""
@author:    Ninad
@version:   $Id$
@copyright: 2007 Nanorex, Inc.  See LICENSE file for details.
@license:   GPL

TODOs:
- Refactor/ expand snap code. Should all the snapping code be in its own module?
- Need to discuss and derive various snap rules 
  Examples: If 'theta_snap' between dragged line and the  two reference enties 
            is the same, then the snap should use the entity with shortest  
            distance
            Should horizontal/vertical snap checkes always be done before 
            standard axis  snap checks -- guess-- No. The current implementation
            however skips the standard axis snap check if the 
            horizontal/vertical snap checks succeed.           

"""

from TemporaryCommand import TemporaryCommand_Overdrawing

from drawer import drawline, drawsphere
from constants import black, darkred, blue

from OpenGL.GL import glPopMatrix
from OpenGL.GL import glPushMatrix

from VQT import vlen, Q, norm, angleBetween, V, ptonline


STARTPOINT_SPHERE_RADIUS = 1.0
STARTPOINT_SPHERE_DRAWLEVEL = 2

# == GraphicsMode part

class LineMode_GM( TemporaryCommand_Overdrawing.GraphicsMode_class ):
    """
    Custom GraphicsMode for use as a component of LineMode.
    
    Its a temporary mode that draws temporary line with mouse click points 
    as endpoints and then returns to the previous mode when the  
    mouseClickLimit specified by the user is reached.
    
    Example use:
    User is working in selectMolsMode, Now he enters a temporary mode 
    called DnaLine mode, where, he clicks two points in the 3Dworkspace 
    and expects to create a DNA using the points he clicked as endpoints. 
    Internally, the program returns to the previous mode after two clicks. 
    The temporary mode sends this information to the method defined in 
    the previous mode called acceptParamsFromTemporaryMode and then the
    previous mode (selectMolsMode) can use it further to create a dna 
    @see: L{DnaLineMode}
    @see: selectMolsMode.provideParamsForTemporaryMode comments for 
          related  TODOs. 
        
    TODO: 
    -Need further documentation. 
    """    
    
    #Initial values of instance variables --
    
    #The first end point of the line being drawn. 
    #It gets initialized during left down --
    endPoint1 = None 
    #The second endpoint of the line. This gets constantly updated as you 
    # free drag the mouse (bare motion) 
    endPoint2 = None
    
    
    #Rubberband line color
    rubberband_line_color = black
    rubberband_line_width = 1  #thickness or 'width' for drawer.drawline
    
    endPoint1_sphereColor = darkred
    endPoint1_sphereOpacity = 0.5
    
    _snapOn = False
    _snapType = ''
    _standardAxisVectorForDrawingSnapReference = None

    def leftDown(self, event):
        """
        Event handler for LMB press event.
        """        
        #The endPoint1 and self.endPoint2 are the mouse points at the 'water' 
        #surface. Soon, support will be added so that these are actually points 
        #on a user specified reference plane. Also, once any temporary mode 
        # begins supporting highlighting, we can also add feature to use 
        # coordinates of a highlighted object (e.g. atom center) as endpoints 
        # of the line
        farQ_junk, self.endPoint1 = self.dragstart_using_GL_DEPTH( event)  
        
        if self._snapOn and self.endPoint2:
            # This fixes a bug. Example: Suppose the dna line is snapped to a 
            # constraint during the bare motion and the second point is clicked
            # when this happens, the second clicked point is the new 
            #'self.endPoint1'  which needs to be snapped like we did for 
            # self.endPoint2 in the bareMotion. Setting self._snapOn to False
            # ensures that the cursor is set to the simple Pencil cursor after 
            # the click  -- Ninad 2007-12-04
            self.endPoint1 = self.snapLineEndPoint()    
            self._snapOn = False
        self.command.mouseClickPoints.append(self.endPoint1)
        return
    
    def bareMotion(self, event):
        """
        Event handler for simple drag event. (i.e. the free drag without holding
        down any mouse button)
        """       
        if len(self.command.mouseClickPoints) > 0:
            self.endPoint2 = self.dragto( self.endPoint1, event)
            self.endPoint2 = self.snapLineEndPoint()  
            self.update_cursor_for_no_MB()
            self.glpane.gl_update()    
        
        return
    
    def snapLineEndPoint(self):
        """
        Snap the line to the specified constraints. 
        To be refactored and expanded. 
        @return: The new endPoint2 i.e. the moving endpoint of the rubberband 
                 line . This value may be same as previous or snapped so that it
                 lies on a specified vector (if one exists)                 
        @rtype: B{A}
        """        
        endPoint2 = self._snapEndPointHorizontalOrVertical()
        
        if not self._snapOn:
            endPoint2 = self._snapEndPointToStandardAxis()
            pass
                
        return endPoint2
    
    def _snapEndPointHorizontalOrVertical(self):
        """
        Snap the second endpoint of the line (and thus the whole line) to the
        screen horizontal or vertical vectors. 
        @return: The new endPoint2 i.e. the moving endpoint of the rubberband 
                 line . This value may be same as previous or snapped so that 
                 line is horizontal or vertical depending upon the angle it 
                 makes with the horizontal and vertical. 
        @rtype: B{A}
        """
        up = self.glpane.up
        down = self.glpane.down
        left = self.glpane.left
        right = self.glpane.right  
        
        endPoint2 = self.endPoint2
        
        snapVector = V(0, 0, 0)
        
        currentLineVector = norm(self.endPoint2 - self.endPoint1)
        
        theta_horizontal = angleBetween(right, currentLineVector) 
        theta_vertical = angleBetween(up, currentLineVector) 
        
        theta_horizontal_old = theta_horizontal
        theta_vertical_old = theta_vertical
        
        if theta_horizontal != 90.0:            
            theta_horizontal = min(theta_horizontal, 
                                   (180.0 - theta_horizontal))
        
        if theta_vertical != 90.0:            
            theta_vertical = min(theta_vertical, 
                                 180.0 - theta_vertical)
            
        theta = min(theta_horizontal, theta_vertical)
                
        if theta <= 2.0 and theta != 0.0:
            self._snapOn = True
            if theta == theta_horizontal:
                self._snapType = 'HORIZONTAL'
                if theta_horizontal == theta_horizontal_old:
                    snapVector = right                   
                else:
                    snapVector = left
            elif theta == theta_vertical:
                self._snapType = 'VERTICAL'
                if theta_vertical == theta_vertical_old:
                    snapVector = up
                else:
                    snapVector = down
                    
            endPoint2 = self.endPoint1 + \
                      vlen(self.endPoint1 - self.endPoint2)*snapVector
 
        else:                
            self._snapOn = False
            
        return endPoint2
    
    def _snapEndPointToStandardAxis(self):
        """
        Snap the second endpoint of the line so that it lies on the nearest
        axis vector. (if its close enough) . This functions keeps the uses the
        current rubberband line vector and just extends the second end point 
        so that it lies at the intersection of the nearest axis vector and the 
        rcurrent rubberband line vector. 
        @return: The new endPoint2 i.e. the moving endpoint of the rubberband 
                 line . This value may be same as previous or snapped to lie on
                 the nearest axis (if one exists) 
        @rtype: B{A}
        """
        x_axis = V(1, 0, 0)
        y_axis = V(0, 1, 0)
        z_axis = V(0, 0, 1)
        
        endPoint2 = self.endPoint2
        currentLineVector = norm(self.endPoint2 - self.endPoint1)
        
        theta_x = angleBetween(x_axis, self.endPoint2)
        theta_y = angleBetween(y_axis, self.endPoint2)
        theta_z = angleBetween(z_axis, self.endPoint2)
        
        theta_x = min(theta_x, (180 - theta_x))
        theta_y = min(theta_y, (180 - theta_y))
        theta_z = min(theta_z, (180 - theta_z))
        
        theta = min(theta_x, theta_y, theta_z)
                
        if theta < 2.0:    
            if theta == theta_x:                
                self._standardAxisVectorForDrawingSnapReference = x_axis
            elif theta == theta_y:
                self._standardAxisVectorForDrawingSnapReference = y_axis
            elif theta == theta_z:                
                self._standardAxisVectorForDrawingSnapReference = z_axis
            
            endPoint2 = ptonline(self.endPoint2, 
                                 V(0, 0, 0), 
                                 self._standardAxisVectorForDrawingSnapReference)
        else:
            self._standardAxisVectorForDrawingSnapReference = None
            
                    
        return endPoint2
    
    def _drawSnapReferenceLines(self):
        """
        Draw the snap reference lines as dottedt lines. Example, if the 
        moving end of the rubberband line is 'close enough' to a standard axis 
        vector, that point is 'snapped' soi that it lies on the axis. When this 
        is done, program draws a dotted line from origin to the endPoint2 
        indicating that the endpoint is snapped to that axis line.
        
        This method is called inside the self.Draw method. 
        
        @see: self._snapEndPointToStandardAxis 
        @see: self.Draw
        """
        if not self.endPoint2:
            return
        if self._standardAxisVectorForDrawingSnapReference:
            drawline(blue,
                     V(0, 0, 0), 
                     self.endPoint2, 
                     dashEnabled = True, 
                     stipleFactor = 4,
                     width = 2)
           

    def Draw(self):
        """
        Draw method for this temporary mode. 
        """
        TemporaryCommand_Overdrawing.GraphicsMode_class.Draw(self)
        if self.endPoint2:
            glPushMatrix()  
            if self.endPoint1:
                drawsphere(self.endPoint1_sphereColor, 
                           self.endPoint1, 
                           STARTPOINT_SPHERE_RADIUS,
                           STARTPOINT_SPHERE_DRAWLEVEL,
                           opacity = self.endPoint1_sphereOpacity
                           )            
            drawline(self.rubberband_line_color, 
                 self.endPoint1, 
                 self.endPoint2,
                 width = self.rubberband_line_width,
                 dashEnabled = True)         
            
            self._drawSnapReferenceLines()
            glPopMatrix()            
    
    def leftUp(self, event):
        """
        Event handler for Left Mouse button left-up event
        """      
        assert len(self.command.mouseClickPoints) <= self.command.mouseClickLimit
                        
        if len(self.command.mouseClickPoints) == self.command.mouseClickLimit:
            self.endPoint2 = None
            self._snapOn = False
            self._standardAxisVectorForDrawingSnapReference = None
            self.glpane.gl_update()
            self.command.Done(exit_using_done_or_cancel_button = False)            
            return
         
    def update_cursor_for_no_MB(self): 
        """
        Update the cursor for this mode.
        """
        
        #self.glpane.setCursor(self.win.SelectAtomsCursor)
        if self._snapOn:
            if self._snapType == 'HORIZONTAL':
                self.glpane.setCursor(self.win.pencilHorizontalSnapCursor)
            elif self._snapType == 'VERTICAL':
                self.glpane.setCursor(self.win.pencilVerticalSnapCursor)
        else:
            self.glpane.setCursor(self.win.colorPencilCursor)
    
    def resetVariables(self):
        """
        Reset instance variables. Typically used by self.command when the 
        command is exited without the graphics mode knowing about it before hand
        Example: You entered line mode, started drawing line, and hit Done 
        button. This exits the Graphics mode (without the 'leftup' which usually
        terminates the command *from Graphics mode') . In the above case, the 
        command.restore_gui needs to tell its graphics mode about what just 
        happened , so that all the assigned values get cleared and ready to use
        next time this graphicsMode is active.
        """
        self.endPoint1 = None
        self.endPoint2 = None
    
    
            
# == Command part

class LineMode(TemporaryCommand_Overdrawing): 
    """
    Encapsulates the LineMode tool functionality.
    """
    # class constants
    
    modename = 'LineMode'
    default_mode_status_text = ""
    hover_highlighting_enabled = True
    GraphicsMode_class = LineMode_GM
    
    # Initial vale for the instance variable. (Note that although it is assigned 
    # an empty tuple, later it is assigned a list.) Empty tuple is just for 
    # the safer implementation than an empty list. Also, it is not 'None' 
    # because in LineMode_GM.bareMotion, it does a check using
    # len(mouseClickPoints)
    mouseClickPoints = ()
    
    def init_gui(self):
        """
        Initialize GUI for this mode 
        """
        prevMode = self.commandSequencer.prevMode        
        #clear the list (for safety) which may still have old data in it
        self.mouseClickPoints = []
        self.glpane.gl_update()
        
        if hasattr(prevMode, 'provideParamsForTemporaryMode'):
            params = prevMode.provideParamsForTemporaryMode(self.modename)
            self.setParams(params)
        return   
    
    def setParams(self, params):
        """
        Assign values obtained from the previouse mode to the instance variables
        of this command object. 
        """
        self.mouseClickLimit = params        
        
    def restore_gui(self):
        """
        Restore the GUI 
        """
        prevMode = self.commandSequencer.prevMode
        if hasattr(prevMode, 'acceptParamsFromTemporaryMode'): 
            prevMode.acceptParamsFromTemporaryMode(
                self.modename, 
                self.mouseClickPoints)
            #clear the list
            self.mouseClickPoints = []       
        
        self.graphicsMode.resetVariables()
       
        return
    
