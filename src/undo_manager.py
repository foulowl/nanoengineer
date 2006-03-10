# Copyright (c) 2005-2006 Nanorex, Inc.  All rights reserved.
'''
undo_manager.py

Own and manage an UndoArchive, feeding it info about user-command events
(such as when to make checkpoints and how to describe the diffs generated by user commands),
and package the undo/redo ops it offers into a reasonable UI.

$Id$

[060117 -- for current status see undo_archive.py module docstring]
'''
__author__ = 'bruce'


from debug import register_debug_menu_command_maker, print_compact_traceback, print_compact_stack
import platform

from undo_archive import AssyUndoArchive #060117 revised
import undo_archive # for debug_undo2
from constants import noop
import env
from HistoryWidget import orangemsg, greenmsg, redmsg, _graymsg
from debug_prefs import debug_pref, Choice_boolean_True, Choice_boolean_False
from qt import SIGNAL
import time

class UndoManager:
    """[abstract class] [060117 addendum: this docstring is mostly obsolete or nim]
    Own and manage an undo-archive, in such a way as to provide undo/redo operations
    and a current-undo-point within the archive [addendum 060117: undo point might be in model objects or archive, not here,
      and since objects can't be in more than one archive or have more than one cur state (at present), this doesn't matter much]
    on top of state-holding objects which would otherwise not have these undo/redo ops
    (though they must have the ability to track changes and/or support scanning of their state).
       Assume that no other UndoManager or UndoArchive is tracking the same state-holding objects
    (i.e. we own them for undo-related purposes).
       #e future: Perhaps also delegate all command-method-calls to the state-holding objects...
    but for now, tolerate external code directly calling command methods on our state-holding objects,
    just receiving begin/end calls related to those commands and their subroutines or calling event-handlers,
    checkpoint calls from same, and undo/redo command callbacks.
    """
    pass

class AssyUndoManager(UndoManager):
    "An UndoManager specialized for handling the state held by an assy (an instance of class assembly)."
    active = True #060223 changed this to True, since False mainly means it died, not that it's being inited [060223]
    inited = False #060223
    def __init__(self, assy, menus = ()): # called from assy.__init__
        """Do what can be done early in assy.__init__; caller must also (subsequently) call init1
        and either _initial_checkpoint or (preferred) clear_undo_stack.
        """
        # assy owns the state whose changes we'll be managing...
        # [semiobs cmt:] should it have same undo-interface as eg chunks do??
        self._current_main_menu_ops = {}
        self.assy = assy
        self.menus = menus
        return

    def init1(self): #e might be merged into end of __init__
        "Do what we might do in __init__ except that it might be too early during assy.__init__ then (see also _initial_checkpoint)"
        assy = self.assy
        self.archive = AssyUndoArchive(assy)
        ## assy._u_archive = self.archive ####@@@@ still safe in 060117 stub code?? [guess 060223: not needed anymore ###@@@]
            # [obs??] this is how model objects in assy find something to report changes to (typically in their __init__ methods);
            # we do it here (not in caller) since its name and value are private to our API for model objects to report changes
