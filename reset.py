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

# Import necessary Qt widgets
from qgis.PyQt.QtWidgets import (
    QCheckBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPushButton, QRadioButton,
    QMessageBox, QListWidget, QComboBox
)

# Import QGIS core project for layer management
from qgis.core import QgsProject

class ResetFunction:
    def __init__(self, dialog):
        # Constructor to set the dialog and define widget groups
        self.dialog = dialog
        
        # Assign pushbuttonclose directly
        self.dialog.pushbuttonclose = self.dialog.pushbuttonclose

        # Collect checkboxes that control different functionalities
        self.function_checkboxes = [
            self.dialog.checkBoxaddsamplesmanually,
            self.dialog.checkBoxaddsamplesbycoordinates,
            self.dialog.checkBoxaddsamplesbyfile,
            self.dialog.checkBoxaddsamplesrandomly,
            self.dialog.checkBoxaddsamplessystematically,
            self.dialog.checkBoxaddstratifiedsamplesrandomly,
            self.dialog.checkBoxaddstratifiedsamplessystematically,
            self.dialog.checkBoxaddclustersamplesrandomly,
            self.dialog.checkBoxaddclustersamplessystematically,
            self.dialog.checkBoxshpsamplingarea,
            self.dialog.checkBoxgenerateshpbycoordinates,
            self.dialog.checkBoxstratapolyline,
            self.dialog.checkBoxstratavoronoi,
            self.dialog.checkBoxstratalines
        ]
        
        # Shared widget group for manual outside sampling
        self.shared_outside_manual = [
            self.dialog.checkBoxoutsidesampling
        ]

        # Shared widget group for stratified options
        self.shared_stratified = [
            self.dialog.checkBoxoutsidesampling_stratified,
            self.dialog.doubleSpinBoxdistancestratifiedperimeter,
            self.dialog.doubleSpinBoxdistancestratifiedexclusion
        ]

        # Shared widget group for cluster options
        self.shared_cluster = [
            self.dialog.checkBoxoutsidesamplingcluster,
            self.dialog.doubleSpinBoxdistanceclusterperimeter,
            self.dialog.doubleSpinBoxdistanceclusterexclusion,
            self.dialog.radiobuttonmanual,
            self.dialog.lineeditclusterid,
            self.dialog.pushbuttonvalidateclusterid,
            self.dialog.radiobuttonrandom,
            self.dialog.spinboxrandonclusterid
        ]

        # Shared widget group for EPSG code
        self.shared_epsg = [
            self.dialog.lineEditEPSGcode
        ]

        # Collect all checkboxes
        self.all_checkboxes = [
            self.dialog.checkBoxaddsamplesmanually,
            self.dialog.checkBoxaddsamplesbycoordinates,
            self.dialog.checkBoxaddsamplesbyfile,
            self.dialog.checkBoxaddsamplesrandomly,
            self.dialog.checkBoxaddsamplessystematically,
            self.dialog.checkBoxaddstratifiedsamplesrandomly,
            self.dialog.checkBoxaddstratifiedsamplessystematically,
            self.dialog.checkBoxaddclustersamplesrandomly,
            self.dialog.checkBoxaddclustersamplessystematically,
            self.dialog.checkBoxshpsamplingarea,
            self.dialog.checkBoxgenerateshpbycoordinates,
            self.dialog.checkBoxstratapolyline,
            self.dialog.checkBoxstratavoronoi,
            self.dialog.checkBoxstratalines,
            self.dialog.checkBoxoutsidesampling,
            self.dialog.checkBoxoutsidesamplingrandom,
            self.dialog.checkBoxoutsidesampling_systematic,
            self.dialog.checkBoxoutsidesampling_stratified,
            self.dialog.checkBoxoutsidesamplingcluster,
            self.dialog.checkBoxadjustsamplesbysurfacearea,
            self.dialog.checkBoxadjustclustersamplesbysurfacearea,
            self.dialog.checkBoxstratifiedsampling_zigzagsystematic,
            self.dialog.checkBoxclustersampling_zigzagcluster,
            self.dialog.checkBoxoutsidesampling_zigzagsystematic
        ]

        # Collect all radio buttons
        self.all_radiobuttons = [
            self.dialog.radiobuttonmanual,
            self.dialog.radiobuttonrandom
        ]

        # Collect all spin boxes
        self.all_spinboxes = [
            self.dialog.spinBoxnumberofsamples,
            self.dialog.spinBoxanglesystematically,
            self.dialog.spinBoxnumberofstratifiedsamples,
            self.dialog.spinBoxnumberofclustersamples,
            self.dialog.spinBoxangleclustersystematically,
            self.dialog.spinboxrandonclusterid
        ]

        # Collect all double spin boxes
        self.all_doublespinboxes = [
            self.dialog.doubleSpinBoxdistancesamples,
            self.dialog.doubleSpinBoxdistanceexclusion,
            self.dialog.doubleSpinBoxdistanceperimeter,
            self.dialog.doubleSpinBoxdistanceperimetersamplearea,
            self.dialog.doubleSpinBoxdistanceperimeterexclusionarea,
            self.dialog.doubleSpinBoxdistancestratifiedsamples,
            self.dialog.doubleSpinBoxdistancestratifiedperimeter,
            self.dialog.doubleSpinBoxdistancestratifiedexclusion,
            self.dialog.doubleSpinBoxdistancexsamples,
            self.dialog.doubleSpinBoxdistanceysamples,
            self.dialog.doubleSpinBoxdistancestratifiedxsamples,
            self.dialog.doubleSpinBoxdistancestratifiedysamples,
            self.dialog.doubleSpinBoxdistanceclusterxsamples,
            self.dialog.doubleSpinBoxdistanceclusterysamples,
            self.dialog.doubleSpinBoxdistanceclusterperimeter,
            self.dialog.doubleSpinBoxdistanceclusterexclusion,
            self.dialog.doubleSpinBoxdistanceclustersamples
        ]

        # Collect all line edits
        self.all_lineedits = [
            self.dialog.lineEditsamplelabel,
            self.dialog.lineEditaddsamplesbyfile,
            self.dialog.lineEditxcoordinates_judgmental,
            self.dialog.lineEditycoordinate_judgmental,
            self.dialog.lineEditxcoordinates,
            self.dialog.lineEditycoordinate,
            self.dialog.lineEditEPSGcode,
            self.dialog.lineeditclusterid
        ]

        # Collect all list widgets
        self.all_listwidgets = [
            self.dialog.listWidgetexclusion,
            self.dialog.listWidgetlistofcoordinates,
            self.dialog.listWidgetlistofcoordinates_judgmental
        ]

        # Collect all combo boxes
        self.all_comboboxes = [
            self.dialog.comboBoxshpsampling,
            self.dialog.comboBoxsymbol,
            self.dialog.comboBoxcolumnx,
            self.dialog.comboBoxcolumny
        ]

    def reset_all(self):
        # Reset function checkboxes
        for cb in self.function_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
            
        # Reset shared widget groups
        self._reset_widgets(self.shared_outside_manual)
        self._reset_widgets(self.shared_stratified)
        self._reset_widgets(self.shared_cluster)
        self._reset_widgets(self.shared_epsg)
        
        # Re-initialize controls on the dialog
        self.dialog.initialize_controls()
        
        # Disable random sampling controls if not selected
        if not self.dialog.checkBoxaddsamplesrandomly.isChecked():
            self.dialog.random_sampling.disable_controls()

    def _reset_widgets(self, widget_list):
        # Helper method to reset widgets in a given list
        for w in widget_list:
            if isinstance(w, QCheckBox) or isinstance(w, QRadioButton):
                w.setChecked(False)
            elif isinstance(w, QSpinBox):
                w.setValue(0)
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(0.0)
            elif isinstance(w, QLineEdit):
                w.clear()

    def full_plugin_reset(self):
        # Full reset triggered by a confirmation dialog
        reply = QMessageBox.question(
            self.dialog,
            "Reset Plugin",
            "This action will reset the plugin to its initial state.\nAre you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Reset all checkboxes
            for cb in self.all_checkboxes:
                cb.setChecked(False)

            # Reset all radio buttons
            for rb in self.all_radiobuttons:
                rb.setChecked(False)

            # Reset all spin boxes
            for sb in self.all_spinboxes:
                sb.setValue(0)

            # Reset all double spin boxes
            for dsb in self.all_doublespinboxes:
                dsb.setValue(0.0)

            # Clear all line edits
            for le in self.all_lineedits:
                le.clear()

            # Clear all list widgets
            for lw in self.all_listwidgets:
                lw.clear()

            # Reset combo boxes to first index if available
            for cb in self.all_comboboxes:
                if cb.count() > 0:
                    cb.setCurrentIndex(0)

            # Repopulate shapefile layers
            self.dialog.layer_module.populate_shapefile_layers()

            # Remove temporary layers if they exist
            if hasattr(self.dialog, "area_exclusion") and self.dialog.area_exclusion:
                if hasattr(self.dialog.area_exclusion, "temp_sampling_layer") and self.dialog.area_exclusion.temp_sampling_layer:
                    QgsProject.instance().removeMapLayer(self.dialog.area_exclusion.temp_sampling_layer.id())
                    self.dialog.area_exclusion.temp_sampling_layer = None
                if hasattr(self.dialog.area_exclusion, "temp_coordinates_layer") and self.dialog.area_exclusion.temp_coordinates_layer:
                    QgsProject.instance().removeMapLayer(self.dialog.area_exclusion.temp_coordinates_layer.id())
                    self.dialog.area_exclusion.temp_coordinates_layer = None
                if hasattr(self.dialog.area_exclusion, "coordinates"):
                    self.dialog.area_exclusion.coordinates = []

            # Re-initialize controls
            self.dialog.initialize_controls()
            
            # Disable random sampling controls if not selected
            if not self.dialog.checkBoxaddsamplesrandomly.isChecked():
                self.dialog.random_sampling.disable_controls()

            # Notify the user of successful reset
            QMessageBox.information(
                self.dialog,
                "Reset Complete",
                "The plugin has been reset to its initial state."
            )

    def silent_full_reset(self):
        # Full reset without displaying any confirmation or info messages
        for cb in self.all_checkboxes:
            cb.setChecked(False)

        for rb in self.all_radiobuttons:
            rb.setChecked(False)

        for sb in self.all_spinboxes:
            sb.setValue(0)

        for dsb in self.all_doublespinboxes:
            dsb.setValue(0.0)

        for le in self.all_lineedits:
            le.clear()

        for lw in self.all_listwidgets:
            lw.clear()

        for cb in self.all_comboboxes:
            if cb.count() > 0:
                cb.setCurrentIndex(0)

        self.dialog.layer_module.populate_shapefile_layers()

        if hasattr(self.dialog, "area_exclusion") and self.dialog.area_exclusion:
            if hasattr(self.dialog.area_exclusion, "temp_sampling_layer") and self.dialog.area_exclusion.temp_sampling_layer:
                QgsProject.instance().removeMapLayer(self.dialog.area_exclusion.temp_sampling_layer.id())
                self.dialog.area_exclusion.temp_sampling_layer = None
            if hasattr(self.dialog.area_exclusion, "temp_coordinates_layer") and self.dialog.area_exclusion.temp_coordinates_layer:
                QgsProject.instance().removeMapLayer(self.dialog.area_exclusion.temp_coordinates_layer.id())
                self.dialog.area_exclusion.temp_coordinates_layer = None
            if hasattr(self.dialog.area_exclusion, "coordinates"):
                self.dialog.area_exclusion.coordinates = []

        self.dialog.initialize_controls()
        
        if not self.dialog.checkBoxaddsamplesrandomly.isChecked():
            self.dialog.random_sampling.disable_controls()

    def reset_specific_function(self, main_checkbox):
        # Reset everything, then check the chosen checkbox
        self.reset_all()
        main_checkbox.setChecked(True)
    
    def close_plugin(self):
        # Ask the user before closing and resetting
        reply = QMessageBox.question(
            self.dialog,
            "Close Plugin",
            "You are about to close the plugin. All settings will be reset to default. Do you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Perform a full reset silently and close
            self.silent_full_reset()
            self.dialog.close()
