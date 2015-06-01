#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Copyright (C) 2007-2014 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2015 Martin Wimpress <code@ubuntu-mate.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.

__VERSION__='5.6.5a'

import ctypes
import gc
import gi
import gettext
import os
import platform
import subprocess
import sys
import traceback

gi.require_version("Gtk", "2.0")

from ctypes import *
from gi.repository import Gtk, GdkPixbuf, Gdk, GObject
from gi.repository import MatePanelApplet
from gi.repository import Gio

try:
    import xdg.Config
    import mate_menu.keybinding as keybinding
    import mate_menu.pointerMonitor as pointerMonitor
except Exception, e:
    print e
    sys.exit( 1 )

GObject.threads_init()

gdk = CDLL("libgdk-x11-2.0.so.0")

# Rename the process
architecture = platform.uname()[4]
if architecture in 'x86_64':
    libc = CDLL('libc.so.6')
    libc.prctl(15, 'mate-menu', 0, 0, 0)
else:
    import dl
    if os.path.exists('/lib/libc.so.6'):
        libc = dl.open('/lib/libc.so.6')
        libc.call('prctl', 15, 'mate-menu', 0, 0, 0)
    elif os.path.exists('/lib/i386-linux-gnu/libc.so.6'):
        libc = dl.open('/lib/i386-linux-gnu/libc.so.6')
        libc.call('prctl', 15, 'mate-menu', 0, 0, 0)

# i18n
gettext.install("mate-menu", "/usr/share/locale")

NAME = _("Menu")

xdg.Config.setWindowManager('MATE')

from mate_menu.execute import *