##        self.archive.subscribe_to_checkpoints( self.remake_UI_menuitems )
##        self.remake_UI_menuitems() # so it runs for initial checkpoint and disables menu items, etc
        if platform.is_macintosh(): 
            win = assy.w
            win.editRedoAction.setAccel(win._MainWindow__tr("Ctrl+Shift+Z")) # set up incorrectly (for Mac) as "Ctrl+Y"
        self.auto_checkpoint_pref() # exercise this, so it shows up in the debug-prefs submenu right away
            # (fixes bug in which the pref didn't show up until the first undoable change was made) [060125]
        return
    
    def _initial_checkpoint(self): #bruce 060223; not much happens until this is called (order is __init__, init1, _initial_checkpoint)
        "[private]"
        self.archive.initial_checkpoint()
        self.connect_or_disconnect_menu_signals(True)
        self.remake_UI_menuitems() # try to fix bug 1387 [060126]
        self.active = True # redundant
        env.command_segment_subscribers.append( self._in_event_loop_changed )
        self.inited = True
        ## redundant call (bug); i hope this is the right one to remove: self.archive.initial_checkpoint()
        return
    
    def deinit(self):
        self.active = False
        self.connect_or_disconnect_menu_signals(False)
        # and effectively destroy self... [060126 precaution; not thought through]
        self.archive.destroy()
        self._current_main_menu_ops = {}
        self.assy = self.menus = None
        #e more??
        return
    
    def connect_or_disconnect_menu_signals(self, connectQ): # this is a noop as of 060126
        win = self.assy.w
        if connectQ:
            method = win.connect
        else:
            method = win.disconnect
        for menu in self.menus:
            # this is useless, since we have to keep them always up to date for sake of accel keys and toolbuttons [060126]
            ## method( menu, SIGNAL("aboutToShow()"), self.remake_UI_menuitems ) ####k
            pass
        return

    def clear_undo_stack(self, *args, **kws): # this is now callable from a debug menu / other command, as of 060301 (experimental)
        if not self.inited:
            self._initial_checkpoint() # have to do this here, not in archive.clear_undo_stack
        return self.archive.clear_undo_stack(*args, **kws)
    
    def menu_cmd_checkpoint(self): # no longer callable from UI as of 060301, and not recently reviewed for safety [060301 comment]
        self.checkpoint( cptype = 'user_explicit' )

    __begin_retval = None ###k this will be used when we're created by a cmd like file open... i guess grabbing pref then is best...
    
    def _in_event_loop_changed(self, beginflag, tracker): # 060127
        "[this bound method will be added to env.command_segment_subscribers so as to be told when ..."
        # this makes "report all checkpoints" useless -- too many null ones.
        # maybe i should make it only report if state changes or cmdname passed...
        if not self.active:
            self.__begin_retval = False #k probably doesn't matter
            return True # unsubscribe
        # print beginflag, len(tracker.stack) # typical: True 1; False 0
        if beginflag:
            self.__begin_retval = self.undo_checkpoint_before_command()
                ###e grab cmdname guess from top op_run i.e. from begin_op? yes for debugging; doesn't matter in the end though.
        else:
            if self.__begin_retval is None:
                # print "self.__begin_retval is None" # not a bug, will be normal ... happens with file open (as expected)
                self.__begin_retval = self.auto_checkpoint_pref()
            self.undo_checkpoint_after_command( self.__begin_retval )
            self.__begin_retval = False # should not matter
        return
    
    def checkpoint(self, *args, **kws):
        # Note, as of 060127 this is called *much* more frequently than before (for every signal->slot to a python slot);
        # we will need to optimize it when state hasn't changed. ###@@@
        global _AutoCheckpointing_enabled
        opts = dict(merge_with_future = not _AutoCheckpointing_enabled)
            # i.e., when not auto-checkpointing and when caller doesn't override,
            # we'll ask archive.checkpoint to (efficiently) merge changes so far with upcoming changes
            # (but to still cause real changes to trash redo stack, and to still record enough info
            #  to allow us to properly remake_UI_menuitems)
        opts.update(kws) # we'll pass it differently from the manual checkpoint maker... ##e
        res = self.archive.checkpoint( *args, **opts )
        self.remake_UI_menuitems() # needed here for toolbuttons and accel keys; not called for initial cp during self.archive init
            # (though for menu items themselves, the aboutToShow signal would be sufficient)
        return res # maybe no retval, this is just a precaution

    def auto_checkpoint_pref(self): ##e should remove calls to this, inline them as True
        return True # this is obsolete -- it's not the same as the checkmark item now in the edit menu! [bruce 060309]
