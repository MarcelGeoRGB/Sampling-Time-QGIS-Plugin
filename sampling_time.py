# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SamplingTime
                                 A QGIS plugin
 A comprehensive QGIS plugin for automated area sampling using judgmental,
 random, systematic, stratified, and cluster techniques. It enables the 
 creation of sampling areas, exclusion zones, customizable stratification 
 and clustering, and generates shapefiles for outputs. Designed for precision 
 and adaptability in geospatial workflows.
 -------------------
        begin                : 2024-09-29
        copyright            : (C) 2024 by Marcel A. Cedrez 
        email                : marcel.a@giscourse.online
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This file is part of Sampling Time Plugin for QGIS.                   *
 *                                                                         *
 *   Sampling Time Plugin is free software: you can redistribute it and/or *
 *   modify it under the terms of the GNU General Public License as        *
 *   published by the Free Software Foundation, either version 3 of the    *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   Sampling Time Plugin is distributed in the hope that it will be       *
 *   useful, but WITHOUT ANY WARRANTY; without even the implied warranty   *
 *   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the       *
 *   GNU General Public License for more details.                          *
 *                                                                         *
 *   You should have received a copy of the GNU General Public License     *
 *   along with Sampling Time Plugin. If not, see                         *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 ***************************************************************************/
"""
# This file contains the main implementation of the Sampling plugin.

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
# Imports PyQt classes for QGIS plugin development
from qgis.PyQt.QtGui import QIcon
# Allows the use of icons and other GUI elements
from qgis.PyQt.QtWidgets import QAction
# Provides an action that can be added to menus and toolbars

# Initialize Qt resources from file resources.py
from .resources import *
# This imports resources used by the plugin

# Import the code for the dialog
from .sampling_time_dialog import SamplingDialog
# Imports the dialog that contains the plugin's GUI

import os.path
# Allows interaction with the file system

class Sampling:
    """QGIS Plugin Implementation."""
    # This class defines all methods required to integrate the plugin into QGIS

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        print(f"self.iface in sampling_time.py __init__: {'available' if self.iface else 'not available'}")

        # Initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # Determines where the plugin files are located

        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        # Fetches the user-defined locale (language preference)
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            f'Sampling_{locale}.qm')
        # Constructs the path to the translation file

        if os.path.exists(locale_path):
            # Loads translation file if it exists
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Sampling Time')
        # This is the menu name that appears in QGIS

        # Initialize dialog as None
        self.dlg = None
        # Will hold an instance of SamplingDialog

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str

        :returns: Translated version of message.
        :rtype: str
        """
        # Handles plugin translation
        return QCoreApplication.translate('Sampling', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar."""
        # This method creates and configures a new action in the QGIS interface
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip:
            action.setStatusTip(status_tip)

        if whats_this:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            # Adds plugin entry to the QGIS Vector menu
            self.iface.addPluginToVectorMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        # Called by QGIS to initialize GUI elements
        icon_path = ':/plugins/sampling_time/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Sampling Time'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        # Called by QGIS to remove GUI elements
        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.tr(u'&Sampling Time'), action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work."""
        # Triggered when user clicks the plugin's action
        print("\n=== STARTING PLUGIN ===")
        try:
            print("1. Checking self.dlg")
            if self.dlg is None:
                print("2. Creating new dialog")
                self.dlg = SamplingDialog(self.iface)
                print("3. Dialog created successfully")
            else:
                print("2. Using existing dialog")
            
            print("4. Preparing to display dialog")
            # Ensures dialog is restored if minimized
            if self.dlg.windowState() & Qt.WindowMinimized:
                self.dlg.setWindowState(self.dlg.windowState() & ~Qt.WindowMinimized)
            
            self.dlg.show()
            self.dlg.raise_()
            self.dlg.activateWindow()
            print("5. Dialog displayed")
            
        except Exception as e:
            print("\n=== PLUGIN ERROR ===")
            print(f"Error: {str(e)}")
            import traceback
            print("Complete Traceback:")
            print(traceback.format_exc())
            return