class MainWindow( object ):
    """This is the main class for the application"""

    def __init__( self, toggleButton, settings, keybinder ):

        self.settings = settings
        self.keybinder = keybinder
        self.data_path = os.path.join( '/', 'usr', 'share', 'mate-menu' )
        self.icon = "/usr/share/mate-menu/icons/mate-logo.svg"

        self.toggle = toggleButton
        # Load UI file and extract widgets   
        builder = Gtk.Builder()
        builder.add_from_file(os.path.join( self.data_path, "mate-menu.glade" ))
        self.window     = builder.get_object( "mainWindow" )
        self.paneholder = builder.get_object( "paneholder" )
        self.border     = builder.get_object( "border" )

        builder.connect_signals(self)

        self.panesToColor = [ ]
        self.headingsToColor = [ ]

        self.window.connect( "key-press-event", self.onKeyPress )
        self.window.connect( "focus-in-event", self.onFocusIn )
        self.loseFocusId = self.window.connect( "focus-out-event", self.onFocusOut )
        self.loseFocusBlocked = False

        self.window.stick()

        plugindir = os.path.join( os.path.expanduser( "~" ), ".config/mate-menu/plugins" )
        sys.path.append( plugindir )

        self.panelSettings = Gio.Settings.new("org.mate.panel")
        self.panelSettings.connect( "changed::tooltips-enabled", self.toggleTooltipsEnabled )

        self.settings.connect( "changed::plugins-list", self.RegenPlugins )
        self.settings.connect( "changed::start-with-favorites", self.toggleStartWithFavorites )
        self.settings.connect( "changed::tooltips-enabled", self.toggleTooltipsEnabled )
        self.settings.connect( "changed::use-custom-color", self.toggleUseCustomColor )
        self.settings.connect( "changed::custom-border-color", self.toggleCustomBorderColor )
        self.settings.connect( "changed::custom-heading-color", self.toggleCustomHeadingColor )
        self.settings.connect( "changed::custom-color", self.toggleCustomBackgroundColor )
        self.settings.connect( "changed::border-width", self.toggleBorderWidth )
        self.settings.connect( "changed::opacity", self.toggleOpacity )

        self.getSetGSettingEntries()

        self.tooltips = Gtk.Tooltips()
        if self.globalEnableTooltips and self.enableTooltips:
            self.tooltips.enable()
        else:
            self.tooltips.disable()

        self.PopulatePlugins();
        self.firstTime = True;

    def on_window1_destroy (self, widget, data=None):
        Gtk.main_quit()
        sys.exit(0)

    def wakePlugins( self ):
        # Call each plugin and let them know we're showing up
        for plugin in self.plugins.values():
            if hasattr( plugin, "wake" ):
                plugin.wake()

    def toggleTooltipsEnabled( self, settings, key, args = None):
        if key == "tooltips-enabled":
            self.globalEnableTooltips = settings.get_boolean(key)
        else:
            self.enableTooltips = settings.get_boolean(key)

        if self.globalEnableTooltips and self.enableTooltips:
            self.tooltips.enable()
        else:
            self.tooltips.disable()

    def toggleStartWithFavorites( self, settings, key, args = None ):
        self.startWithFavorites = settings.get_boolean(key)

    def toggleBorderWidth( self, settings, key,  args = None ):
        self.borderwidth = settings.get_int(key)
        self.SetupMateMenuBorder()

    def toggleOpacity( self, settings, key, args = None ):
        self.opacity = settings.get_int(key)
        self.SetupMateMenuOpacity()

    def toggleUseCustomColor( self, settings, key, args = None ):
        self.usecustomcolor = settings.get_boolean(key)
        self.loadTheme()

    def toggleCustomBorderColor( self, settings, key, args = None ):
        self.custombordercolor = settings.get_string(key)
        self.SetupMateMenuBorder()

    def toggleCustomBackgroundColor( self, settings, key, args = None):
        self.customcolor = settings.get_string(key)
        self.SetPaneColors( self.panesToColor )

    def toggleCustomHeadingColor( self, settings, key, args = None ):
        self.customheadingcolor = settings.get_string(key)
        self.SetHeadingStyle( self.headingsToColor )

    def getSetGSettingEntries( self ):        
        self.pluginlist           = self.settings.get_strv( "plugins-list" )
        self.usecustomcolor       = self.settings.get_boolean( "use-custom-color" )
        self.customcolor          = self.settings.get_string( "custom-color" )
        self.customheadingcolor   = self.settings.get_string( "custom-heading-color" )
        self.custombordercolor    = self.settings.get_string( "custom-border-color" )
        self.borderwidth          = self.settings.get_int( "border-width" )
        self.opacity              = self.settings.get_int( "opacity" )
        self.offset               = self.settings.get_int( "offset" )        
        self.enableTooltips       = self.settings.get_boolean( "tooltips-enabled" )
        self.startWithFavorites   = self.settings.get_boolean( "start-with-favorites" )

        self.globalEnableTooltips = self.panelSettings.get_boolean( "tooltips-enabled" )

    def SetupMateMenuBorder( self, defaultStyle = None ):
        if self.usecustomcolor:
            self.window.modify_bg( Gtk.StateType.NORMAL, Gdk.color_parse( self.custombordercolor ) )
        elif defaultStyle is not None:
            self.window.modify_bg( Gtk.StateType.NORMAL, defaultStyle.lookup_color('bg_color')[1] )
        self.border.set_padding( self.borderwidth, self.borderwidth, self.borderwidth, self.borderwidth )

    def SetupMateMenuOpacity( self ):
        print "Opacity is: " + str(self.opacity)
        opacity = float(self.opacity) / float(100)
        print "Setting opacity to: " + str(opacity)
        if opacity is not 1:
            self.window.set_opacity(opacity)

    def PopulatePlugins( self ):
        self.panesToColor = [ ]
        self.headingsToColor = [ ]
        PluginPane = Gtk.EventBox()
        PluginPane.show()
        PaneLadder = Gtk.VBox( False, 0 )
        PluginPane.add( PaneLadder )
        ImageBox = Gtk.EventBox()
        ImageBox.show()
        self.panesToColor.extend( [ PluginPane, ImageBox ] )

        self.plugins = {}

        for plugin in self.pluginlist:
            if plugin in self.plugins:
                print u"Duplicate plugin in list: ", plugin
                continue

            if plugin != "newpane":
                try:
                    plugin_module = 'mate_menu.plugins.{plugin}'.format(plugin=plugin)
                    exec("from {plugin_module} import pluginclass".format(plugin_module=plugin_module))
                    # If no parameter passed to plugin it is autonomous
                    if pluginclass.__init__.func_code.co_argcount == 1:
                        MyPlugin = pluginclass()
                    else:
                        # pass mateMenu and togglebutton instance so that the plugin can use it
                        MyPlugin = pluginclass(self, self.toggle)

                    if not MyPlugin.icon:
                        MyPlugin.icon = "mate-logo-icon.png"

                    #if hasattr( MyPlugin, "hideseparator" ) and not MyPlugin.hideseparator:
                    #    Image1 = Gtk.Image()
                    #    Image1.set_from_pixbuf( seperatorImage )
                    #    if not ImageBox.get_child():
                    #        ImageBox.add( Image1 )
                    #        Image1.show()

                    #print u"Loading plugin '" + plugin + "' : sucessful"
                except Exception, e:
                    MyPlugin = Gtk.EventBox() #Fake class for MyPlugin
                    MyPlugin.heading = _("Couldn't load plugin:") + " " + plugin
                    MyPlugin.content_holder = Gtk.EventBox()

                    # create traceback
                    info = sys.exc_info()

                    errorLabel = Gtk.Label( "\n".join(traceback.format_exception( info[0], info[1], info[2] )).replace("\\n", "\n") )
                    errorLabel.set_selectable( True )
                    errorLabel.set_line_wrap( True )
                    errorLabel.set_alignment( 0.0, 0.0 )
                    errorLabel.set_padding( 5, 5 )
                    errorLabel.show()

                    MyPlugin.content_holder.add( errorLabel )
                    MyPlugin.add( MyPlugin.content_holder )
                    MyPlugin.width = 270
                    MyPlugin.icon = 'mate-logo-icon.png'
                    print u"Unable to load " + plugin + " plugin :-("


                self.panesToColor.append( MyPlugin.content_holder )
                MyPlugin.content_holder.show()

                VBox1 = Gtk.VBox( False, 0 )
                if MyPlugin.heading != "":
                    Label1 = Gtk.Label(label= MyPlugin.heading )
                    Align1 = Gtk.Alignment.new( 0, 0, 0, 0 )
                    Align1.set_padding( 10, 5, 10, 0 )
                    Align1.add( Label1 )
                    self.headingsToColor.append( Label1 )
                    Align1.show()
                    Label1.show()

                    if not hasattr( MyPlugin, 'sticky' ) or MyPlugin.sticky == True:
                        heading = Gtk.EventBox()
                        Align1.set_padding( 0, 0, 10, 0 )
                        heading.set_visible_window( False )
                        heading.set_size_request( MyPlugin.width, 30 )
                    else:
                        heading = Gtk.HBox()
                        #heading.set_relief( Gtk.ReliefStyle.NONE )
                        heading.set_size_request( MyPlugin.width, -1 )
                        #heading.set_sensitive(False)
                        #heading.connect( "button_press_event", self.TogglePluginView, VBox1, MyPlugin.icon, MyPlugin.heading, MyPlugin )

                    heading.add( Align1 )
                    heading.show()
                    VBox1.pack_start( heading, False, False, 0 )                    
                VBox1.show()
                #Add plugin to Plugin Box under heading button
                MyPlugin.content_holder.reparent( VBox1 )

                #Add plugin to main window
                PaneLadder.pack_start( VBox1 , True, True, 0)
                PaneLadder.show()

                if MyPlugin.window:
                    MyPlugin.window.destroy()

                try:
                    if hasattr( MyPlugin, 'do_plugin' ):
                        MyPlugin.do_plugin()
                    if hasattr( MyPlugin, 'height' ):
                        MyPlugin.content_holder.set_size_request( -1, MyPlugin.height )
                    if hasattr( MyPlugin, 'itemstocolor' ):
                        self.panesToColor.extend( MyPlugin.itemstocolor )
                    if hasattr( MyPlugin, 'headingstocolor' ):
                        self.headingsToColor.extend( MyPlugin.headingstocolor )
                except:
                    # create traceback
                    info = sys.exc_info()

                    error = _("Couldn't initialize plugin") + " " + plugin + " : " + "\n".join(traceback.format_exception( info[0], info[1], info[2] )).replace("\\n", "\n")
                    msgDlg = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, error )
                    msgDlg.run();
                    msgDlg.destroy();

                self.plugins[plugin] = MyPlugin

            else:
                self.paneholder.pack_start( ImageBox, False, False, 0 )
                self.paneholder.pack_start( PluginPane, False, False, 0 )
                PluginPane = Gtk.EventBox()
                PaneLadder = Gtk.VBox( False, 0 )
                PluginPane.add( PaneLadder )
                ImageBox = Gtk.EventBox()
                self.panesToColor.extend( [ PluginPane, ImageBox ] )
                ImageBox.show()
                PluginPane.show_all()

                if self.plugins and hasattr( MyPlugin, 'hideseparator' ) and not MyPlugin.hideseparator:
                    Image1 = Gtk.Image()
                    Image1.set_from_pixbuf( seperatorImage )
                    Image1.show()
                    #ImageBox.add( Image1 )

                    Align1 = Gtk.Alignment.new(0, 0, 0, 0)
                    Align1.set_padding( 0, 0, 6, 6 )
                    Align1.add(Image1)
                    ImageBox.add(Align1)
                    ImageBox.show_all()


        self.paneholder.pack_start( ImageBox, False, False, 0 )
        self.paneholder.pack_start( PluginPane, False, False, 0 )
        self.tooltips.disable()

    # A little hacky but works
    def getDefaultStyle( self ):
        widget = Gtk.EventBox()
        widget.show()
        return Gtk.rc_get_style(widget)

    def loadTheme( self ):
        defaultStyle = self.getDefaultStyle()
        self.SetPaneColors( self.panesToColor, defaultStyle )
        self.SetupMateMenuBorder( defaultStyle )
        self.SetHeadingStyle( self.headingsToColor )

    def SetPaneColors( self, items, defaultStyle = None ):
        if self.usecustomcolor:
            for item in items:
                item.modify_bg( Gtk.StateType.NORMAL, Gdk.color_parse( self.customcolor ) )
                # TODO: Changing background color isn't working for pixmaps! The following does not work:
                item.get_style().bg_pixmap[Gtk.StateType.NORMAL] = None
        elif defaultStyle is not None:
            for item in items:
                item.modify_bg( Gtk.StateType.NORMAL, defaultStyle.lookup_color('bg_color')[1] )
                item.get_style().bg_pixmap[Gtk.StateType.NORMAL] = defaultStyle.bg_pixmap[Gtk.StateType.NORMAL]

    def SetHeadingStyle( self, items ):
        if self.usecustomcolor:
            color = self.customheadingcolor
        else:
            color = None

        for item in items:
            item.set_use_markup(True)
            text = item.get_text()
            if color == None:
                markup = '<span size="12000" weight="bold">%s</span>' % (text)
            else:
                markup = '<span size="12000" weight="bold" color="%s">%s</span>' % (color, text)
            item.set_markup( markup )

    def setTooltip( self, widget, tip, tipPrivate = None ):
        self.tooltips.set_tip( widget, tip, tipPrivate )

    def RegenPlugins( self, *args, **kargs ):
        #print
        #print u"Reloading Plugins..."
        for item in self.paneholder:
            item.destroy()

        for plugin in self.plugins.values():
            if hasattr( plugin, "destroy" ):
                plugin.destroy()

        try:
            del plugin
        except:
            pass

        try:
            del self.plugins
        except:
            pass

        gc.collect()

        self.getSetGSettingEntries()
        self.PopulatePlugins()
        self.loadTheme()

        #print NAME+u" reloaded"

    def onKeyPress( self, widget, event ):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def show( self ):
        self.window.present()

        # Hack for opacity not showing on first composited draw
        if self.firstTime:
            self.firstTime = False
            self.SetupMateMenuOpacity()

        self.window.window.focus( Gdk.CURRENT_TIME )

        for plugin in self.plugins.values():
            if hasattr( plugin, "onShowMenu" ):
                plugin.onShowMenu()

        if ( "applications" in self.plugins ) and ( hasattr( self.plugins["applications"], "focusSearchEntry" ) ):
            if (self.startWithFavorites):
                self.plugins["applications"].changeTab(0)
            self.plugins["applications"].focusSearchEntry()

    def hide( self ):
        for plugin in self.plugins.values():
            if hasattr( plugin, "onHideMenu" ):
                plugin.onHideMenu()

        self.window.hide()

    def onFocusIn( self, *args ):
        if self.loseFocusBlocked:
            self.window.handler_unblock( self.loseFocusId )
            self.loseFocusBlocked = False

        return False  

    def onFocusOut( self, *args):            
        if self.window.get_visible():
            self.hide()
        return False

    def stopHiding( self ):
        if not self.loseFocusBlocked:
            self.window.handler_block( self.loseFocusId )
            self.loseFocusBlocked = True