##        return debug_pref('undo: auto-checkpointing? (slow)', Choice_boolean_True, #bruce 060302 changed default to True, added ':'
##                        prefs_key = 'A7/undo/auto-checkpointing',
##                        non_debug = True)
        
    def undo_checkpoint_before_command(self, cmdname = ""):
        """###doc
        [returns a value which should be passed to undo_checkpoint_after_command;
         we make no guarantees at all about what type of value that is, whether it's boolean true, etc]
        """
        #e should this be renamed begin_cmd_checkpoint() or begin_command_checkpoint() like I sometimes think it's called?
        # recheck the pref every time
        auto_checkpointing = self.auto_checkpoint_pref()
        if not auto_checkpointing:
            return False
        # (everything before this point must be kept fast)
        cmdname2 = cmdname or "command"
        if undo_archive.debug_undo2:
            env.history.message("debug_undo2: begin_cmd_checkpoint for %r" % (cmdname2,))
        # this will get fancier, use cmdname, worry about being fast when no diffs, merging ops, redundant calls in one cmd, etc:
        self.checkpoint( cptype = 'begin_cmd', cmdname_for_debug = cmdname )
        if cmdname:
            self.archive.current_command_info(cmdname = cmdname) #060126
        return True # this code should be passed to the matching undo_checkpoint_after_command (#e could make it fancier)

    def undo_checkpoint_after_command(self, begin_retval):
        assert begin_retval in [False, True], "begin_retval should not be %r" % (begin_retval,)
        if begin_retval:
            # this means [as of 060123] that debug pref for undo checkpointing is enabled
            if undo_archive.debug_undo2:
                env.history.message("  debug_undo2: end_cmd_checkpoint")
            # this will get fancier, use cmdname, worry about being fast when no diffs, merging ops, redundant calls in one cmd, etc:
            self.checkpoint( cptype = 'end_cmd' )
            pass
        return

    def current_command_info(self, *args, **kws):
        self.archive.current_command_info(*args, **kws)
    
    def undo_redo_ops(self):
        # copied code below [dup code is in undo_manager_older.py, not in cvs]
        ops = self.archive.find_undoredos() # state_version - now held inside UndoArchive.last_cp (might be wrong) ###@@@
        undos = []
        redos = []
        d1 = {'Undo':undos, 'Redo':redos}
        for op in ops:
            optype = op.optype()
            d1[optype].append(op) # sort ops by type
        ## done in the subr: redos = filter( lambda redo: not redo.destroyed, redos) #060309 since destroyed ones are not yet unstored
        # remove obsolete redo ops
        if redos:
            lis = [ (redo.cps[1].cp_counter, redo) for redo in redos ]
            lis.sort()
            only_redo = lis[-1][1]
            redos = [only_redo]
            for obs_redo in lis[:-1]:
                if undo_archive.debug_undo2 or env.debug():
                    #060309 adding 'or env.debug()' since this should never happen once clear_redo_stack() is implemented in archive
                    print "obsolete redo:",obs_redo
                pass #e discard it permanently? ####@@@@
        return undos, redos
    
    def undo_cmds_menuspec(self, widget):
        # WARNING: this is not being maintained, it's just a development draft.
        # So far it lacks merging and history message and perhaps win_update and update_select_mode. [060227 comment]
        """return a menu_spec for including undo-related commands in a popup menu
        (to be shown in the given widget, tho i don't know why the widget could matter)
        """
        del widget
        archive = self.archive
        # copied code below [dup code is in undo_manager_older.py, not in cvs]
        res = []

        #bruce 060301 removing this one, since it hasn't been reviewed in awhile so it might cause bugs,
        # and maybe it did cause one...
        ## res.append(( 'undo checkpoint (in RAM only)', self.menu_cmd_checkpoint ))

        #060301 try this one instead:
        res.append(( 'clear undo stack (experimental)', self.clear_undo_stack ))

        undos, redos = self.undo_redo_ops()
        ###e sort each list by some sort of time order (maybe of most recent use of the op in either direction??), and limit lengths
        
        # there are at most one per chunk per undoable attr... so for this test, show them all, don't bother with submenus
        if not undos:
            res.append(( "Nothing we can Undo", noop, 'disabled' ))
                ###e should figure out whether "Can't Undo XXX" or "Nothing to Undo" is more correct
        for op in undos + redos:
            # for now, we're not even including them unless as far as we know we can do them, so no role for "Can't Undo" unless none
            arch = archive # it's on purpose that op itself has no ref to model, so we have to pass it [obs cmt?]
            cmd = lambda _guard1_ = None, _guard2_ = None, arch = arch: arch.do_op(op) #k guards needed? (does qt pass args to menu cmds?)
            ## text = "%s %s" % (op.type, op.what())
            text = op.menu_desc()
            res.append(( text , cmd ))
        if not redos:
            res.append(( "Nothing we can Redo", noop, 'disabled' ))
        return res

    def remake_UI_menuitems(self): #e this should also be called again if any undo-related preferences change ###@@@
        #e see also: void QPopupMenu::aboutToShow () [signal], for how to know when to run this (when Edit menu is about to show);
        # to find the menu, no easy way (only way: monitor QAction::addedTo in a custom QAction subclass - not worth the trouble),
        # so just hardcode it as edit menu for now. We'll need to connect & disconnect this when created/finished,
        # and get passed the menu (or list of them) from the caller, which is I guess assy.__init__.
        if undo_archive.debug_undo2:
            print "debug_undo2: running remake_UI_menuitems (could be direct call or signal)"
        undos, redos = self.undo_redo_ops()
        win = self.assy.w
        undo_mitem = win.editUndoAction
        redo_mitem = win.editRedoAction
        for ops, action, optype in [(undos, undo_mitem, 'Undo'), (redos, redo_mitem, 'Redo')]: #e or could grab op.optype()?
            extra = ""
            if undo_archive.debug_undo2:
                extra = " (%s)" % str(time.time()) # show when it's updated in the menu text (remove when works) ####@@@@
            if ops:
                action.setEnabled(True)
                if not ( len(ops) == 1): #e there should always be just one for now
                    #060212 changed to debug msg, since this assert failed (due to process_events?? undoing esp image delete)
                    print_compact_stack("bug: more than one %s op found: " % optype)
                op = ops[0]
                op = self.wrap_op_with_merging_flags(op) #060127
                text = op.menu_desc() + extra #060126
                action.setMenuText(text)
                fix_tooltip(action, text) # replace description, leave (accelkeys) alone (they contain unicode chars on Mac)
                self._current_main_menu_ops[optype] = op #e should store it into menu item if we can, I suppose
            else:
                action.setEnabled(False)
                ## action.setText("Can't %s" % optype) # someday we might have to say "can't undo Cmdxxx" for certain cmds
                ## action.setMenuText("Nothing to %s" % optype)
                text = "%s" % optype + extra
                action.setMenuText(text) # for 061117 commit, look like it used to look, for the time being
                fix_tooltip(action, text)
                self._current_main_menu_ops[optype] = None
            pass
        #060304 also disable/enable Clear Undo Stack
        action = win.editClearUndoStackAction
        text = "Clear Undo Stack" + '...' # workaround missing '...' (remove this when the .ui file is fixed)
        #e future: add an estimate of RAM to be cleared
        action.setMenuText(text)
        fix_tooltip(action, text)
        enable_it = not not (undos or redos)
        action.setEnabled( enable_it )
        return
        ''' the kinds of things we can set on one of those actions include:
        self.setViewFitToWindowAction.setText(self.__tr("Fit to Window"))
        self.setViewFitToWindowAction.setMenuText(self.__tr("&Fit to Window"))
        self.setViewFitToWindowAction.setToolTip(self.__tr("Fit to Window (Ctrl+F)"))
        self.setViewFitToWindowAction.setAccel(self.__tr("Ctrl+F"))
        self.setViewRightAction.setStatusTip(self.__tr("Right View"))
        self.helpMouseControlsAction.setWhatsThis(self.__tr("Displays help for mouse controls"))
        '''

    def wrap_op_with_merging_flags(self, op, flags = None): #e will also accept merging-flag or -pref arguments
        """Return a higher-level op based on the given op, but with the appropriate diff-merging flags wrapped around it.
        Applying this higher-level op will (in general) apply op, then apply more diffs which should be merged with it
        according to those merging flags (though in an optimized way, e.g. first collect and merge the LL diffs, then apply
        all at once). The higher-level op might also have a different menu_desc, etc.
           In principle, caller could pass flag args, and call us more than one with different flag args for the same op;
        in making the wrapped op we don't modify the passed op.
        """
        #e first we supply our own defaults for flags
        return self.archive.wrap_op_with_merging_flags(op, flags = flags)
    
    # main menu items (their slots in MWsemantics forward to assy which forwards to here)
    def editUndo(self):
        ## env.history.message(orangemsg("Undo: (prototype)"))
        self.do_main_menu_op('Undo')

    def editRedo(self):
        ## env.history.message(orangemsg("Redo: (prototype)"))
        self.do_main_menu_op('Redo')

    def do_main_menu_op(self, optype):
        "optype should be Undo or Redo"
        try:
            op = self._current_main_menu_ops.get(optype)
            if op:
                undo_xxx = op.menu_desc() # note: menu_desc includes history sernos
                env.history.message("%s" % undo_xxx) #e say Undoing rather than Undo in case more msgs??
                self.archive.do_op(op)
                self.assy.w.mt.update_select_mode() #bruce 060227 try to fix bug 1576
                self.assy.w.win_update() #bruce 060227 not positive this isn't called elsewhere, or how we got away without it if not
            else:
                print "no op to %r; not sure how this slot was called, since it should have been disabled" % optype
                env.history.message(redmsg("Nothing to %s (and it's a bug that its menu item or tool button was enabled)" % optype))
            pass
        except:
            print_compact_traceback()
            env.history.message(redmsg("Bug in %s; see traceback in console" % optype))
        return
    
    pass # end of class AssyUndoManager

