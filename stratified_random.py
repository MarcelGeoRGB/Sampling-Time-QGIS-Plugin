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

import os  # Provides OS interface
import random  # Used for generating random numbers
from qgis.core import (
    QgsGeometry, QgsFeature, QgsPointXY, QgsVectorLayer, QgsField,
    QgsProject, QgsSingleSymbolRenderer, QgsMarkerSymbol, QgsVectorFileWriter,
    QgsWkbTypes, QgsSvgMarkerSymbolLayer, QgsFeatureRequest, QgsMapLayerType
)
from qgis.PyQt.QtCore import QVariant, Qt, QCoreApplication, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QMessageBox, QFileDialog, QInputDialog, QLineEdit, QProgressDialog
)
from qgis.gui import QgsMapTool
from qgis.PyQt.QtGui import QIcon


class SamplingWorker(QThread):
    # This class manages sample generation in a separate thread
    progress = pyqtSignal(int)  # Signals to update progress
    finished = pyqtSignal(bool, dict)  # Signals when process is done
    warning = pyqtSignal(str, str)  # Signals warning messages

    def __init__(self, sampling_obj):
        # Initializes the worker with the sampling object
        super().__init__()
        self.sampling_obj = sampling_obj
        self.is_cancelled = False
        self.samples = {}

    def run(self):
        # Performs sample generation
        try:
            samples_per_stratum = self.sampling_obj.calculate_samples_per_stratum()
            total_samples = sum(samples_per_stratum.values())
            samples_generated = 0

            for feature in self.sampling_obj.sampling_area.getFeatures():
                # If user cancels process
                if self.is_cancelled:
                    self.finished.emit(False, {})
                    return

                stratum_id = feature.id() + 1
                stratum_geom = feature.geometry()
                extent = stratum_geom.boundingBox()
                current_samples = []
                attempts = 0
                max_attempts = samples_per_stratum[stratum_id] * 2000

                while len(current_samples) < samples_per_stratum[stratum_id] and attempts < max_attempts:
                    # Check for cancel request
                    if self.is_cancelled:
                        self.finished.emit(False, {})
                        return

                    x = random.uniform(extent.xMinimum(), extent.xMaximum())
                    y = random.uniform(extent.yMinimum(), extent.yMaximum())
                    point = QgsPointXY(x, y)

                    # Check if the generated point is valid
                    if self.sampling_obj.is_valid_sample(point, stratum_geom, current_samples, show_warning=False):
                        current_samples.append(point)
                        samples_generated += 1
                        self.progress.emit(samples_generated)
                    attempts += 1

                # Issue warning if not enough samples were generated
                if len(current_samples) < samples_per_stratum[stratum_id]:
                    warning_text = (
                        f"Could not generate all requested samples for Stratum {stratum_id}.\n"
                        f"Requested samples: {samples_per_stratum[stratum_id]}\n"
                        f"Generated samples: {len(current_samples)}\n"
                        f"Attempts made: {attempts}\n"
                        f"This might be due to:\n"
                        f"- Distance constraints being too strict\n"
                        f"- Strata area being too small\n"
                        f"- Too many samples requested for the available space\n"
                        f"Try adjusting these parameters and try again."
                    )
                    self.warning.emit("Warning", warning_text)

                self.samples[stratum_id] = current_samples

            self.finished.emit(True, self.samples)

        except Exception:
            self.finished.emit(False, {})

    def stop(self):
        # Allows cancellation of the thread
        self.is_cancelled = True