class MenuWin( object ):
    def __init__( self, applet, iid ):
        self.data_path = os.path.join('/','usr','share','mate-menu')
        self.applet = applet        
        self.settings = Gio.Settings.new("org.mate.mate-menu")
        self.keybinder = keybinding.GlobalKeyBinding()
        self.settings.connect( "changed::applet-text", self.reloadSettings )
        self.settings.connect( "changed::theme-name", self.changeTheme )
        self.settings.connect( "changed::hot-key", self.reloadSettings )
        self.settings.connect( "changed::applet-icon", self.reloadSettings )
        self.settings.connect( "changed::hide-applet-icon", self.reloadSettings )
        self.settings.connect( "changed::applet-icon-size", self.reloadSettings )
        self.settings.connect( "changed::hot-key", self.hotkeyChanged )
        self.loadSettings()

        self.mate_settings = Gio.Settings.new("org.mate.interface")
        self.mate_settings.connect( "changed::gtk-theme", self.changeTheme )

        self.createPanelButton()

        self.applet.set_flags( MatePanelApplet.AppletFlags.EXPAND_MINOR )
        self.applet.connect( "button-press-event", self.showMenu )
        self.applet.connect( "change-orient", self.changeOrientation )        
        self.applet.connect("enter-notify-event", self.enter_notify)
        self.applet.connect("leave-notify-event", self.leave_notify)
        self.mainwin = MainWindow( self.button_box, self.settings, self.keybinder )
        self.mainwin.window.connect( "map-event", self.onWindowMap )
        self.mainwin.window.connect( "unmap-event", self.onWindowUnmap )
        self.mainwin.window.connect( "realize", self.onRealize )
        self.mainwin.window.connect( "size-allocate", lambda *args: self.positionMenu() )

        self.mainwin.window.set_name("mate-menu") # Name used in Gtk RC files
        self.applyTheme()
        self.mainwin.loadTheme()

        if self.mainwin.icon:
            Gtk.Window.set_default_icon_name( self.mainwin.icon )

        self.bind_hot_key()
        self.applet.set_can_focus(False)

        self.pointerMonitor = pointerMonitor.PointerMonitor()
        self.pointerMonitor.connect("activate", self.onPointerOutside)

    def onWindowMap( self, *args ):
        self.applet.set_state( Gtk.StateType.SELECTED )
        self.keybinder.set_focus_window( self.mainwin.window.window )
        self.pointerMonitor.grabPointer()
        return False

    def onWindowUnmap( self, *args ):
        self.applet.set_state( Gtk.StateType.NORMAL )
        self.keybinder.set_focus_window()
        self.pointerMonitor.ungrabPointer()
        return False

    def onRealize( self, *args):
        self.pointerMonitor.addWindowToMonitor( self.mainwin.window.window )
        self.pointerMonitor.addWindowToMonitor( self.applet.window )
        self.pointerMonitor.start()
        return False

    def onPointerOutside(self, *args):
        self.mainwin.hide()
        return True

    def onBindingPress(self, binder):
        self.toggleMenu()
        return True

    def enter_notify(self, applet, event):
        self.do_image(self.buttonIcon, True)

    def leave_notify(self, applet, event):
		# Hack for mate-panel-test-applets focus issue (this can be commented)
        if event.state & Gdk.ModifierType.BUTTON1_MASK and applet.state & Gtk.StateType.SELECTED:
            if event.x >= 0 and event.y >= 0 and event.x < applet.window.get_width() and event.y < applet.window.get_height():
                self.mainwin.stopHiding()

        self.do_image(self.buttonIcon, False)

    def do_image(self, image_file, saturate):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_file)
        if saturate:
            GdkPixbuf.Pixbuf.saturate_and_pixelate(pixbuf, pixbuf, 1.5, False)
        self.button_icon.set_from_pixbuf(pixbuf)

    def createPanelButton( self ):
        self.button_icon = Gtk.Image.new_from_file( self.buttonIcon )
        self.systemlabel = Gtk.Label(label= self.buttonText )
        process = subprocess.Popen(['lsb_release', '-d'], stdout=subprocess.PIPE)
        out, err = process.communicate()
        tooltip = out.replace('Description:', '').strip()
        self.systemlabel.set_tooltip_text(tooltip)
        self.button_icon.set_tooltip_text(tooltip)
        if self.applet.get_orient() == MatePanelApplet.AppletOrient.UP or self.applet.get_orient() == MatePanelApplet.AppletOrient.DOWN:
            self.button_box = Gtk.HBox()
            self.button_box.pack_start( self.button_icon, False, False, 0 )
            self.button_box.pack_start( self.systemlabel, False, False, 0 )
            self.button_icon.set_padding( 5, 0 )
        # if we have a vertical panel
        elif self.applet.get_orient() == MatePanelApplet.AppletOrient.LEFT:
            self.button_box = Gtk.VBox()
            self.systemlabel.set_angle( 270 )
            self.button_box.pack_start( self.button_icon , False, False, 0)
            self.button_box.pack_start( self.systemlabel , False, False, 0)
            self.button_icon.set_padding( 0, 5 )
        elif self.applet.get_orient() == MatePanelApplet.AppletOrient.RIGHT:
            self.button_box = Gtk.VBox()
            self.systemlabel.set_angle( 90 )
            self.button_box.pack_start( self.systemlabel , False, False, 0)
            self.button_box.pack_start( self.button_icon , False, False, 0)
            self.button_icon.set_padding( 0, 5 )

        self.button_box.set_homogeneous( False )
        self.button_box.show_all()
        self.sizeButton()

        self.applet.add( self.button_box )
        self.applet.set_background_widget( self.applet )


    def loadSettings( self, *args, **kargs ):
        self.hideIcon   =  self.settings.get_boolean( "hide-applet-icon" )
        self.buttonText =  self.settings.get_string( "applet-text" )
        self.theme_name =  self.settings.get_string( "theme-name" )
        self.hotkeyText =  self.settings.get_string( "hot-key" )
        self.buttonIcon =  self.settings.get_string( "applet-icon" )
        self.iconSize = self.settings.get_int( "applet-icon-size" )    

    def changeTheme(self, *args):        
        self.reloadSettings()
        self.applyTheme()
        self.mainwin.loadTheme()

    def applyTheme(self):
        style_settings = Gtk.Settings.get_default()
        desktop_theme = self.mate_settings.get_string('gtk-theme')
        if self.theme_name == "default":
            style_settings.set_property("gtk-theme-name", desktop_theme)        
        else:
            try:
                style_settings.set_property("gtk-theme-name", self.theme_name)
            except:
                style_settings.set_property("gtk-theme-name", desktop_theme)            

    def changeOrientation( self, *args, **kargs ):

        if self.applet.get_orient() == MatePanelApplet.AppletOrient.UP or self.applet.get_orient() == MatePanelApplet.AppletOrient.DOWN:
            tmpbox = Gtk.HBox()
            self.systemlabel.set_angle( 0 )
            self.button_box.reorder_child( self.button_icon, 0 )
            self.button_icon.set_padding( 5, 0 )
        elif self.applet.get_orient() == MatePanelApplet.AppletOrient.LEFT:
            tmpbox = Gtk.VBox()
            self.systemlabel.set_angle( 270 )
            self.button_box.reorder_child( self.button_icon, 0 )
            self.button_icon.set_padding( 0, 5 )
        elif self.applet.get_orient() == MatePanelApplet.AppletOrient.RIGHT:
            tmpbox = Gtk.VBox()
            self.systemlabel.set_angle( 90 )
            self.button_box.reorder_child( self.button_icon, 1 )
            self.button_icon.set_padding( 0, 5 )

        tmpbox.set_homogeneous( False )

        # reparent all the hboxes to the new tmpbox
        for i in self.button_box:
            i.reparent( tmpbox )

        self.button_box.destroy()

        self.button_box = tmpbox
        self.button_box.show()

        # this call makes sure width stays intact
        self.updateButton()
        self.applet.add( self.button_box )


    def updateButton( self ):
        self.systemlabel.set_text( self.buttonText )
        self.button_icon.clear()
        self.button_icon.set_from_file( self.buttonIcon )
        self.sizeButton()

    def bind_hot_key (self):
        try:
            if self.hotkeyText != "":
                self.keybinder.grab( self.hotkeyText )
            self.keybinder.connect("activate", self.onBindingPress)
            self.keybinder.start()
            # Binding menu to hotkey
            print "Binding to Hot Key: " + self.hotkeyText

        except Exception, cause:
            print "** WARNING ** - Menu Hotkey Binding Error"
            print "Error Report :\n", str(cause)
            pass

    def hotkeyChanged (self, schema, key):
        self.hotkeyText =  self.settings.get_string( "hot-key" )
        self.keybinder.rebind(self.hotkeyText)

    def sizeButton( self ):
        if self.hideIcon:
            self.button_icon.hide()
        else:
            self.button_icon.show()
     #   This code calculates width and height for the button_box
     #   and takes the orientation in account
        sl_req = Gtk.Requisition()
        bi_req = Gtk.Requisition()
        self.button_icon.size_request(bi_req)
        self.systemlabel.size_request(sl_req)
        if self.applet.get_orient() == MatePanelApplet.AppletOrient.UP or self.applet.get_orient() == MatePanelApplet.AppletOrient.DOWN:
            if self.hideIcon:
                self.applet.set_size_request( sl_req.width + 2, bi_req.height )
            else:
                self.applet.set_size_request( sl_req.width + bi_req.width + 5, bi_req.height )
        else:
            if self.hideIcon:
                self.applet.set_size_request( bi_req.width, sl_req.height + 2 )
            else:
                self.applet.set_size_request( bi_req.width, sl_req.height + bi_req.height + 5 )

    def reloadSettings( self, *args ):
        self.loadSettings()
        self.updateButton()        

    def showAboutDialog( self, action, userdata = None ):
        about = Gtk.AboutDialog()
        about.set_name("MATE Menu")
        about.set_version(__VERSION__)
        about.set_comments( _("Advanced MATE Menu") )
        about.set_logo( GdkPixbuf.Pixbuf.new_from_file("/usr/share/mate-menu/icons/mate-logo.svg") )
        about.connect( "response", lambda dialog, r: dialog.destroy() )
        about.show()

    def showPreferences( self, action, userdata = None ):
        Execute( os.path.join( "/", "usr", "lib", "mate-menu", "mate-menu-config.py" ) )

    def showMenuEditor( self, action, userdata = None ):
        Execute( "mozo" )

    def showMenu( self, widget=None, event=None ):
        if event == None or event.button == 1:
            self.toggleMenu()
        # show right click menu
        elif event.button == 3:
            self.create_menu()
        # allow middle click and drag
        elif event.button == 2:
            self.mainwin.hide()

    def toggleMenu( self ):
        if self.applet.state & Gtk.StateType.SELECTED:
            self.mainwin.hide()
        else:
            self.positionMenu()
            self.mainwin.show()
            self.wakePlugins()

    def wakePlugins( self ):
        self.mainwin.wakePlugins()

    def positionMenu( self ):
        # Get our own dimensions & position
        ourWidth  = self.mainwin.window.get_size()[0]
        ourHeight = self.mainwin.window.get_size()[1] + self.mainwin.offset

        x = c_int()
        y = c_int()
        # Get the dimensions/position of the widgetToAlignWith
        gdk.gdk_window_get_origin(hash(self.applet.window), byref(x), byref(y))
        entryX = x.value
        entryY = y.value

        entryWidth, entryHeight =  self.applet.get_allocation().width, self.applet.get_allocation().height
        entryHeight = entryHeight + self.mainwin.offset

        # Get the screen dimensions
        screenHeight = Gdk.Screen.height()
        screenWidth = Gdk.Screen.width()
        if self.applet.get_orient() == MatePanelApplet.AppletOrient.UP or self.applet.get_orient() == MatePanelApplet.AppletOrient.DOWN:
            if entryX + ourWidth < screenWidth or  entryX + entryWidth / 2 < screenWidth / 2:
            # Align to the left of the entry
                newX = entryX
            else:
                # Align to the right of the entry
                newX = entryX + entryWidth - ourWidth

            if entryY + entryHeight / 2 < screenHeight / 2:
                # Align to the bottom of the entry
                newY = entryY + entryHeight
            else:
                newY = entryY - ourHeight
        else:
            if entryX + entryWidth / 2 < screenWidth / 2:
                # Align to the left of the entry
                newX = entryX + entryWidth
            else:
                # Align to the right of the entry
                newX = entryX - ourWidth

            if entryY + ourHeight < screenHeight or entryY + entryHeight / 2 < screenHeight / 2:
                # Align to the bottom of the entry
                newY = entryY
            else:
                newY = entryY - ourHeight + entryHeight
        # -"Move window"
        self.mainwin.window.move( newX, newY )

    # this callback is to create a context menu
    def create_menu(self):
        action_group = Gtk.ActionGroup("context-menu")
        action = Gtk.Action("MateMenuPrefs", _("Preferences"), None, "gtk-preferences")
        action.connect("activate", self.showPreferences)
        action_group.add_action(action)
        action = Gtk.Action("MateMenuEdit", _("Edit menu"), None, "gtk-edit")
        action.connect("activate", self.showMenuEditor)
        action_group.add_action(action)
        action = Gtk.Action("MateMenuReload", _("Reload plugins"), None, "gtk-refresh")
        action.connect("activate", self.mainwin.RegenPlugins)
        action_group.add_action(action)
        action = Gtk.Action("MateMenuAbout", _("About"), None, "gtk-about")
        action.connect("activate", self.showAboutDialog)
        action_group.add_action(action)
        action_group.set_translation_domain ("mate-menu")

        xml = os.path.join( self.data_path, "popup.xml" )
        self.applet.setup_menu_from_file(xml, action_group)

def applet_factory( applet, iid, data ):
    MenuWin( applet, iid )
    applet.show()
    return True

def quit_all(widget):
    Gtk.main_quit()
    sys.exit(0)

MatePanelApplet.Applet.factory_main("MateMenuAppletFactory", True,
                                    MatePanelApplet.Applet.__gtype__,
                                    applet_factory, None)