# ==

#e refile
def fix_tooltip(qaction, text): #060126
    """Assuming qaction's tooltip looks like "command name (accel keys)" and might contain unicode in accel keys
    (as often happens on Mac due to symbols for Shift and Command modifier keys),
    replace command name with text, leave accel keys unchanged (saving result into actual tooltip).
       OR if the tooltip doesn't end with ')', just replace the entire thing with text, plus a space if text ends with ')'
    (to avoid a bug the next time -- not sure if that kluge will work).
    """
    whole = unicode(qaction.toolTip()) # str() on this might have an exception
    try:
        #060304 improve the alg to permit parens in text to remain; assume last '( ' is the one before the accel keys;
        # also permit no accel keys
        if whole[-1] == ')':
            # has accel keys (reasonable assumption, not unbreakably certain)
            sep = u' ('
            parts = whole.split(sep)
            parts = [text, parts[-1]]
            whole = sep.join(parts)
        else:
            # has no accel keys
            whole = text
            if whole[-1] == ')':
                whole = whole + ' ' # kluge, explained in docstring
            pass
        # print "formed tooltip",`whole` # printing whole might have an exception, but printing `whole` is ok
        qaction.setToolTip(whole) # no need for __tr, I think?
    except:
        print_compact_traceback("exception in fix_tooltip(%r, %r): " % (qaction, text) )
    return