class StratifiedRandomSampling:
    # Main class for handling stratified random sampling
    def __init__(self, iface, ui):
        # Stores QGIS interface and UI elements
        self.iface = iface
        self.ui = ui
        self.sampling_area = None
        self.exclusion_zones = []
        self.min_samples_per_stratum = 0
        self.min_distance_samples = 0
        self.min_distance_perimeter = 0
        self.min_distance_exclusion = 0
        self.samples = {}
        self.temp_layer = None
        self.label_root = ""
        self.selected_symbol = None
        self.selected_symbol_editable = None
        self.map_tool = None
        self.allow_outside_sampling = False
        self.adjust_by_area = False
        self.instructions_shown = False

        self.worker = None
        self.progress_dialog = None

        # Ensures spinbox changes are tracked
        self.ui.doubleSpinBoxdistancestratifiedperimeter.setKeyboardTracking(True)
        self.ui.doubleSpinBoxdistancestratifiedexclusion.setKeyboardTracking(True)

        # Disables certain controls initially
        self.disable_controls()

        # Connects interface signals
        self.ui.checkBoxaddstratifiedsamplesrandomly.stateChanged.connect(
            self.on_checkBoxaddstratifiedsamplesrandomly_stateChanged
        )
        self.ui.comboBoxshpsampling.currentIndexChanged.connect(
            self.on_comboBoxshpsampling_currentIndexChanged
        )
        self.ui.pushButtonstratifiedrandomstart.clicked.connect(
            self.on_pushButtonstratifiedrandomstart_clicked
        )
        self.ui.pushButtonstratifiedrandomreset.clicked.connect(
            self.on_pushButtonstratifiedrandomreset_clicked
        )
        self.ui.pushButtonstratifiedrandomsave.clicked.connect(
            self.on_pushButtonstratifiedrandomsave_clicked
        )
        self.ui.pushButtonexclusion.clicked.connect(self.update_exclusion_zones)
        self.ui.pushButtonsavesymbol.clicked.connect(self.on_pushButtonsavesymbol_clicked)
        self.ui.comboBoxsymbol.currentIndexChanged.connect(self.on_comboBoxsymbol_currentIndexChanged)

        self.ui.checkBoxoutsidesampling_stratified.stateChanged.connect(
            self.on_checkBoxoutsidesampling_stratified_stateChanged
        )

        # Populates available polygon layers
        self.populate_sampling_area_combo_box()

        # Connects layer removal event
        QgsProject.instance().layerWillBeRemoved.connect(self.on_layer_removed)

    def on_layer_removed(self, layerId):
        # Resets the temp layer if it is removed externally
        if self.temp_layer is not None and layerId == self.temp_layer.id():
            self.temp_layer = None

    def get_layer_icon(self, layer):
        # Returns icon for a layer based on geometry type
        if layer.type() != QgsMapLayerType.VectorLayer:
            return None

        if layer.geometryType() == QgsWkbTypes.PointGeometry:
            return QIcon(":/images/themes/default/mIconPointLayer.svg")
        elif layer.geometryType() == QgsWkbTypes.LineGeometry:
            return QIcon(":/images/themes/default/mIconLineLayer.svg")
        elif layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            return QIcon(":/images/themes/default/mIconPolygonLayer.svg")
        return None

    def populate_sampling_area_combo_box(self):
        # Fills the combo box with polygon layers
        self.ui.comboBoxshpsampling.clear()
        layers = QgsProject.instance().mapLayers().values()
        polygon_layers = [
            layer for layer in layers
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry
        ]
        for layer in polygon_layers:
            icon = self.get_layer_icon(layer)
            if icon:
                self.ui.comboBoxshpsampling.addItem(icon, layer.name())
            else:
                self.ui.comboBoxshpsampling.addItem(layer.name())

    def on_pushButtonsavesymbol_clicked(self):
        # Saves the chosen symbol for future usage
        current_index = self.ui.comboBoxsymbol.currentIndex()
        if current_index >= 0:
            symbol_paths = self.ui.comboBoxsymbol.itemData(current_index, Qt.UserRole)
            if isinstance(symbol_paths, tuple):
                symbol_path = symbol_paths[0]
            else:
                symbol_path = symbol_paths

            if symbol_path:
                self.selected_symbol = symbol_path
                self.selected_symbol_editable = symbol_path
                print("Symbol saved:", self.selected_symbol_editable)

    def on_comboBoxsymbol_currentIndexChanged(self, index):
        # Updates the currently selected symbol
        if index >= 0:
            symbol_path = self.ui.comboBoxsymbol.itemData(index, Qt.UserRole)
            if symbol_path:
                self.selected_symbol = symbol_path
                self.selected_symbol_editable = symbol_path

    def disable_controls(self):
        # Disables UI controls to prevent interactions
        controls = [
            self.ui.spinBoxnumberofstratifiedsamples,
            self.ui.doubleSpinBoxdistancestratifiedsamples,
            self.ui.checkBoxadjustsamplesbysurfacearea,
            self.ui.pushButtonstratifiedrandomstart,
            self.ui.pushButtonstratifiedrandomreset,
            self.ui.pushButtonstratifiedrandomsave,
            self.ui.checkBoxoutsidesampling_stratified,
            self.ui.doubleSpinBoxdistancestratifiedperimeter,
            self.ui.doubleSpinBoxdistancestratifiedexclusion
        ]
        for control in controls:
            control.setEnabled(False)

    def enable_controls(self):
        # Enables UI controls for interactions
        controls = [
            self.ui.spinBoxnumberofstratifiedsamples,
            self.ui.doubleSpinBoxdistancestratifiedsamples,
            self.ui.checkBoxadjustsamplesbysurfacearea,
            self.ui.pushButtonstratifiedrandomstart,
            self.ui.pushButtonstratifiedrandomreset,
            self.ui.pushButtonstratifiedrandomsave,
            self.ui.checkBoxoutsidesampling_stratified,
            self.ui.doubleSpinBoxdistancestratifiedperimeter,
            self.ui.doubleSpinBoxdistancestratifiedexclusion
        ]
        for control in controls:
            control.setEnabled(True)

    def update_exclusion_zones(self):
        # Updates the list of exclusion zones from the UI
        self.exclusion_zones = []
        for i in range(self.ui.listWidgetexclusion.count()):
            item = self.ui.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                self.exclusion_zones.append(layer)

    def on_checkBoxoutsidesampling_stratified_stateChanged(self, state):
        # Toggles the option to place samples outside the stratum
        self.allow_outside_sampling = state == Qt.Checked

    def on_checkBoxaddstratifiedsamplesrandomly_stateChanged(self, state):
        # Enables or disables controls based on checkbox state
        if state == Qt.Checked:
            self.enable_controls()
            if not self.instructions_shown:
                QMessageBox.information(
                    self.ui,
                    "Instructions",
                    "Required settings:\n"
                    "- Set minimum number of samples per stratum\n\n"
                    "Optional settings:\n"
                    "- Set minimum distance between samples\n"
                    "- 'Adjust by Surface Area': scales sample count based on stratum size\n"
                    "- 'Allow Outside Sampling': enables manual sampling outside perimeter\n"
                    "- Set minimum distance between samples and the perimeter\n"
                    "- Set minimum distance between samples and exclusion zones\n\n"
                    "Workflow:\n"
                    "1. Click 'Start' to generate samples\n"
                    "2. Use 'Reset' for a new set\n"
                    "3. Left click to add samples manually\n"
                    "4. Right click to remove samples\n"
                    "5. Click 'Save' when finished"
                )
                self.instructions_shown = True
        else:
            self.disable_controls()
            self.instructions_shown = False

    def on_comboBoxshpsampling_currentIndexChanged(self, index):
        # Updates the sampling_area when a different polygon layer is selected
        try:
            layer_name = self.ui.comboBoxshpsampling.currentText().split(" [")[0]
            layers = QgsProject.instance().mapLayersByName(layer_name)
            if layers:
                layer = layers[0]
                if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.set_sampling_area(layer)
                else:
                    QMessageBox.warning(self.ui, "Invalid Layer", "Please select a polygon vector layer as the sampling area.")
                    self.sampling_area = None
            else:
                self.sampling_area = None
        except Exception as e:
            print(f"Error in sampling area selection: {e}")

    def set_parameters(self):
        # Retrieves parameter values from the UI
        self.min_samples_per_stratum = self.ui.spinBoxnumberofstratifiedsamples.value()
        self.min_distance_samples = self.ui.doubleSpinBoxdistancestratifiedsamples.value()
        self.min_distance_perimeter = self.ui.doubleSpinBoxdistancestratifiedperimeter.value()
        self.min_distance_exclusion = self.ui.doubleSpinBoxdistancestratifiedexclusion.value()
        self.allow_outside_sampling = self.ui.checkBoxoutsidesampling_stratified.isChecked()
        self.adjust_by_area = self.ui.checkBoxadjustsamplesbysurfacearea.isChecked()
        self.label_root = self.ui.lineEditsamplelabel.text().strip()

    def set_sampling_area(self, layer):
        # Sets the polygon layer to be used as the sampling area
        self.sampling_area = layer

    def set_exclusion_zones(self, exclusion_layers):
        # Sets layers to be used as exclusion zones
        self.exclusion_zones = exclusion_layers

    def set_symbol(self, symbol, symbol_editable):
        # Updates the selected symbol for sample points
        self.selected_symbol = symbol
        self.selected_symbol_editable = symbol_editable

    def calculate_samples_per_stratum(self):
        # Calculates how many samples to place in each stratum
        samples_per_stratum = {}
        if not self.adjust_by_area:
            for feature in self.sampling_area.getFeatures():
                samples_per_stratum[feature.id() + 1] = self.min_samples_per_stratum
            return samples_per_stratum

        areas = {feature.id() + 1: feature.geometry().area()
                 for feature in self.sampling_area.getFeatures()}
        min_area = min(areas.values())

        for feat_id, area in areas.items():
            samples = int(round(self.min_samples_per_stratum * (area / min_area)))
            samples_per_stratum[feat_id] = max(samples, self.min_samples_per_stratum)

        return samples_per_stratum

    def calculate_distance_to_boundary(self, geometry, point_geom):
        # Measures the distance from a point to the polygon boundary
        if geometry.type() == QgsWkbTypes.PolygonGeometry:
            if geometry.isMultipart():
                distances = [
                    QgsGeometry.fromPolylineXY(ring).distance(point_geom)
                    for polygon in geometry.asMultiPolygon()
                    for ring in polygon
                ]
                return min(distances) if distances else float('inf')
            else:
                return min(
                    QgsGeometry.fromPolylineXY(ring).distance(point_geom)
                    for ring in geometry.asPolygon()
                )
        return geometry.distance(point_geom)

    def is_valid_sample(self, point, stratum_geom, current_samples, show_warning=True, is_manual=False):
        # Verifies if a new sample point complies with all constraints
        point_geom = QgsGeometry.fromPointXY(point)

        # Check if point is within the stratum (if outside sampling is not allowed)
        if not (self.allow_outside_sampling and is_manual):
            if not stratum_geom.contains(point_geom):
                if show_warning:
                    QMessageBox.warning(self.ui, "Invalid Location", "Point is outside the stratum area.")
                return False

        # Check if point intersects exclusion zones
        if self.exclusion_zones:
            for zone in self.exclusion_zones:
                for feature in zone.getFeatures():
                    exclusion_geom = feature.geometry()
                    if exclusion_geom.contains(point_geom):
                        if show_warning:
                            QMessageBox.warning(self.ui, "Invalid Location", "Point is inside an exclusion zone.")
                        return False

                    if self.min_distance_exclusion > 0:
                        if exclusion_geom.distance(point_geom) < self.min_distance_exclusion:
                            if show_warning:
                                QMessageBox.warning(
                                    self.ui,
                                    "Invalid Location",
                                    f"Point too close to exclusion zone (min: {self.min_distance_exclusion}m)"
                                )
                            return False

        # Check if the point is within a minimum distance from the perimeter
        if self.min_distance_perimeter > 0:
            distance = self.calculate_distance_to_boundary(stratum_geom, point_geom)
            if distance < self.min_distance_perimeter:
                if show_warning:
                    QMessageBox.warning(
                        self.ui,
                        "Invalid Location",
                        f"Point too close to perimeter (min: {self.min_distance_perimeter}m)"
                    )
                return False

        # Check distance to other samples
        if self.min_distance_samples > 0 and current_samples:
            if any(point.distance(sample) < self.min_distance_samples for sample in current_samples):
                if show_warning:
                    QMessageBox.warning(
                        self.ui,
                        "Invalid Location",
                        f"Point too close to another sample (min: {self.min_distance_samples}m)"
                    )
                return False

        return True

    def show_warning(self, title, message):
        # Displays a warning message box
        QMessageBox.warning(self.ui, title, message)

    def handle_worker_finished(self, success, samples):
        # Called when the worker finishes sample generation
        if success:
            self.samples = samples
            self.create_temp_layer()
        else:
            self.reset()
        self.progress_dialog.close()
        self.progress_dialog.deleteLater()
        self.progress_dialog = None

    def generate_samples(self):
        # Starts the sample generation process
        try:
            if not self.sampling_area:
                QMessageBox.warning(self.ui, "Error", "No sampling area defined.")
                return False

            if self.temp_layer is not None:
                QMessageBox.information(self.ui, "Info", "Samples already exist. Use 'Reset' button to generate a new set.")
                return False

            self.samples = {}
            samples_per_stratum = self.calculate_samples_per_stratum()
            total_samples = sum(samples_per_stratum.values())

            self.progress_dialog = QProgressDialog("Generating stratified samples...", "Cancel", 0, total_samples, self.ui)
            self.progress_dialog.setWindowTitle("Progress")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setMinimumDuration(0)

            self.worker = SamplingWorker(self)
            self.worker.progress.connect(self.progress_dialog.setValue)
            self.worker.finished.connect(self.handle_worker_finished)
            self.worker.warning.connect(self.show_warning)
            self.progress_dialog.canceled.connect(self.worker.stop)

            self.worker.start()
            result = self.progress_dialog.exec_()
            if result == QProgressDialog.Rejected:
                self.worker.stop()
            return True

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error generating samples: {str(e)}")
            return False

    def create_temp_layer(self):
        # Builds a temporary layer to hold the generated samples
        try:
            if self.temp_layer is not None:
                QgsProject.instance().removeMapLayer(self.temp_layer)
                self.temp_layer = None

            self.temp_layer = QgsVectorLayer(
                f"Point?crs={self.sampling_area.crs().authid()}",
                "Stratified Random Samples", "memory"
            )

            provider = self.temp_layer.dataProvider()
            provider.addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Strata", QVariant.String),
                QgsField("Samples", QVariant.String),
                QgsField("X", QVariant.Double),
                QgsField("Y", QVariant.Double)
            ])
            self.temp_layer.updateFields()

            features = []
            sample_count = 1
            for stratum_id, points in self.samples.items():
                for point in points:
                    feature = QgsFeature(self.temp_layer.fields())
                    feature.setGeometry(QgsGeometry.fromPointXY(point))
                    sample_label = f"{self.label_root}{sample_count}" if self.label_root else str(sample_count)
                    strata_label = f"Stratum {stratum_id}" if isinstance(stratum_id, int) else "Stratum outside"
                    feature.setAttributes([
                        sample_count,
                        strata_label,
                        sample_label,
                        point.x(),
                        point.y()
                    ])
                    features.append(feature)
                    sample_count += 1

            provider.addFeatures(features)
            self.temp_layer.updateExtents()

            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle',
                'color': '0,255,255',
                'outline_color': '0,0,0',
                'outline_width': '0.2',
                'size': '2.0'
            })

            self.temp_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            QgsProject.instance().addMapLayer(self.temp_layer)
            self.map_tool = StratifiedRandomSamplingMapTool(self.iface.mapCanvas(), self)
            self.iface.mapCanvas().setMapTool(self.map_tool)

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error creating temporary layer: {str(e)}")

    def add_sample(self, point):
        # Adds a new sample point to the layer and updates internal data
        if self.temp_layer is None:
            self.create_temp_layer()

        point_geom = QgsGeometry.fromPointXY(point)

        stratum_id = None
        stratum_geom = None
        is_outside = True

        for feature in self.sampling_area.getFeatures():
            if feature.geometry().contains(point_geom):
                stratum_id = feature.id() + 1
                stratum_geom = feature.geometry()
                is_outside = False
                break

        # Check if sample is outside
        if is_outside and not self.allow_outside_sampling:
            QMessageBox.warning(self.ui, "Invalid Location", "Point must be inside a stratum.")
            return

        if is_outside and self.allow_outside_sampling:
            for feature in self.sampling_area.getFeatures():
                stratum_geom = feature.geometry()
                break
            stratum_id = "outside"

        # Validate the sample location
        if not self.is_valid_sample(point, stratum_geom, self.samples.get(stratum_id, []),
                                   show_warning=True, is_manual=True):
            return

        if stratum_id not in self.samples:
            self.samples[stratum_id] = []
        self.samples[stratum_id].append(point)

        feature = QgsFeature(self.temp_layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        total_samples = sum(len(samples) for samples in self.samples.values())

        strata_label = f"Stratum {stratum_id}" if isinstance(stratum_id, int) else "Stratum outside"

        feature.setAttributes([
            total_samples,
            strata_label,
            f"{self.label_root}{total_samples}",
            point.x(),
            point.y()
        ])
        self.temp_layer.dataProvider().addFeatures([feature])
        self.temp_layer.updateExtents()
        self.renumber_samples()

    def remove_sample(self, point):
        # Finds and removes the nearest sample to the provided point
        nearest_feature = None
        min_distance = float('inf')

        for feature in self.temp_layer.getFeatures():
            distance = feature.geometry().distance(QgsGeometry.fromPointXY(point))
            if distance < min_distance:
                min_distance = distance
                nearest_feature = feature

        if nearest_feature:
            strata_label = nearest_feature.attribute("Strata")
            point_geom = nearest_feature.geometry().asPoint()
            stratum_id = None
            if strata_label.startswith("Stratum "):
                try:
                    stratum_id = int(strata_label.split("Stratum ")[1])
                except ValueError:
                    if strata_label == "Stratum outside":
                        stratum_id = "outside"

            if stratum_id is not None and stratum_id in self.samples:
                if stratum_id == "outside":
                    self.samples[stratum_id] = [p for p in self.samples[stratum_id]
                                                if p != point_geom]
                else:
                    self.samples[stratum_id] = [p for p in self.samples[stratum_id]
                                                if p != point_geom]

            self.temp_layer.dataProvider().deleteFeatures([nearest_feature.id()])
            self.temp_layer.updateExtents()
            self.renumber_samples()

    def renumber_samples(self):
        # Renumbers all samples in the temp layer to maintain a valid sequence
        updates = {}
        new_id = 1

        for stratum_id, points in self.samples.items():
            for point in points:
                request = QgsFeatureRequest()
                request.setFilterRect(QgsGeometry.fromPointXY(point).boundingBox())
                for feature in self.temp_layer.getFeatures(request):
                    feat_geom = feature.geometry().asPoint()
                    if feat_geom == point:
                        updates[feature.id()] = {
                            self.temp_layer.fields().lookupField('ID'): new_id,
                            self.temp_layer.fields().lookupField('Samples'): f"{self.label_root}{new_id}",
                            self.temp_layer.fields().lookupField('Strata'): f"Stratum {stratum_id}" if isinstance(stratum_id, int) else "Stratum outside",
                            self.temp_layer.fields().lookupField('X'): point.x(),
                            self.temp_layer.fields().lookupField('Y'): point.y()
                        }
                        new_id += 1

        self.temp_layer.dataProvider().changeAttributeValues(updates)
        self.temp_layer.triggerRepaint()

    def reset(self):
        # Resets the sampling process and removes the temp layer
        if self.temp_layer:
            QgsProject.instance().removeMapLayer(self.temp_layer)
        self.samples = {}
        self.temp_layer = None
        if self.worker:
            self.worker.stop()
            self.worker = None

    def on_pushButtonstratifiedrandomstart_clicked(self):
        # Handles the logic when 'Start' button is clicked
        try:
            if not self.sampling_area:
                QMessageBox.warning(self.ui, "Error", "Please select a sampling area first.")
                return

            feature_count = self.sampling_area.featureCount()
            if feature_count == 1:
                QMessageBox.warning(self.ui, "Warning", "The loaded shapefile contains only one area. Stratified sampling requires multiple strata for optimal use.")

            if not self.samples:
                self.update_exclusion_zones()
                self.set_parameters()

                if self.generate_samples():
                    samples_per_stratum = self.calculate_samples_per_stratum()
                    message = "Stratum | Expected/Generated\n"
                    message += "-" * 26 + "\n"

                    total_expected = 0
                    total_generated = 0

                    for stratum_id in sorted(samples_per_stratum.keys()):
                        expected = samples_per_stratum[stratum_id]
                        generated = len(self.samples.get(stratum_id, []))
                        warning = " ⚠️" if generated < expected else ""
                        message += f"{stratum_id:<7} | {expected}/{generated}{warning}\n"
                        total_expected += expected
                        total_generated += generated

                    message += "-" * 26 + "\n"
                    message += f"Total   | {total_expected}/{total_generated}"

                    QMessageBox.information(self.ui, "Generation Complete", message)
            else:
                QMessageBox.information(self.ui, "Info", "Samples already exist. Use 'Reset' button to generate a new set.")

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error generating samples: {str(e)}")

    def on_pushButtonstratifiedrandomreset_clicked(self):
        # Resets the process and immediately generates a new set of samples
        self.reset()
        self.update_exclusion_zones()
        self.set_parameters()
        success = self.generate_samples()
        if success:
            samples_per_stratum = self.calculate_samples_per_stratum()
            message = "Stratum | Expected/Generated\n"
            message += "-" * 26 + "\n"

            total_expected = 0
            total_generated = 0

            for stratum_id in sorted(samples_per_stratum.keys()):
                expected = samples_per_stratum[stratum_id]
                generated = len(self.samples.get(stratum_id, []))
                warning = " ⚠️" if generated < expected else ""
                message += f"{stratum_id:<7} | {expected}/{generated}{warning}\n"
                total_expected += expected
                total_generated += generated

            message += "-" * 26 + "\n"
            message += f"Total   | {total_expected}/{total_generated}"

            QMessageBox.information(self.ui, "Reset Complete", message)

    def on_pushButtonstratifiedrandomsave_clicked(self):
        # Saves the generated samples to an ESRI Shapefile
        try:
            if not self.temp_layer or not self.samples:
                QMessageBox.warning(self.ui, "Error", "No samples to save.")
                return

            output_dir = QFileDialog.getExistingDirectory(
                self.ui, "Select Output Directory",
                QgsProject.instance().homePath(),
                QFileDialog.ShowDirsOnly
            )

            if output_dir:
                filename, ok = QInputDialog.getText(
                    self.ui, "Save Samples", "Enter filename:",
                    QLineEdit.Normal, "stratified_random_samples"
                )

                if ok and filename:
                    if self.save_samples(output_dir, filename):
                        QMessageBox.information(
                            self.ui, "Success",
                            "Samples have been saved successfully."
                        )
                        return
                    else:
                        QMessageBox.critical(
                            self.ui, "Error",
                            "Failed to save samples. Please check the output location and try again."
                        )

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error saving samples: {str(e)}")

    def save_samples(self, output_dir, filename):
        # Writes the samples to a shapefile and optionally applies a custom symbol
        try:
            if not self.temp_layer or not self.samples:
                return False

            self.renumber_samples()
            output_path = os.path.join(output_dir, f"{filename}.shp")

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "ESRI Shapefile"
            options.fileEncoding = "UTF-8"

            error = QgsVectorFileWriter.writeAsVectorFormat(
                self.temp_layer,
                output_path,
                options
            )

            if error[0] == QgsVectorFileWriter.NoError:
                # Attempt to use custom symbol if available
                if self.selected_symbol_editable:
                    try:
                        symbol_path = self.selected_symbol_editable.replace('symbol_icon', 'symbol_icon2')
                        symbol = QgsMarkerSymbol.createSimple({'name': 'circle'})
                        svg_symbol = QgsSvgMarkerSymbolLayer(symbol_path)
                        symbol.changeSymbolLayer(0, svg_symbol)
                    except Exception as e:
                        print(f"Error creating symbol: {str(e)}")
                        symbol = QgsMarkerSymbol.createSimple({
                            'name': 'circle',
                            'color': '255,0,0',
                            'outline_color': '0,0,0',
                            'outline_width': '0.2'
                        })
                else:
                    symbol = QgsMarkerSymbol.createSimple({
                        'name': 'circle',
                        'color': '255,0,0',
                        'outline_color': '0,0,0',
                        'outline_width': '0.2'
                    })

                renderer = QgsSingleSymbolRenderer(symbol)
                new_layer = QgsVectorLayer(output_path, filename, "ogr")
                if new_layer.isValid():
                    new_layer.setRenderer(renderer)
                    new_layer.triggerRepaint()
                    QgsProject.instance().addMapLayer(new_layer)

                    if self.temp_layer:
                        QgsProject.instance().removeMapLayer(self.temp_layer.id())
                        self.temp_layer = None

                    if self.map_tool:
                        self.iface.mapCanvas().unsetMapTool(self.map_tool)
                        self.map_tool = None

                    self.samples = {}

                    self.iface.actionPan().trigger()

                    self.iface.mapCanvas().refresh()
                    return True

                return False

            return False

        except Exception as e:
            print(f"Error in save_samples: {str(e)}")
            QMessageBox.critical(self.ui, "Error", f"Error saving samples: {str(e)}")
            return False


class StratifiedRandomSamplingMapTool(QgsMapTool):
    # Custom map tool to add/remove samples by clicking
    def __init__(self, canvas, sampling):
        super().__init__(canvas)
        self.sampling = sampling

    def canvasReleaseEvent(self, event):
        # Adds or removes a sample based on mouse button
        if event.button() == Qt.LeftButton:
            self.sampling.add_sample(self.toMapCoordinates(event.pos()))
        elif event.button() == Qt.RightButton:
            self.sampling.remove_sample(self.toMapCoordinates(event.pos()))
