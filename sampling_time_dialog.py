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

import os
import sys
import webbrowser
import subprocess
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QMessageBox, QFileDialog, QListWidgetItem, QInputDialog, QLineEdit,
)
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtCore import Qt

# Importing various sampling modules that implement different sampling methods
from .judgmental import JudgmentalSampling
from .random import RandomSampling
from .systematic import SystematicSampling
from .stratified_random import StratifiedRandomSampling
from .cluster_random import ClusterRandomSampling
from .generate_shapefile import Stratifiedshapefile
from .generate_areaexclusion import AreaExclusionModule
from .stratified_systematic import StratifiedSystematicSampling
from .cluster_systematic import ClusterSystematicSampling
from .reset import ResetFunction

# Load the UI definition from the .ui file created with Qt Designer
FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "sampling_time_dialog_base.ui")
)


class SamplingLayerModule:
    """
    Handles functionalities related to managing sampling layers within the QGIS project.
    This includes populating layer lists, handling symbol selection, managing exclusion layers,
    and saving labels.
    """
    def __init__(
        self,
        combo_box,
        tool_button,
        push_button_exclusion,
        list_widget_exclusion,
        line_edit_sample_label,
        push_button_save_label,
        combo_box_symbol,
        push_button_save_symbol,
    ):
        # Initialize UI components
        self.combo_box = combo_box
        self.tool_button = tool_button
        self.push_button_exclusion = push_button_exclusion
        self.list_widget_exclusion = list_widget_exclusion
        self.line_edit_sample_label = line_edit_sample_label
        self.push_button_save_label = push_button_save_label
        self.combo_box_symbol = combo_box_symbol
        self.push_button_save_symbol = push_button_save_symbol

        # Initialize internal variables
        self.sample_label_root = ""
        self.selected_symbol = None
        self.selected_symbol_editable = None

        # Populate the symbol selection combo box with available symbols
        self.populate_symbol_combo_box()

    def set_sample_label_root(self, text):
        """
        Sets the root label for samples based on user input.
        Strips any leading/trailing whitespace.
        """
        self.sample_label_root = text.strip()

    def save_sample_label(self):
        """
        Saves the current sample label if provided.
        Returns True if successful, False otherwise.
        """
        current_label = self.line_edit_sample_label.text().strip()
        if current_label:
            self.sample_label_root = current_label
            return True
        return False

    def populate_symbol_combo_box(self):
        """
        Loads symbol icons from specified directories into the symbol combo box.
        Icons are expected to be in 'symbol_icon' and 'symbol_icon2' directories.
        """
        symbol_folder = os.path.join(os.path.dirname(__file__), "symbol_icon")
        symbol_folder_editable = os.path.join(
            os.path.dirname(__file__), "symbol_icon2"
        )
        if os.path.exists(symbol_folder) and os.path.exists(symbol_folder_editable):
            for i in range(1, 11):
                svg_path = os.path.join(symbol_folder, f"Symbol {i}.svg")
                svg_path_editable = os.path.join(symbol_folder_editable, f"Symbol {i}.svg")
                if os.path.exists(svg_path) and os.path.exists(svg_path_editable):
                    try:
                        # Create an icon from the SVG file and add it to the combo box
                        icon = QIcon(svg_path)
                        self.combo_box_symbol.addItem(
                            icon, f"Symbol {i}", (svg_path, svg_path_editable)
                        )
                    except Exception as e:
                        print(f"Error loading symbol {i}: {str(e)}")

    def save_symbol(self):
        """
        Saves the selected symbol from the combo box.
        Returns True if a symbol is selected, False otherwise.
        """
        index = self.combo_box_symbol.currentIndex()
        if index >= 0:
            symbol_data = self.combo_box_symbol.itemData(index)
            if symbol_data:
                self.selected_symbol, self.selected_symbol_editable = symbol_data
                return True
        return False

    def populate_shapefile_layers(self):
        """
        Populates the shapefile layers combo box with available vector layers from the QGIS project.
        Only point, line, and polygon geometries are considered.
        """
        self.combo_box.clear()
        root = QgsProject.instance().layerTreeRoot()
        tree_layers = root.findLayers()

        for tree_layer in tree_layers:
            layer = tree_layer.layer()
            if isinstance(layer, QgsVectorLayer):
                geom_type = layer.geometryType()
                # Select appropriate icon based on geometry type
                if geom_type == QgsWkbTypes.PointGeometry:
                    icon = QIcon(":/images/themes/default/mIconPointLayer.svg")
                elif geom_type == QgsWkbTypes.LineGeometry:
                    icon = QIcon(":/images/themes/default/mIconLineLayer.svg")
                elif geom_type == QgsWkbTypes.PolygonGeometry:
                    icon = QIcon(":/images/themes/default/mIconPolygonLayer.svg")
                else:
                    icon = QIcon()
                # Get EPSG code for the layer's CRS
                epsg_code = layer.crs().authid()
                display_name = f"{layer.name()} [{epsg_code}]"
                # Add the layer to the combo box with its icon and name
                self.combo_box.addItem(icon, display_name)

    def open_file_dialog(self):
        """
        Opens a file dialog for the user to select shapefiles to add to the QGIS project.
        Adds valid shapefiles as vector layers and updates the shapefile layers combo box.
        """
        file_name, _ = QFileDialog.getOpenFileName(
            None, "Select File", "", "Shapefiles (*.shp);;All Files (*)"
        )
        if file_name:
            # Create a vector layer from the selected shapefile
            layer = QgsVectorLayer(file_name, os.path.basename(file_name), "ogr")
            if layer.isValid():
                # Add the layer to the current QGIS project
                QgsProject.instance().addMapLayer(layer)
                self.populate_shapefile_layers()
                # Set the newly added layer as the current selection in the combo box
                index = self.combo_box.findText(layer.name())
                if index != -1:
                    self.combo_box.setCurrentIndex(index)
            else:
                # Show a warning if the shapefile is invalid
                QMessageBox.warning(
                    None, "Invalid Layer", "The selected file is not a valid shapefile."
                )

    def open_exclusion_file_dialog(self):
        """
        Opens a file dialog to select exclusion shapefiles.
        Adds valid exclusion shapefiles as vector layers and updates the exclusion list widget.
        """
        files, _ = QFileDialog.getOpenFileNames(
            None, "Select Exclusion Files", "", "Shapefiles (*.shp);;All Files (*)"
        )
        if files:
            for file in files:
                # Create a vector layer from each selected shapefile
                layer = QgsVectorLayer(file, os.path.basename(file), "ogr")
                if layer.isValid():
                    # Add the layer to the project without adding it to the legend
                    QgsProject.instance().addMapLayer(layer, addToLegend=False)
                    # Create a list item for the exclusion layer
                    list_item = QListWidgetItem(os.path.basename(file))
                    list_item.setData(Qt.UserRole, layer.id())
                    # Add the item to the exclusion list widget
                    self.list_widget_exclusion.addItem(list_item)
                else:
                    # Show a warning if any shapefile is invalid
                    QMessageBox.warning(
                        None,
                        "Invalid Layer",
                        f"The file '{file}' is not a valid shapefile.",
                    )

    def remove_exclusion_layer(self, item):
        """
        Removes a selected exclusion layer from the project and the exclusion list widget.
        Prompts the user for confirmation before removal.
        """
        reply = QMessageBox.question(
            None,
            "Remove Layer",
            f"Remove {item.text()} from exclusion list?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            layer_id = item.data(Qt.UserRole)
            if layer_id:
                # Remove the layer from the QGIS project
                QgsProject.instance().removeMapLayer(layer_id)
            # Remove the item from the list widget
            self.list_widget_exclusion.takeItem(self.list_widget_exclusion.row(item))


class SamplingDialog(QtWidgets.QDialog, FORM_CLASS):
    """
    Represents the main dialog window of the sampling plugin.
    Initializes the UI, sets up connections between UI elements and functionalities,
    and manages the overall workflow of the sampling processes.
    """
    def __init__(self, iface=None, parent=None):
        super(SamplingDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)  # Add minimize button to the dialog window while keeping the close button
        self.setupUi(self)  # Set up the UI from the loaded .ui file
        self.tabWidget.setCurrentIndex(0)  # Set Judgmental tab as default when opening the plugin
        self.iface = iface  # Reference to the QGIS interface

        # Initialize the reset manager and connect the reset button
        self.reset_manager = ResetFunction(self)
        self.pushbuttonreset.clicked.connect(self.reset_manager.full_plugin_reset)

        # Initialize the SamplingLayerModule with relevant UI components
        self.layer_module = SamplingLayerModule(
            self.comboBoxshpsampling,
            self.toolButtonshpsampling,
            self.pushButtonexclusion,
            self.listWidgetexclusion,
            self.lineEditsamplelabel,
            self.pushButtonsavelabel,
            self.comboBoxsymbol,
            self.pushButtonsavesymbol,
        )

        # Populate the shapefile layers combo box
        self.layer_module.populate_shapefile_layers()

        # Initialize controls and set up UI connections and additional modules
        self.initialize_controls()
        self.setup_ui_connections()
        self.setup_modules()

        # Configure the spin box for angle input with a range of 0 to 180 degrees
        self.spinBoxanglesystematically.setRange(0, 180)
        self.spinBoxanglesystematically.setValue(0)

        # Connect the state change of the systematic sampling checkbox to its handler
        self.checkBoxaddsamplessystematically.stateChanged.connect(
            self.on_checkBoxaddsamplessystematically_stateChanged
        )

        # Initialize the state of the systematic sampling controls based on the checkbox state
        self.on_checkBoxaddsamplessystematically_stateChanged(
            self.checkBoxaddsamplessystematically.checkState()
        )

        # Load and display the plugin's logo
        plugin_dir = os.path.dirname(__file__)
        icon_path = os.path.join(plugin_dir, "icon_ui.png")
        pixmap = QPixmap(icon_path)

        self.label_logo.setScaledContents(True)
        self.label_logo.setAttribute(Qt.WA_TranslucentBackground)
        self.label_logo.setWindowFlags(Qt.FramelessWindowHint)

        # Scale the logo image for better visibility
        scale_factor = 2
        scaled_width = int(self.label_logo.width() * scale_factor)
        scaled_height = int(self.label_logo.height() * scale_factor)

        scaled_pixmap = pixmap.scaled(
            scaled_width,
            scaled_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.label_logo.setPixmap(scaled_pixmap)
    
    def keyPressEvent(self, event):
        """Override keyPressEvent to prevent Enter key from opening symbol folder"""
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            event.ignore()
        else:
            super().keyPressEvent(event)

    def setup_ui_connections(self):
        """
        Connects various UI elements (buttons, text fields, checkboxes) to their respective
        event handlers or functions to manage user interactions.
        """
        # Connect text changes in the sample label line edit to update the sample label
        self.layer_module.set_sample_label_root
        self.lineEditsamplelabel.textChanged.connect(
            self.layer_module.set_sample_label_root
        )
        # Connect save label and save symbol buttons to their handlers
        self.pushButtonsavelabel.clicked.connect(self.save_label_and_show_message)
        self.pushButtonsavesymbol.clicked.connect(self.save_symbol_and_show_message)
        # Connect buttons to open file dialogs
        self.toolButtonshpsampling.clicked.connect(self.layer_module.open_file_dialog)
        self.pushButtonexclusion.clicked.connect(
            self.layer_module.open_exclusion_file_dialog
        )
        # Connect double-click on exclusion list items to removal handler
        self.listWidgetexclusion.itemDoubleClicked.connect(
            self.layer_module.remove_exclusion_layer
        )
        # Connect symbol button if it exists
        if hasattr(self, 'pushbuttonsymbol'):
            self.pushbuttonsymbol.clicked.connect(self.open_symbol_folder)

        # Connect the close button to the plugin's close handler
        self.pushbuttonclose.clicked.connect(self.reset_manager.close_plugin)

        # List of all function-related checkboxes to connect to a common handler
        self.all_function_checkboxes = [
            self.checkBoxaddsamplesmanually,
            self.checkBoxaddsamplesbycoordinates,
            self.checkBoxaddsamplesbyfile,
            self.checkBoxaddsamplesrandomly,
            self.checkBoxaddsamplessystematically,
            self.checkBoxaddstratifiedsamplesrandomly,
            self.checkBoxaddstratifiedsamplessystematically,
            self.checkBoxaddclustersamplesrandomly,
            self.checkBoxaddclustersamplessystematically,
            self.checkBoxshpsamplingarea,
            self.checkBoxgenerateshpbycoordinates,
            self.checkBoxstratapolyline,
            self.checkBoxstratavoronoi,
            self.checkBoxstratalines
        ]

        # Connect each checkbox to the general function checkbox state handler
        for cb in self.all_function_checkboxes:
            cb.stateChanged.connect(self.on_function_checkbox_changed)

        # Connect specific checkboxes to their dedicated handlers
        self.checkBoxaddsamplesmanually.stateChanged.connect(
            self.on_addsamplesmanually_changed
        )
        self.checkBoxaddsamplesbycoordinates.stateChanged.connect(
            self.on_addsamplesbycoordinates_changed
        )
        self.checkBoxaddsamplesbyfile.stateChanged.connect(
            self.on_addsamplesbyfile_changed
        )
        self.checkBoxaddsamplesrandomly.stateChanged.connect(
            self.on_addsamplesrandomly_changed
        )

        # Initialize and connect random sampling module
        self.random_sampling = RandomSampling(self.iface, self)
        self.spinBoxnumberofsamples.valueChanged.connect(self.update_random_parameters)
        self.doubleSpinBoxdistanceperimeter.valueChanged.connect(self.update_random_parameters)
        self.doubleSpinBoxdistancesamples.valueChanged.connect(self.update_random_parameters)
        self.doubleSpinBoxdistanceexclusion.valueChanged.connect(self.update_random_parameters)
        self.pushButtonrandomstart.clicked.connect(self.random_sampling.on_pushButtonrandomstart_clicked)
        self.pushButtonrandomreset.clicked.connect(self.random_sampling.on_pushButtonrandomreset_clicked)
        self.pushButtonrandomsave.clicked.connect(self.random_sampling.on_pushButtonrandomsave_clicked)
        self.checkBoxoutsidesamplingrandom.stateChanged.connect(self.update_random_parameters)

        # Initialize and connect stratified random sampling module
        self.stratified_sampling = StratifiedRandomSampling(self.iface, self)
        self.spinBoxnumberofstratifiedsamples.valueChanged.connect(self.update_stratified_parameters)
        self.doubleSpinBoxdistancestratifiedsamples.valueChanged.connect(self.update_stratified_parameters)
        self.doubleSpinBoxdistancestratifiedperimeter.valueChanged.connect(self.update_stratified_parameters)
        self.doubleSpinBoxdistancestratifiedexclusion.valueChanged.connect(self.update_stratified_parameters)
        self.checkBoxadjustsamplesbysurfacearea.stateChanged.connect(self.update_stratified_parameters)
        self.pushButtonstratifiedrandomstart.clicked.connect(self.start_stratified_sampling)
        self.checkBoxoutsidesampling_stratified.stateChanged.connect(self.update_stratified_parameters)
        self.checkBoxaddstratifiedsamplesrandomly.stateChanged.connect(
            self.stratified_sampling.on_checkBoxaddstratifiedsamplesrandomly_stateChanged
        )

        # Initialize and connect cluster random sampling module
        self.cluster_sampling = ClusterRandomSampling(self.iface, self)
        self.spinBoxnumberofclustersamples.valueChanged.connect(self.update_cluster_parameters)
        self.doubleSpinBoxdistanceclustersamples.valueChanged.connect(self.update_cluster_parameters)
        self.doubleSpinBoxdistanceclusterperimeter.valueChanged.connect(self.update_cluster_parameters)
        self.doubleSpinBoxdistanceclusterexclusion.valueChanged.connect(self.update_cluster_parameters)
        self.checkBoxadjustclustersamplesbysurfacearea.stateChanged.connect(self.update_cluster_parameters)
        self.pushButtonclusterrandomstart.clicked.connect(self.start_cluster_sampling)
        self.checkBoxoutsidesamplingcluster.stateChanged.connect(self.update_cluster_parameters)
        self.checkBoxaddclustersamplesrandomly.stateChanged.connect(
            self.cluster_sampling.on_checkBoxaddclustersamplesrandomly_stateChanged
        )

        # Initialize and connect stratified systematic sampling module
        self.stratified_systematic_sampling = StratifiedSystematicSampling(self.iface, self)
        self.checkBoxaddstratifiedsamplessystematically.stateChanged.connect(
            self.on_addstratifiedsystematic_changed
        )
        self.checkBoxaddstratifiedsamplesrandomly.stateChanged.connect(
            self.on_addstratifiedrandom_changed
        )
        self.pushButtonstratifiedsystematicstart.clicked.connect(
            self.start_stratified_systematic_sampling
        )
        self.pushButtonstratifiedsystematicsave.clicked.connect(
            self.save_stratified_systematic_sampling
        )

        # Initialize and connect cluster systematic sampling module
        self.cluster_systematic_sampling = ClusterSystematicSampling(self.iface, self)
        self.checkBoxaddclustersamplessystematically.stateChanged.connect(
            self.on_addclustersystematic_changed
        )
        self.checkBoxaddclustersamplesrandomly.stateChanged.connect(
            self.on_addclusterrandom_changed
        )
        self.pushButtonclustersystematicstart.clicked.connect(
            self.start_cluster_systematic_sampling
        )
        self.pushButtonclustersystematicsave.clicked.connect(
            self.save_cluster_systematic_sampling
        )

        # Connect shapefile sampling area and generation checkboxes to their handlers
        self.checkBoxshpsamplingarea.stateChanged.connect(
            self.on_shpsamplingarea_changed
        )
        self.checkBoxgenerateshpbycoordinates.stateChanged.connect(
            self.on_generateshpbycoordinates_changed
        )

        # Connect license button if it exists
        if hasattr(self, 'pushButtonlicense'):
            self.pushButtonlicense.clicked.connect(self.open_license_file)

    def open_symbol_folder(self):
        """
        Opens the folder containing editable symbol icons in the user's default file browser.
        Shows a warning if the folder does not exist or an error occurs.
        """
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            symbol_dir = os.path.join(current_dir, "symbol_icon2")

            if os.path.exists(symbol_dir):
                webbrowser.open(symbol_dir)
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Symbol directory not found at: {symbol_dir}"
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Error opening directory: {str(e)}"
            )

    def initialize_controls(self):
        """
        Disables specific UI controls at startup to prevent user interaction
        until certain conditions are met.
        """
        controls_to_disable = [
            self.pushButtonedition,
            self.pushButtonfinishedition,
            self.checkBoxoutsidesampling,
            self.pushButtonaddcoordinates_judgmental,
            self.pushButtonfinishcoordinates_judgmental,
            self.listWidgetlistofcoordinates_judgmental,
            self.lineEditxcoordinates_judgmental,
            self.lineEditycoordinate_judgmental,
            self.pushButtonloadfilejudgmental,
            self.lineEditaddsamplesbyfile,
            self.comboBoxcolumnx,
            self.comboBoxcolumny,
            self.pushButtonaddcoordinatesfile_judgmental,
            self.pushButtonfinishcoordinatesfile_judgmental,
            self.spinBoxanglesystematically,
            self.pushButtonregularsystematicstart,
            self.pushButtonregularsystematicsave,
            self.doubleSpinBoxdistancexsamples,
            self.doubleSpinBoxdistanceysamples,
            self.doubleSpinBoxdistanceperimetersamplearea,
            self.doubleSpinBoxdistanceperimeterexclusionarea,
            self.checkBoxoutsidesampling_zigzagsystematic,
            self.checkBoxoutsidesampling_systematic,
            self.spinBoxnumberofstratifiedsamples,
            self.doubleSpinBoxdistancestratifiedsamples,
            self.pushButtonstratifiedrandomstart,
            self.pushButtonstratifiedrandomreset,
            self.pushButtonstratifiedrandomsave,
            self.doubleSpinBoxdistancestratifiedperimeter,
            self.doubleSpinBoxdistancestratifiedexclusion,
            self.checkBoxoutsidesampling_stratified,
            self.checkBoxadjustsamplesbysurfacearea,
            self.spinBoxnumberofclustersamples,
            self.doubleSpinBoxdistanceclustersamples,
            self.pushButtonclusterrandomstart,
            self.pushButtonclusterrandomreset,
            self.pushButtonclusterrandomsave,
            self.doubleSpinBoxdistanceclusterperimeter,
            self.doubleSpinBoxdistanceclusterexclusion,
            self.checkBoxoutsidesamplingcluster,
            self.checkBoxadjustclustersamplesbysurfacearea,
            self.doubleSpinBoxdistanceclusterxsamples,
            self.doubleSpinBoxdistanceclusterysamples,
            self.spinBoxangleclustersystematically,
            self.pushButtonclustersystematicstart,
            self.pushButtonclustersystematicsave,
            self.checkBoxclustersampling_zigzagcluster
        ]

        # Disable each control in the list
        for control in controls_to_disable:
            control.setEnabled(False)

    def setup_modules(self):
        """
        Initializes additional modules like area exclusion, judgmental sampling,
        systematic sampling, and stratified shapefile generation.
        """
        self.setup_area_exclusion()
        self.setup_judgmental_sampling()
        self.setup_systematic_sampling()
        self.setup_stratified_shapefile()

    def setup_area_exclusion(self):
        """
        Initializes the AreaExclusionModule if the QGIS interface is available.
        """
        if self.iface:
            self.area_exclusion = AreaExclusionModule(self.iface, self)

    def setup_judgmental_sampling(self):
        """
        Initializes the JudgmentalSampling module and connects its buttons to handlers.
        Also connects the layerRemoved signal to handle layer removal events.
        """
        if self.iface:
            self.judgmental_sampling = JudgmentalSampling(self.iface, self)
            self.pushButtonedition.clicked.connect(
                lambda: self.judgmental_sampling.start_editing(
                    self.checkBoxoutsidesampling.isChecked()
                )
            )
            self.pushButtonfinishedition.clicked.connect(
                self.judgmental_sampling.finish_editing
            )
            QgsProject.instance().layerRemoved.connect(self.judgmental_sampling.handle_layer_removed)
        else:
            # Disable related buttons if interface is not available
            self.judgmental_sampling = None
            self.pushButtonedition.setEnabled(False)
            self.pushButtonfinishedition.setEnabled(False)

    def setup_systematic_sampling(self):
        """
        Initializes the SystematicSampling module and connects its buttons to handlers.
        """
        if self.iface:
            self.systematic_sampling = SystematicSampling(self.iface, self)
            self.pushButtonregularsystematicstart.clicked.connect(self.start_systematic_sampling)
            self.pushButtonregularsystematicsave.clicked.connect(self.save_systematic_sampling)
        else:
            # Disable related buttons if interface is not available
            self.systematic_sampling = None
            self.pushButtonregularsystematicstart.setEnabled(False)
            self.pushButtonregularsystematicsave.setEnabled(False)

    def setup_stratified_shapefile(self):
        """
        Initializes the Stratifiedshapefile module if the QGIS interface is available.
        """
        if self.iface:
            self.stratified_shapefile = Stratifiedshapefile(self.iface, self)
        else:
            self.stratified_shapefile = None

    def save_label_and_show_message(self):
        """
        Saves the sample label and shows an information message if successful.
        Shows a warning if no label is entered.
        """
        if self.layer_module.save_sample_label():
            QMessageBox.information(
                self,
                "Label Saved",
                f"Sample label '{self.lineEditsamplelabel.text().strip()}' saved successfully!"
            )
        else:
            QMessageBox.warning(
                self,
                "Error",
                "Please enter a sample label before saving."
            )

    def save_symbol_and_show_message(self):
        """
        Saves the selected symbol and shows an information message if successful.
        Shows a warning if no symbol is selected.
        """
        if self.layer_module.save_symbol():
            QMessageBox.information(
                self,
                "Symbol Saved",
                f"Symbol '{self.comboBoxsymbol.currentText()}' saved successfully!"
            )
        else:
            QMessageBox.warning(
                self,
                "Error",
                "Please select a symbol before saving."
            )

    def update_random_parameters(self):
        """
        Placeholder method to handle updates to random sampling parameters.
        Can be expanded to implement specific behaviors when parameters change.
        """
        pass

    def update_stratified_parameters(self):
        """
        Placeholder method to handle updates to stratified sampling parameters.
        Can be expanded to implement specific behaviors when parameters change.
        """
        pass

    def update_cluster_parameters(self):
        """
        Placeholder method to handle updates to cluster sampling parameters.
        Can be expanded to implement specific behaviors when parameters change.
        """
        pass

    def start_stratified_sampling(self):
        """
        Initiates stratified random sampling based on the current settings and selected layers.
        Validates the selected sampling layer and exclusion layers before starting the sampling process.
        """
        # Get the name of the currently selected sampling layer
        current_layer_name = self.comboBoxshpsampling.currentText().split(" [")[0]
        sampling_layer = None

        # Find the layer in the project by name
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == current_layer_name:
                sampling_layer = layer
                break

        if not sampling_layer:
            QMessageBox.warning(self, "Error", "Please select a valid sampling layer.")
            return

        # Collect all exclusion layers selected by the user
        exclusion_layers = []
        for i in range(self.listWidgetexclusion.count()):
            item = self.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                exclusion_layers.append(layer)

        # Configure the stratified sampling module with selected layers and parameters
        self.stratified_sampling.set_sampling_area(sampling_layer)
        self.stratified_sampling.set_exclusion_zones(exclusion_layers)
        self.stratified_sampling.set_parameters()
        
    def start_cluster_sampling(self):
        """
        Initiates cluster random sampling based on the current settings and selected layers.
        Validates the selected sampling layer and exclusion layers before starting the sampling process.
        """
        # Get the name of the currently selected sampling layer
        current_layer_name = self.comboBoxshpsampling.currentText().split(" [")[0]
        sampling_layer = None

        # Find the layer in the project by name
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == current_layer_name:
                sampling_layer = layer
                break

        if not sampling_layer:
            QMessageBox.warning(self, "Error", "Please select a valid sampling layer.")
            return

        # Collect all exclusion layers selected by the user
        exclusion_layers = []
        for i in range(self.listWidgetexclusion.count()):
            item = self.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                exclusion_layers.append(layer)

        # Configure the cluster sampling module with selected layers and parameters
        self.cluster_sampling.set_sampling_area(sampling_layer)
        self.cluster_sampling.set_exclusion_zones(exclusion_layers)
        self.cluster_sampling.set_parameters()
       
    def start_systematic_sampling(self):
        """
        Initiates systematic sampling based on the current settings and selected layers.
        Validates the selected sampling layer and exclusion layers before starting the sampling process.
        """
        # Get the name of the currently selected sampling layer
        current_layer_name = self.comboBoxshpsampling.currentText().split(" [")[0]
        sampling_layer = None

        # Find the layer in the project by name
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == current_layer_name:
                sampling_layer = layer
                break

        if not sampling_layer:
            QMessageBox.warning(self, "Error", "Please select a valid sampling layer.")
            return

        # Collect all exclusion layers selected by the user
        exclusion_layers = []
        for i in range(self.listWidgetexclusion.count()):
            item = self.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                exclusion_layers.append(layer)

        # Configure the systematic sampling module with selected layers and parameters
        self.systematic_sampling.set_sampling_area(sampling_layer)
        self.systematic_sampling.set_exclusion_zones(exclusion_layers)
        self.systematic_sampling.set_parameters(
            spacing_x=self.doubleSpinBoxdistancexsamples.value(),
            spacing_y=self.doubleSpinBoxdistanceysamples.value(),
            label_root=self.layer_module.sample_label_root,
            perimeter_buffer_sample_area=self.doubleSpinBoxdistanceperimetersamplearea.value(),
            perimeter_buffer_exclusion_area=self.doubleSpinBoxdistanceperimeterexclusionarea.value()
        )
        # Start the systematic sampling process
        self.systematic_sampling.start_sampling()

    def save_systematic_sampling(self):
        """
        Saves the results of the systematic sampling to a shapefile.
        Prompts the user to select an output directory and enter a file name.
        """
        if not hasattr(self.systematic_sampling, 'samples') or not self.systematic_sampling.samples:
            QMessageBox.warning(self, "Error", "No samples to save.")
            return

        # Prompt the user to select an output directory
        output_dir = QFileDialog.getExistingDirectory(self, "Select output directory")
        if not output_dir:
            return

        # Prompt the user to enter a file name
        filename, ok = QInputDialog.getText(
            self,
            "File name",
            "Enter file name (without extension):",
            QLineEdit.Normal,
            "systematic_samples"
        )
        if not ok or not filename:
            return

        # Save the samples using the systematic sampling module
        self.systematic_sampling.save_samples(output_dir, filename)

    def save_stratified_systematic_sampling(self):
        """
        Saves the results of the stratified systematic sampling to a shapefile.
        Prompts the user to select an output directory and enter a file name.
        """
        if not hasattr(self.stratified_systematic_sampling, 'samples') or not self.stratified_systematic_sampling.samples:
            QMessageBox.warning(self, "Error", "No samples to save.")
            return

        # Prompt the user to select an output directory
        output_dir = QFileDialog.getExistingDirectory(self, "Select output directory")
        if not output_dir:
            return

        # Prompt the user to enter a file name
        filename, ok = QInputDialog.getText(
            self,
            "File name",
            "Enter file name (without extension):",
            QLineEdit.Normal,
            "stratified_systematic_samples"
        )
        if not ok or not filename:
            return

        # Save the samples using the stratified systematic sampling module
        self.stratified_systematic_sampling.save_samples(output_dir, filename)

    def save_cluster_systematic_sampling(self):
        """
        Saves the results of the cluster systematic sampling to a shapefile.
        Prompts the user to select an output directory and enter a file name.
        """
        if not hasattr(self.cluster_systematic_sampling, 'samples') or not self.cluster_systematic_sampling.samples:
            QMessageBox.warning(self, "Error", "No samples to save.")
            return

        # Prompt the user to select an output directory
        output_dir = QFileDialog.getExistingDirectory(self, "Select output directory")
        if not output_dir:
            return

        # Prompt the user to enter a file name
        filename, ok = QInputDialog.getText(
            self,
            "File name",
            "Enter file name (without extension):",
            QLineEdit.Normal,
            "cluster_systematic_samples"
        )
        if not ok or not filename:
            return

        # Save the samples using the cluster systematic sampling module
        self.cluster_systematic_sampling.save_samples(output_dir, filename)

    def start_stratified_systematic_sampling(self):
        """
        Initiates stratified systematic sampling based on the current settings and selected layers.
        Validates the selected sampling layer and exclusion layers before starting the sampling process.
        """
        # Get the name of the currently selected sampling layer
        current_layer_name = self.comboBoxshpsampling.currentText().split(" [")[0]
        sampling_layer = None

        # Find the layer in the project by name
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == current_layer_name:
                sampling_layer = layer
                break

        if not sampling_layer:
            QMessageBox.warning(self, "Error", "Please select a valid sampling layer.")
            return

        # Collect all exclusion layers selected by the user
        exclusion_layers = []
        for i in range(self.listWidgetexclusion.count()):
            item = self.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                exclusion_layers.append(layer)

        # Configure the stratified systematic sampling module with selected layers and parameters
        self.stratified_systematic_sampling.set_sampling_area(sampling_layer)
        self.stratified_systematic_sampling.set_exclusion_zones(exclusion_layers)
        self.stratified_systematic_sampling.set_parameters(
            spacing_x=self.doubleSpinBoxdistancestratifiedxsamples.value(),
            spacing_y=self.doubleSpinBoxdistancestratifiedysamples.value(),
            label_root=self.layer_module.sample_label_root,
            perimeter_buffer_sample_area=self.doubleSpinBoxdistancestratifiedperimeter.value(),
            perimeter_buffer_exclusion_area=self.doubleSpinBoxdistancestratifiedexclusion.value()
        )
        # Start the stratified systematic sampling process
        self.stratified_systematic_sampling.start_sampling()

    def start_cluster_systematic_sampling(self):
        """
        Initiates cluster systematic sampling based on the current settings and selected layers.
        Validates the selected sampling layer and exclusion layers before starting the sampling process.
        """
        # Get the name of the currently selected sampling layer
        current_layer_name = self.comboBoxshpsampling.currentText().split(" [")[0]
        sampling_layer = None

        # Find the layer in the project by name
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == current_layer_name:
                sampling_layer = layer
                break

        if not sampling_layer:
            QMessageBox.warning(self, "Error", "Please select a valid sampling layer.")
            return

        # Collect all exclusion layers selected by the user
        exclusion_layers = []
        for i in range(self.listWidgetexclusion.count()):
            item = self.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                exclusion_layers.append(layer)

        # Configure the cluster systematic sampling module with selected layers and parameters
        self.cluster_systematic_sampling.set_sampling_area(sampling_layer)
        self.cluster_systematic_sampling.set_exclusion_zones(exclusion_layers)
        self.cluster_systematic_sampling.set_parameters(
            spacing_x=self.doubleSpinBoxdistanceclusterxsamples.value(),
            spacing_y=self.doubleSpinBoxdistanceclusterysamples.value(),
            label_root=self.layer_module.sample_label_root,
            perimeter_buffer_sample_area=self.doubleSpinBoxdistanceclusterperimeter.value(),
            perimeter_buffer_exclusion_area=self.doubleSpinBoxdistanceclusterexclusion.value()
        )
        # Start the cluster systematic sampling process
        self.cluster_systematic_sampling.start_sampling()

    def on_checkBoxaddsamplessystematically_stateChanged(self, state):
        """
        Handles the state change of the 'Add Samples Systematically' checkbox.
        Enables or disables related controls based on whether the checkbox is checked.
        """
        controls = [
            self.doubleSpinBoxdistancexsamples,
            self.doubleSpinBoxdistanceysamples,
            self.spinBoxanglesystematically,
            self.pushButtonregularsystematicstart,
            self.pushButtonregularsystematicsave,
            self.doubleSpinBoxdistanceperimetersamplearea,
            self.doubleSpinBoxdistanceperimeterexclusionarea,
            self.checkBoxoutsidesampling_zigzagsystematic,
            self.checkBoxoutsidesampling_systematic,
        ]
        for control in controls:
            control.setEnabled(state == Qt.Checked)

    def on_addsamplesmanually_changed(self, state):
        """
        Handles the state change of the 'Add Samples Manually' checkbox.
        Enables or disables related controls based on whether the checkbox is checked.
        """
        controls_manual = [
            self.pushButtonedition,
            self.pushButtonfinishedition,
            self.checkBoxoutsidesampling,
        ]
        for control in controls_manual:
            control.setEnabled(state == Qt.Checked)

    def on_addsamplesbycoordinates_changed(self, state):
        """
        Handles the state change of the 'Add Samples by Coordinates' checkbox.
        Enables or disables related controls based on whether the checkbox is checked.
        """
        controls_coordinates = [
            self.pushButtonaddcoordinates_judgmental,
            self.pushButtonfinishcoordinates_judgmental,
            self.listWidgetlistofcoordinates_judgmental,
            self.lineEditxcoordinates_judgmental,
            self.lineEditycoordinate_judgmental,
            self.checkBoxoutsidesampling
        ]
        for control in controls_coordinates:
            control.setEnabled(state == Qt.Checked)

    def on_addsamplesbyfile_changed(self, state):
        """
        Handles the state change of the 'Add Samples by File' checkbox.
        Enables or disables related controls based on whether the checkbox is checked.
        """
        controls_file = [
            self.pushButtonloadfilejudgmental,
            self.lineEditaddsamplesbyfile,
            self.comboBoxcolumnx,
            self.comboBoxcolumny,
            self.pushButtonaddcoordinatesfile_judgmental,
            self.pushButtonfinishcoordinatesfile_judgmental,
            self.checkBoxoutsidesampling,
        ]
        for control in controls_file:
            control.setEnabled(state == Qt.Checked)

    def on_shpsamplingarea_changed(self, state):
        """
        Handles the state change of the 'Shapefile Sampling Area' checkbox.
        Toggles buttons in the AreaExclusionModule based on the checkbox state.
        """
        if hasattr(self, 'area_exclusion') and self.area_exclusion:
            self.area_exclusion.toggle_buttons(state)

    def on_generateshpbycoordinates_changed(self, state):
        """
        Handles the state change of the 'Generate Shapefile by Coordinates' checkbox.
        Toggles buttons in the AreaExclusionModule based on the checkbox state.
        """
        if hasattr(self, 'area_exclusion') and self.area_exclusion:
            self.area_exclusion.toggle_buttons(state)

    def on_addstratifiedsystematic_changed(self, state):
        """
        Handles the state change of the 'Add Stratified Samples Systematically' checkbox.
        Enables or disables related controls and unchecks other sampling method checkboxes.
        """
        if state == Qt.Checked:
            # Uncheck the random stratified samples checkbox to prevent conflict
            self.checkBoxaddstratifiedsamplesrandomly.setChecked(False)
            controls = [
                self.doubleSpinBoxdistancestratifiedxsamples,
                self.doubleSpinBoxdistancestratifiedysamples,
                self.spinBoxanglestratifiedsystematically,
                self.pushButtonstratifiedsystematicstart,
                self.pushButtonstratifiedsystematicsave,
                self.checkBoxstratifiedsampling_zigzagsystematic,
                self.checkBoxoutsidesampling_stratified,
                self.doubleSpinBoxdistancestratifiedperimeter,
                self.doubleSpinBoxdistancestratifiedexclusion
            ]
            for control in controls:
                control.setEnabled(True)
        else:
            # Disable the related controls if the checkbox is unchecked
            controls = [
                self.doubleSpinBoxdistancestratifiedxsamples,
                self.doubleSpinBoxdistancestratifiedysamples,
                self.spinBoxanglestratifiedsystematically,
                self.pushButtonstratifiedsystematicstart,
                self.pushButtonstratifiedsystematicsave,
                self.checkBoxstratifiedsampling_zigzagsystematic,
                self.checkBoxoutsidesampling_stratified,
                self.doubleSpinBoxdistancestratifiedperimeter,
                self.doubleSpinBoxdistancestratifiedexclusion
            ]
            for control in controls:
                control.setEnabled(False)

    def on_addstratifiedrandom_changed(self, state):
        """
        Handles the state change of the 'Add Stratified Samples Randomly' checkbox.
        Unchecks the systematic stratified samples checkbox to prevent conflict.
        """
        if state == Qt.Checked:
            self.checkBoxaddstratifiedsamplessystematically.setChecked(False)

    def on_addclusterrandom_changed(self, state):
        """
        Handles the state change of the 'Add Cluster Samples Randomly' checkbox.
        Enables or disables related controls based on whether the checkbox is checked.
        """
        if state == Qt.Checked:
            controls = [
                self.spinBoxnumberofclustersamples,
                self.doubleSpinBoxdistanceclustersamples,
                self.pushButtonclusterrandomstart,
                self.pushButtonclusterrandomreset,
                self.pushButtonclusterrandomsave,
                self.doubleSpinBoxdistanceclusterperimeter,
                self.doubleSpinBoxdistanceclusterexclusion,
                self.checkBoxoutsidesamplingcluster,
                self.checkBoxadjustclustersamplesbysurfacearea
            ]
            for control in controls:
                control.setEnabled(True)
        else:
            controls = [
                self.spinBoxnumberofclustersamples,
                self.doubleSpinBoxdistanceclustersamples,
                self.pushButtonclusterrandomstart,
                self.pushButtonclusterrandomreset,
                self.pushButtonclusterrandomsave,
                self.doubleSpinBoxdistanceclusterperimeter,
                self.doubleSpinBoxdistanceclusterexclusion,
                self.checkBoxoutsidesamplingcluster,
                self.checkBoxadjustclustersamplesbysurfacearea
            ]
            for control in controls:
                control.setEnabled(False)

    def on_addclustersystematic_changed(self, state):
        """
        Handles the state change of the 'Add Cluster Samples Systematically' checkbox.
        Enables or disables related controls and unchecks other sampling method checkboxes.
        """
        if state == Qt.Checked:
            # Uncheck the random cluster samples checkbox to prevent conflict
            self.checkBoxaddclustersamplesrandomly.setChecked(False)
            controls = [
                self.doubleSpinBoxdistanceclusterxsamples,
                self.doubleSpinBoxdistanceclusterysamples,
                self.spinBoxangleclustersystematically,
                self.pushButtonclustersystematicstart,
                self.pushButtonclustersystematicsave,
                self.checkBoxclustersampling_zigzagcluster,
                self.checkBoxoutsidesamplingcluster,
                self.doubleSpinBoxdistanceclusterperimeter,
                self.doubleSpinBoxdistanceclusterexclusion
            ]
            for control in controls:
                control.setEnabled(True)
        else:
            # Disable the related controls if the checkbox is unchecked
            controls = [
                self.doubleSpinBoxdistanceclusterxsamples,
                self.doubleSpinBoxdistanceclusterysamples,
                self.spinBoxangleclustersystematically,
                self.pushButtonclustersystematicstart,
                self.pushButtonclustersystematicsave,
                self.checkBoxclustersampling_zigzagcluster,
                self.checkBoxoutsidesamplingcluster,
                self.doubleSpinBoxdistanceclusterperimeter,
                self.doubleSpinBoxdistanceclusterexclusion
            ]
            for control in controls:
                control.setEnabled(False)

    def on_addsamplesrandomly_changed(self, state):
        """
        Handles the state change of the 'Add Samples Randomly' checkbox.
        Enables or disables related controls based on whether the checkbox is checked.
        """
        controls_random = [
            self.spinBoxnumberofsamples,
            self.doubleSpinBoxdistancesamples,
            self.doubleSpinBoxdistanceexclusion,
            self.doubleSpinBoxdistanceperimeter,
            self.pushButtonrandomstart,
            self.pushButtonrandomreset,
            self.pushButtonrandomsave,
            self.checkBoxoutsidesamplingrandom
        ]
        for control in controls_random:
            control.setEnabled(state == Qt.Checked)

    def on_function_checkbox_changed(self, state):
        """
        Handles the state change of any function-related checkbox.
        Ensures that only one sampling method is active at a time by resetting others.
        """
        if state == Qt.Checked:
            sender = self.sender()
            # Prevent specific checkboxes from triggering this behavior
            if sender != self.checkBoxaddstratifiedsamplessystematically:
                controls = [
                    self.doubleSpinBoxdistancestratifiedxsamples,
                    self.doubleSpinBoxdistancestratifiedysamples,
                    self.spinBoxanglestratifiedsystematically,
                    self.pushButtonstratifiedsystematicstart,
                    self.pushButtonstratifiedsystematicsave,
                    self.checkBoxstratifiedsampling_zigzagsystematic,
                    self.checkBoxoutsidesampling_stratified,
                    self.doubleSpinBoxdistancestratifiedperimeter,
                    self.doubleSpinBoxdistancestratifiedexclusion
                ]
                for control in controls:
                    control.setEnabled(False)

            # Reset all other sampling methods
            self.reset_manager.reset_all()
            if not self.checkBoxaddsamplesrandomly.isChecked():
                self.random_sampling.disable_controls()
            # Ensure the sender checkbox remains checked and doesn't interfere with others
            sender.blockSignals(True)
            sender.setChecked(True)
            sender.blockSignals(False)

    def closeEvent(self, event):
        """
        Handles the dialog close event.
        Ensures that temporary layers added during sampling are removed from the QGIS project.
        """
        # Remove temporary sampling layers from the AreaExclusionModule
        if hasattr(self, "area_exclusion") and self.area_exclusion:
            if hasattr(self.area_exclusion, "temp_sampling_layer") and self.area_exclusion.temp_sampling_layer:
                QgsProject.instance().removeMapLayer(self.area_exclusion.temp_sampling_layer.id())
            if hasattr(self.area_exclusion, "temp_coordinates_layer") and self.area_exclusion.temp_coordinates_layer:
                QgsProject.instance().removeMapLayer(self.area_exclusion.temp_coordinates_layer.id())

        # Remove temporary layers from the JudgmentalSampling module
        if hasattr(self, "judgmental_sampling") and self.judgmental_sampling:
            if hasattr(self.judgmental_sampling, "temp_layer") and self.judgmental_sampling.temp_layer:
                try:
                    QgsProject.instance().removeMapLayer(self.judgmental_sampling.temp_layer.id())
                except:
                    pass
                self.judgmental_sampling.temp_layer = None

        # Accept the close event to proceed with closing the dialog
        event.accept()

    # Updated method to open the license file with a pop-up dialog
    def open_license_file(self):
        """
        Opens a custom styled dialog with plugin information and buttons to view license or close.
        """
        try:
            custom_dialog = QtWidgets.QDialog(self)
            custom_dialog.setWindowTitle("About Sampling Time Plugin")
            custom_dialog.setStyleSheet("""
                QDialog {
                    background-color: #cccaca;
                    border: 2px solid #080808;
                    border-radius: 10px;
                }
                QLabel {
                    color: #2c3e50;
                    padding: 10px;
                    background-color: white;
                    border-radius: 5px;
                }
                QPushButton {
                    background-color: #080808;
                    color: white;
                    border: none;
                    padding: 8px 15px;
                    border-radius: 4px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #545454;
                }
                QPushButton:pressed {
                    background-color: #080808;
                }
            """)

            # Adjust (if desired) the minimum size of the dialog for better text visibility
            custom_dialog.setMinimumSize(650, 400)

            layout = QtWidgets.QVBoxLayout(custom_dialog)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)

            title_label = QtWidgets.QLabel("Sampling Time Plugin")
            title_label.setStyleSheet("""
                font-size: 18px;
                font-weight: bold;
                color: #080808;
                background-color: transparent;
            """)
            layout.addWidget(title_label)

            # ===== FULL TEXT, WITHOUT ELLIPSIS =====
            info_text = """<b>A comprehensive QGIS plugin for automated area sampling 
using judgmental, random, systematic, stratified, and cluster techniques. 
This plugin enables the creation of sampling areas, exclusion zones, customizable 
stratification and clustering, and generates shapefiles for outputs. 
Designed for precision and adaptability in geospatial workflows.</b><br><br>

Version: 0.1<br>
Begin: 2024-09-29<br>
Author: Marcel A. Cedrez Dacosta<br>
Contact: marcel.a@giscourse.online<br><br>

<b>How to use the plugin:</b> 
<a href="https://giscourse.online/qgis-sampling-time-plugin/">
https://giscourse.online/qgis-sampling-time-plugin/
</a><br><br>

License: This plugin is free software: you can redistribute it and/or modify it under 
the terms of the GNU General Public License as published by the Free Software Foundation, 
either version 3 of the License, or (at your option) any later version.<br><br>

Sampling Time Plugin is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. 
See the GNU General Public License for more details.
"""

            # Create the label with rich text properties and external links
            content_label = QtWidgets.QLabel()
            content_label.setTextFormat(Qt.RichText)
            content_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            content_label.setOpenExternalLinks(True)
            content_label.setText(info_text)
            content_label.setWordWrap(True)
            content_label.setStyleSheet("""
                font-size: 12px;
                font-weight: bold;
                color: #080808;
                padding: 14px;
                background-color: white;
                border-radius: 5px;
            """)

            # QScrollArea to prevent text from being cut off
            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(content_label)
            layout.addWidget(scroll_area)

            button_container = QtWidgets.QHBoxLayout()
            button_container.setSpacing(10)

            license_button = QtWidgets.QPushButton("LICENSE")
            close_button = QtWidgets.QPushButton("Close")

            button_container.addWidget(license_button)
            button_container.addWidget(close_button)
            layout.addLayout(button_container)

            license_button.clicked.connect(lambda: self._open_license_file(custom_dialog))
            close_button.clicked.connect(custom_dialog.close)

            custom_dialog.exec_()

        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Error opening dialog: {str(e)}"
            )

    def _open_license_file(self, parent_dialog):
        """Helper method to open the license file"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        license_file = os.path.join(current_dir, "LICENSE.txt")

        if os.path.exists(license_file):
            webbrowser.open(license_file)
        else:
            QMessageBox.warning(
                parent_dialog,
                "Error",
                f"License file not found at: {license_file}"
            )


class SamplingPlugin:
    """
    Serves as the entry point for the QGIS plugin.
    Integrates the plugin into the QGIS interface by adding toolbar icons and menu entries,
    manages the lifecycle of the plugin (initialization and unloading), and displays the main dialog when triggered.
    """
    def __init__(self, iface):
        """
        Initializes the plugin with a reference to the QGIS interface.
        """
        self.iface = iface  # QGIS interface
        self.dlg = None  # Placeholder for the dialog instance

    def initGui(self):
        """
        Initializes the GUI elements of the plugin.
        Adds a toolbar icon and menu entry for the plugin.
        """
        icon_path = ':/plugins/sampling_plugin/icon.png'
        # Create an action with an icon and name for the plugin
        self.action = QtWidgets.QAction(QIcon(icon_path), "Sampling Plugin", self.iface.mainWindow())
        # Connect the action to the method that shows the dialog
        self.action.triggered.connect(self.show_dialog)
        # Add the action to the QGIS toolbar and plugin menu
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Sampling Plugin", self.action)

    def unload(self):
        """
        Removes the plugin's GUI elements from the QGIS interface when the plugin is unloaded.
        """
        self.iface.removePluginMenu("&Sampling Plugin", self.action)
        self.iface.removeToolBarIcon(self.action)

    def show_dialog(self):
        """
        Displays the main dialog of the plugin.
        Ensures that only one instance of the dialog exists and brings it to the front if already open.
        """
        if self.dlg is None:
            # Instantiate the SamplingDialog if it doesn't exist
            self.dlg = SamplingDialog(self.iface)

        # If the dialog is minimized, restore and activate it
        if self.dlg.windowState() & Qt.WindowMinimized:
            self.dlg.setWindowState(self.dlg.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.dlg.raise_()  # Bring the dialog to the front
        self.dlg.activateWindow()  # Activate the dialog window
        self.dlg.show()  # Show the dialog