# == debugging code - invoke undo/redo from debug menu (only) in initial test implem

def undo_cmds_maker(widget):
    ###e maybe this belongs in assy module itself?? clue: it knows the name of assy.undo_manager; otoh, should work from various widgets
    "[widget is the widget in which the debug menu is being put up right now]"
    #e in theory we use that widget's undo-chain... but in real life this won't even happen inside the debug menu, so nevermind.
    # for now just always use the assy's undo-chain.
    # hmm, how do we find the assy? well, ok, i'll use the widget.
    try:
        assy = widget.win.assy
    except:
        import platform
        if platform.atom_debug:
            return [('atom_debug: no undo in this widget', noop, 'disabled')]
        return []
##    if 'kluge' and not hasattr(assy, 'undo_manager'):
##        assy.undo_manager = UndoManager(assy) #e needs review; might just be a devel kluge, or might be good if arg type is unciv
    mgr = assy.undo_manager #k should it be an attr like this, or a sep func?
    return mgr.undo_cmds_menuspec(widget)

register_debug_menu_command_maker( "undo_cmds", undo_cmds_maker)
    # fyi: this runs once when the first assy is being created, but undo_cmds_maker runs every time the debug menu is put up.

# ==

# Undo-related main menu commands other than Undo/Redo themselves

_AutoCheckpointing_enabled = True
    #e this might be revised to look at env.prefs sometime during app startup,
    # and to call editAutoCheckpointing (or some part of it) with the proper initial state;
    # the current code is designed, internally, for checkpointing to be enabled except
    # for certain intervals, so we might start out True and set this to False when
    # an undo_manager is created... we'll see; maybe it won't even (or mainly or only) be a global? [060309]

def editMakeCheckpoint():
    '''This is called from MWsemantics.editMakeCheckpoint, which is documented as
    "Slot for making a checkpoint (only available when Automatic Checkpointing is disabled)."
    '''
    env.history.message("Make Checkpoint: Not implemented yet.")
    return

def editAutoCheckpointing(enabled):
    '''This is called from MWsemantics.editClearUndoStack, which is documented as
    "Slot for enabling/disabling automatic checkpointing."
       This has only UI effects (including editMakeCheckpointAction.setVisible),
    other than setting the global _AutoCheckpointing_enabled.
    '''
    win = env.mainwindow() #k should this and/or assy be an argument instead?
    global _AutoCheckpointing_enabled
    _AutoCheckpointing_enabled = not not enabled
    if enabled:
        msg_short = "Autocheckpointing enabled"
        msg_long  = "Autocheckpointing enabled -- each operation will be undoable"
    else:
        msg_short = "Autocheckpointing disabled"
        msg_long  = "Autocheckpointing disabled -- only explicit Undo checkpoints are kept" #k length ok?
    env.history.message(greenmsg(msg_short) + orangemsg(" [not yet fully implemented]")) #######@@@@@@@
    env.history.statusbar_msg(msg_long)
    win.editMakeCheckpointAction.setVisible(not enabled)
    return

def editClearUndoStack(): #bruce 060304, modified from Mark's prototype in MWsemantics
    '''called from MWsemantics.editClearUndoStack, which is documented as a
       "Slot for clearing the Undo Stack.  Requires the user to confirm."
    '''
##    if not env.debug():
##        env.history.message("Clear Undo Stack: Not implemented yet.")
##        return
##    #e in real life, no message is needed until after the confirmation dialog, i think... not sure
##    env.history.message("Clear Undo Stack: ATOM_DEBUG set, so using unfinished draft of real code (which doesn't free any RAM)")
    #e the following message should specify the amount of data to be lost... #e and the menu item text also should
    msg = "Please confirm that you want to clear the Undo/Redo Stack.<br>" + _graymsg("(This operation cannot be undone.)")
    from widgets import PleaseConfirmMsgBox ###e I bet this needs a "don't show this again" checkbox... with a prefs key...
    confirmed = PleaseConfirmMsgBox( msg)
    if not confirmed:
        env.history.message("Clear Undo Stack: Cancelled.") #k needed??
        return
    # do it
    env.history.message(greenmsg("Clear Undo Stack")) # no further message needed if it works, I think
    try:
        ##e Note: the following doesn't actually free storage. [update, 060309 -- i think as of a few days ago it does try to... ##k]
        # Once the UI seems to work, we'll either add that to it,
        # or destroy and remake assy.undo_manager itself before doing this (and make sure destroying it frees storage).
        ##e Make sure this can be called with or without auto-checkpointing enabled, and leaves that setting unchanged. #####@@@@@
        env.mainwindow().assy.clear_undo_stack()
             #k should win and/or assy be an argument instead?
    except:
        print_compact_traceback("exception in clear_undo_stack: ")
        env.history.message(redmsg("Internal error in Clear Undo Stack. Undo/Redo might be unsafe until a new file is opened."))
            #e that wording assumes we can't open more than one file at a time...
    return
# bugs in editClearUndoStack [some fixed, as indicated, as of 060304 1132pm PST]:
# cosmetic:
# + [worked around in this code, for now] '...' needed in menu text;
# + [fixed] need to disable it when undo/redo stack empty;
# - it ought to have ram estimate in menu text;
# - "don't show again" checkbox might be needed
# - does the dialog (or menu item if it doesn't have one) need a wiki help link?
# - dialog starts out too narrow
# - when Undo is disabled at the point where stack was cleared, maybe text should say it was cleared? "Undo stack cleared (%d.)" ???
# major:
# + [fixed] doesn't attempt to free RAM
# + [fixed] doesn't work: it doesn't update the Undo action (or, didn't clear the stack)...
#   hmm, it totally failed to work, it was even an "operation" on the undo stack itself, and so was the prior "deposit atom"
#   Theory about that bug: self.current_diff.suppress_storing_undo_redo_ops = True only matters if the varid_vers differed
#   across that diff, but they don't in this case since there was no real change and this is detected.
#   Possible fixes:
#   - make a fake change
#   - set another flag and behave differently
#   + [did this one, though it was harder than it initially seemed]
#     actually implement the freeing of all stored ops, which can't be that hard given that it's easy to tell which ones to free --
#     *all* of them! guess: stored_ops.clear(), in archive, in all calls of clear_undo_stack.


# end
