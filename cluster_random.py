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
import random
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

# This thread-based class performs random sampling for each cluster
class SamplingWorker(QThread):
    progress = pyqtSignal(int)  # Signal to indicate current progress
    finished = pyqtSignal(bool, dict)  # Signal to indicate completion
    warning = pyqtSignal(str, str)  # Signal to communicate warnings

    def __init__(self, sampling_obj, samples_per_cluster):
        super().__init__()
        self.sampling_obj = sampling_obj
        self.is_cancelled = False
        self.samples = {}
        self.samples_per_cluster = samples_per_cluster

    # Main run method of the thread
    def run(self):
        try:
            samples_per_cluster = self.samples_per_cluster
            total_samples = sum(samples_per_cluster.values())
            samples_generated = 0

            # Iterate through each feature in the sampling area
            for feature in self.sampling_obj.sampling_area.getFeatures():
                cluster_id = feature.id() + 1
                if self.sampling_obj.selected_clusters:
                    if cluster_id not in self.sampling_obj.selected_clusters:
                        continue
                cluster_geom = feature.geometry()
                extent = cluster_geom.boundingBox()
                current_samples = []
                attempts = 0
                max_attempts = samples_per_cluster[cluster_id] * 2000

                # Generate random points until the desired number is reached or maximum attempts
                while len(current_samples) < samples_per_cluster[cluster_id] and attempts < max_attempts:
                    if self.is_cancelled:
                        self.finished.emit(False, {})
                        return

                    x = random.uniform(extent.xMinimum(), extent.xMaximum())
                    y = random.uniform(extent.yMinimum(), extent.yMaximum())
                    point = QgsPointXY(x, y)

                    if self.sampling_obj.is_valid_sample(point, cluster_geom, current_samples, show_warning=False):
                        current_samples.append(point)
                        samples_generated += 1
                        self.progress.emit(samples_generated)
                    attempts += 1

                # Emit warning if generation of all samples was not possible
                if len(current_samples) < samples_per_cluster[cluster_id]:
                    warning_text = (
                        f"Could not generate all requested samples for Cluster {cluster_id}.\n"
                        f"Requested samples: {samples_per_cluster[cluster_id]}\n"
                        f"Generated samples: {len(current_samples)}\n"
                        f"Attempts made: {attempts}"
                    )
                    self.warning.emit("Warning", warning_text)

                self.samples[cluster_id] = current_samples

            self.finished.emit(True, self.samples)

        except Exception:
            # Signal failure if an unexpected error occurs
            self.finished.emit(False, {})

    # Method to stop the sampling process
    def stop(self):
        self.is_cancelled = True


# Main class to handle cluster-based random sampling
class ClusterRandomSampling:
    def __init__(self, iface, ui):
        self.iface = iface  # QGIS interface
        self.ui = ui  # UI reference
        self.sampling_area = None  # Layer for sampling area
        self.exclusion_zones = []  # List of layers considered as exclusion zones
        self.min_samples_per_cluster = 0  # Minimum samples per cluster
        self.min_distance_samples = 0  # Minimum distance between samples
        self.min_distance_perimeter = 0  # Minimum distance from cluster perimeter
        self.min_distance_exclusion = 0  # Minimum distance from exclusion zones
        self.samples = {}  # Dictionary to store generated samples
        self.temp_layer = None  # Temporary in-memory layer for samples
        self.label_root = ""  # Prefix for sample labels
        self.selected_symbol = None  # Symbol for samples
        self.selected_symbol_editable = None  # Editable symbol path
        self.map_tool = None  # Map tool for manual sample placing
        self.allow_outside_sampling = False  # Whether samples can be placed outside the cluster area
        self.adjust_by_area = False  # Adjust samples per cluster based on area
        self.instructions_shown = False  # Flag to show instructions only once
        self.worker = None  # Thread worker
        self.progress_dialog = None  # Progress dialog

        # Enable keyboard tracking on distance spin boxes
        self.ui.doubleSpinBoxdistanceclusterperimeter.setKeyboardTracking(True)
        self.ui.doubleSpinBoxdistanceclusterexclusion.setKeyboardTracking(True)

        self.is_random_active = False  # Flag to control random sampling activation
        self.random_signals_connected = False  # Flag to track if signals are connected

        # Disable UI controls initially
        self.disable_controls()

        # Connect signals for UI elements
        self.ui.checkBoxaddclustersamplesrandomly.stateChanged.connect(
            self.on_checkBoxaddclustersamplesrandomly_stateChanged
        )
        self.ui.comboBoxshpsampling.currentIndexChanged.connect(
            self.on_comboBoxshpsampling_currentIndexChanged
        )
        self.ui.pushButtonclusterrandomstart.clicked.connect(
            self.on_pushButtonclusterrandomstart_clicked
        )
        self.ui.pushButtonclusterrandomreset.clicked.connect(
            self.on_pushButtonclusterrandomreset_clicked
        )
        self.ui.pushButtonclusterrandomsave.clicked.connect(
            self.on_pushButtonclusterrandomsave_clicked
        )
        self.ui.pushButtonexclusion.clicked.connect(self.update_exclusion_zones)
        self.ui.pushButtonsavesymbol.clicked.connect(self.on_pushButtonsavesymbol_clicked)
        self.ui.comboBoxsymbol.currentIndexChanged.connect(self.on_comboBoxsymbol_currentIndexChanged)

        self.ui.checkBoxoutsidesamplingcluster.stateChanged.connect(
            self.on_checkBoxoutsidesamplingcluster_stateChanged
        )

        self.selected_clusters = []  # List of chosen clusters
        self.ui.radiobuttonmanual.toggled.connect(self.on_manual_selection_toggled)
        self.ui.radiobuttonrandom.toggled.connect(self.on_random_selection_toggled)

        # Disable these controls until certain conditions are met
        self.ui.lineeditclusterid.setEnabled(False)
        self.ui.pushbuttonvalidateclusterid.setEnabled(False)
        self.ui.spinboxrandonclusterid.setEnabled(False)
        self.ui.radiobuttonmanual.setEnabled(False)
        self.ui.radiobuttonrandom.setEnabled(False)
        self.ui.label_51.setEnabled(False)
        self.ui.label_52.setEnabled(False)

        # Populate combo box for sampling area layers
        self.populate_sampling_area_combo_box()

        # Connect signal to handle layer removal
        QgsProject.instance().layerWillBeRemoved.connect(self.on_layer_removed)

    # Checks if the temporary layer is removed
    def on_layer_removed(self, layerId):
        if self.temp_layer is not None and layerId == self.temp_layer.id():
            self.temp_layer = None

    # Returns an icon based on layer geometry type
    def get_layer_icon(self, layer):
        if layer.type() != QgsMapLayerType.VectorLayer:
            return None

        if layer.geometryType() == QgsWkbTypes.PointGeometry:
            return QIcon(":/images/themes/default/mIconPointLayer.svg")
        elif layer.geometryType() == QgsWkbTypes.LineGeometry:
            return QIcon(":/images/themes/default/mIconLineLayer.svg")
        elif layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            return QIcon(":/images/themes/default/mIconPolygonLayer.svg")
        return None

    # Populate the combo box with available polygon layers
    def populate_sampling_area_combo_box(self):
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

    # Saves the chosen symbol from the combo box
    def on_pushButtonsavesymbol_clicked(self):
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

    # Updates symbol references upon combo box index change
    def on_comboBoxsymbol_currentIndexChanged(self, index):
        if index >= 0:
            symbol_path = self.ui.comboBoxsymbol.itemData(index, Qt.UserRole)
            if symbol_path:
                self.selected_symbol = symbol_path
                self.selected_symbol_editable = symbol_path

    # Disables several UI controls
    def disable_controls(self):
        controls = [
            self.ui.spinBoxnumberofclustersamples,
            self.ui.doubleSpinBoxdistanceclustersamples,
            self.ui.checkBoxadjustclustersamplesbysurfacearea,
            self.ui.pushButtonclusterrandomstart,
            self.ui.pushButtonclusterrandomreset,
            self.ui.pushButtonclusterrandomsave,
            self.ui.checkBoxoutsidesamplingcluster,
            self.ui.doubleSpinBoxdistanceclusterperimeter,
            self.ui.doubleSpinBoxdistanceclusterexclusion,
            self.ui.radiobuttonmanual,
            self.ui.radiobuttonrandom,
            self.ui.label_51,
            self.ui.label_52,
            self.ui.lineeditclusterid,
            self.ui.pushbuttonvalidateclusterid,
            self.ui.spinboxrandonclusterid
        ]
        for control in controls:
            control.setEnabled(False)

    # Enables relevant UI controls
    def enable_controls(self):
        controls = [
            self.ui.spinBoxnumberofclustersamples,
            self.ui.doubleSpinBoxdistanceclustersamples,
            self.ui.checkBoxadjustclustersamplesbysurfacearea,
            self.ui.pushButtonclusterrandomstart,
            self.ui.pushButtonclusterrandomreset,
            self.ui.pushButtonclusterrandomsave,
            self.ui.checkBoxoutsidesamplingcluster,
            self.ui.doubleSpinBoxdistanceclusterperimeter,
            self.ui.doubleSpinBoxdistanceclusterexclusion,
            self.ui.radiobuttonmanual,
            self.ui.radiobuttonrandom,
            self.ui.label_51,
            self.ui.label_52
        ]
        for control in controls:
            control.setEnabled(True)

    # Called when the checkbox for random cluster sampling is changed
    def on_checkBoxaddclustersamplesrandomly_stateChanged(self, state):
        if state == Qt.Checked:
            self.is_random_active = True
            self.connect_random_signals()
            self.enable_controls()
            # Enable radio buttons and labels
            self.ui.radiobuttonmanual.setEnabled(True)
            self.ui.radiobuttonrandom.setEnabled(True)
            self.ui.label_51.setEnabled(True)
            self.ui.label_52.setEnabled(True)

            # Update control states based on the selected mode
            if self.ui.radiobuttonmanual.isChecked():
                self.ui.lineeditclusterid.setEnabled(True)
                self.ui.pushbuttonvalidateclusterid.setEnabled(True)
                self.ui.spinboxrandonclusterid.setEnabled(False)
            elif self.ui.radiobuttonrandom.isChecked():
                self.ui.lineeditclusterid.setEnabled(False)
                self.ui.pushbuttonvalidateclusterid.setEnabled(False)
                self.ui.spinboxrandonclusterid.setEnabled(True)

            # Uncheck the systematic samples option to avoid conflicts
            self.ui.checkBoxaddclustersamplessystematically.setChecked(False)

            # Show instructions (only once)
            if not self.instructions_shown:
                QMessageBox.information(
                    self.ui,
                    "Instructions",
                    "Required settings:\n"
                    "- Set minimum number of samples per cluster\n\n"
                    "Optional settings:\n"
                    "- Set minimum distance between samples\n"
                    "- Set minimum distance between samples and the perimeter\n"
                    "- Set minimum distance between samples and exclusion zones\n"
                    "- 'Adjust by Surface Area': scales sample count based on cluster size\n"
                    "- 'Allow Outside Sampling': enables manual sampling outside perimeter\n\n"
                    "- Cluster Selection Mode:\n"
                    "  - 'Manual Selection': enter cluster IDs and click 'Validate ID' to confirm\n"
                    "  - 'Random Selection': specify the number of clusters to sample randomly\n"
                    "  - If neither is selected, sampling is performed across all clusters\n\n"
                    "Workflow:\n"
                    "1. Click 'Start' to generate samples\n"
                    "2. Use 'Reset' for a new set\n"
                    "3. Left click to add samples manually\n"
                    "4. Right click to remove samples\n"
                    "5. Click 'Save' when finished"
                )
                self.instructions_shown = True
        else:
            self.is_random_active = False
            self.disconnect_random_signals()
            self.disable_controls()
            self.instructions_shown = False
            self.ui.radiobuttonmanual.setChecked(False)
            self.ui.radiobuttonrandom.setChecked(False)
            self.ui.lineeditclusterid.clear()
            self.ui.spinboxrandonclusterid.setValue(0)
            self.selected_clusters = []

    # Connects signals associated with random sampling mode
    def connect_random_signals(self):
        try:
            self.ui.radiobuttonmanual.toggled.disconnect(self.on_manual_selection_toggled)
        except TypeError:
            pass
        try:
            self.ui.radiobuttonrandom.toggled.disconnect(self.on_random_selection_toggled)
        except TypeError:
            pass
        except TypeError:
            pass

        self.ui.radiobuttonmanual.toggled.connect(self.on_manual_selection_toggled)
        self.ui.radiobuttonrandom.toggled.connect(self.on_random_selection_toggled)
        self.random_signals_connected = True

    # Disconnects signals for random sampling
    def disconnect_random_signals(self):
        if self.random_signals_connected:
            try:
                self.ui.radiobuttonmanual.toggled.disconnect(self.on_manual_selection_toggled)
            except TypeError:
                pass
            try:
                self.ui.radiobuttonrandom.toggled.disconnect(self.on_random_selection_toggled)
            except TypeError:
                pass
            except TypeError:
                pass
            self.random_signals_connected = False

    # Triggered when the sampling area combo box index changes
    def on_comboBoxshpsampling_currentIndexChanged(self, index):
        if index >= 0:
            layer_name = self.ui.comboBoxshpsampling.currentText()
            layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == layer_name:
                    layer = lyr
                    break

            if layer and isinstance(layer, QgsVectorLayer):
                self.sampling_area = layer
                if self.ui.checkBoxaddclustersamplesrandomly.isChecked():
                    self.enable_controls()
                    self.ui.radiobuttonmanual.setEnabled(True)
                    self.ui.radiobuttonrandom.setEnabled(True)
                    self.ui.label_51.setEnabled(True)
                    self.ui.label_52.setEnabled(True)

    # Updates the exclusion zones by reading from the list widget
    def update_exclusion_zones(self):
        self.exclusion_zones = []
        for i in range(self.ui.listWidgetexclusion.count()):
            item = self.ui.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                self.exclusion_zones.append(layer)

    # Toggles outside sampling permission
    def on_checkBoxoutsidesamplingcluster_stateChanged(self, state):
        self.allow_outside_sampling = state == Qt.Checked

    # Gathers parameters from the UI
    def set_parameters(self):
        self.min_samples_per_cluster = self.ui.spinBoxnumberofclustersamples.value()
        self.min_distance_samples = self.ui.doubleSpinBoxdistanceclustersamples.value()
        self.min_distance_perimeter = self.ui.doubleSpinBoxdistanceclusterperimeter.value()
        self.min_distance_exclusion = self.ui.doubleSpinBoxdistanceclusterexclusion.value()
        self.allow_outside_sampling = self.ui.checkBoxoutsidesamplingcluster.isChecked()
        self.adjust_by_area = self.ui.checkBoxadjustclustersamplesbysurfacearea.isChecked()
        self.label_root = self.ui.lineEditsamplelabel.text().strip()

    # Sets the sampling area layer
    def set_sampling_area(self, layer):
        self.sampling_area = layer

    # Sets the exclusion zone layers
    def set_exclusion_zones(self, exclusion_layers):
        self.exclusion_zones = exclusion_layers

    # Sets the selected symbol for rendering
    def set_symbol(self, symbol, symbol_editable):
        self.selected_symbol = symbol
        self.selected_symbol_editable = symbol_editable

    # Chooses clusters depending on manual or random mode
    def select_clusters(self):
        if self.ui.radiobuttonmanual.isChecked():
            pass
        elif self.ui.radiobuttonrandom.isChecked():
            num_clusters = self.ui.spinboxrandonclusterid.value()
            total_clusters = self.sampling_area.featureCount()
            available_clusters = list(range(1, total_clusters + 1))
            selected_clusters = random.sample(available_clusters, min(num_clusters, total_clusters))
            self.selected_clusters = selected_clusters
        else:
            total_clusters = self.sampling_area.featureCount()
            self.selected_clusters = list(range(1, total_clusters + 1))

    # Computes how many samples per cluster, optionally adjusting by area
    def calculate_samples_per_cluster(self):
        samples_per_cluster = {}

        if not self.adjust_by_area:
            for cluster_id in self.selected_clusters:
                samples_per_cluster[cluster_id] = self.min_samples_per_cluster
        else:
            areas = {feature.id() + 1: feature.geometry().area()
                     for feature in self.sampling_area.getFeatures()}
            min_area = min(areas.values())

            for cluster_id in self.selected_clusters:
                area = areas.get(cluster_id, min_area)
                samples = int(round(self.min_samples_per_cluster * (area / min_area)))
                samples_per_cluster[cluster_id] = max(samples, self.min_samples_per_cluster)

        return samples_per_cluster

    # Calculates distance from point to the polygon boundary
    def calculate_distance_to_boundary(self, geometry, point_geom):
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

    # Checks if the sample is valid considering perimeter and exclusion constraints
    def is_valid_sample(self, point, cluster_geom, current_samples, show_warning=True, is_manual=False):
        point_geom = QgsGeometry.fromPointXY(point)

        # Check if the point is inside the cluster if not allowed outside
        if not (self.allow_outside_sampling and is_manual):
            if not cluster_geom.contains(point_geom):
                if show_warning:
                    QMessageBox.warning(self.ui, "Invalid Location", "Point is outside the cluster area.")
                return False

        # Verify against exclusion zones
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

        # Check distance from perimeter if required
        if self.min_distance_perimeter > 0:
            distance = self.calculate_distance_to_boundary(cluster_geom, point_geom)
            if distance < self.min_distance_perimeter:
                if show_warning:
                    QMessageBox.warning(
                        self.ui,
                        "Invalid Location",
                        f"Point too close to perimeter (min: {self.min_distance_perimeter}m)"
                    )
                return False

        # Check distance from other samples
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

    # Main method to generate samples in batch
    def generate_samples(self):
        try:
            if not self.sampling_area:
                QMessageBox.warning(self.ui, "Error", "No sampling area defined.")
                return False

            if self.temp_layer is not None:
                QMessageBox.information(self.ui, "Info", "Samples already exist. Use 'Reset' button to generate a new set.")
                return False

            self.samples = {}
            self.select_clusters()
            samples_per_cluster = self.calculate_samples_per_cluster()
            total_samples = sum(samples_per_cluster.values())

            self.progress_dialog = QProgressDialog("Generating cluster samples...", "Cancel", 0, total_samples, self.ui)
            self.progress_dialog.setWindowTitle("Progress")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setMinimumDuration(0)

            self.worker = SamplingWorker(self, samples_per_cluster)
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

    # Displays a warning message
    def show_warning(self, title, message):
        QMessageBox.warning(self.ui, title, message)

    # Called when the worker finishes generating samples
    def handle_worker_finished(self, success, samples):
        if success:
            self.samples = samples
            self.create_temp_layer()
        else:
            self.reset()
        self.progress_dialog.close()
        self.progress_dialog.deleteLater()
        self.progress_dialog = None

    # Creates an in-memory layer for visualizing generated samples
    def create_temp_layer(self):
        try:
            if self.temp_layer is not None:
                QgsProject.instance().removeMapLayer(self.temp_layer)
                self.temp_layer = None

            self.temp_layer = QgsVectorLayer(
                f"Point?crs={self.sampling_area.crs().authid()}",
                "Cluster Random Samples", "memory"
            )

            provider = self.temp_layer.dataProvider()
            provider.addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Cluster", QVariant.String),
                QgsField("Samples", QVariant.String),
                QgsField("X", QVariant.Double),
                QgsField("Y", QVariant.Double)
            ])
            self.temp_layer.updateFields()

            features = []
            sample_count = 1
            for cluster_id, points in self.samples.items():
                for point in points:
                    feature = QgsFeature(self.temp_layer.fields())
                    feature.setGeometry(QgsGeometry.fromPointXY(point))
                    sample_label = f"{self.label_root}{sample_count}" if self.label_root else str(sample_count)
                    cluster_label = f"Cluster {cluster_id}" if isinstance(cluster_id, int) else "Cluster outside"
                    feature.setAttributes([
                        sample_count,
                        cluster_label,
                        sample_label,
                        point.x(),
                        point.y()
                    ])
                    features.append(feature)
                    sample_count += 1

            provider.addFeatures(features)
            self.temp_layer.updateExtents()

            # Create a default symbol
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle',
                'color': '0,255,255',
                'outline_color': '0,0,0',
                'outline_width': '0.2',
                'size': '2.0'
            })

            self.temp_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            QgsProject.instance().addMapLayer(self.temp_layer)
            self.map_tool = ClusterRandomSamplingMapTool(self.iface.mapCanvas(), self)
            self.iface.mapCanvas().setMapTool(self.map_tool)

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error creating temporary layer: {str(e)}")

    # Adds a single sample point manually to the temp layer
    def add_sample(self, point):
        if self.temp_layer is None:
            self.create_temp_layer()

        point_geom = QgsGeometry.fromPointXY(point)

        cluster_id = None
        cluster_geom = None
        is_outside = True

        # Identify the cluster containing the point
        for feature in self.sampling_area.getFeatures():
            if feature.geometry().contains(point_geom):
                cluster_id = feature.id() + 1
                if self.selected_clusters:
                    if cluster_id not in self.selected_clusters:
                        QMessageBox.warning(self.ui, "Invalid Cluster", "Point is not within the selected clusters.")
                        return
                cluster_geom = feature.geometry()
                is_outside = False
                break

        # If not in any cluster, check if outside sampling is allowed
        if is_outside and not self.allow_outside_sampling:
            QMessageBox.warning(self.ui, "Invalid Location", "Point must be inside a cluster.")
            return

        # Use "outside" as the cluster identifier if outside sampling is allowed
        if is_outside and self.allow_outside_sampling:
            for feature in self.sampling_area.getFeatures():
                cluster_geom = feature.geometry()
                break
            cluster_id = "outside"

        # Validate the sample against constraints
        if not self.is_valid_sample(point, cluster_geom, self.samples.get(cluster_id, []),
                                    show_warning=True, is_manual=True):
            return

        if cluster_id not in self.samples:
            self.samples[cluster_id] = []
        self.samples[cluster_id].append(point)

        feature = QgsFeature(self.temp_layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        total_samples = sum(len(samples) for samples in self.samples.values())

        cluster_label = f"Cluster {cluster_id}" if isinstance(cluster_id, int) else "Cluster outside"

        feature.setAttributes([
            total_samples,
            cluster_label,
            f"{self.label_root}{total_samples}",
            point.x(),
            point.y()
        ])
        self.temp_layer.dataProvider().addFeatures([feature])
        self.temp_layer.updateExtents()
        self.renumber_samples()

    # Removes the nearest sample point by right-click
    def remove_sample(self, point):
        nearest_feature = None
        min_distance = float('inf')

        # Find the nearest feature
        for feature in self.temp_layer.getFeatures():
            distance = feature.geometry().distance(QgsGeometry.fromPointXY(point))
            if distance < min_distance:
                min_distance = distance
                nearest_feature = feature

        # Remove the feature from layer and from the samples dictionary
        if nearest_feature:
            cluster_label = nearest_feature.attribute("Cluster")
            point_geom = nearest_feature.geometry().asPoint()
            cluster_id = None
            if cluster_label.startswith("Cluster "):
                try:
                    cluster_id = int(cluster_label.split("Cluster ")[1])
                except ValueError:
                    if cluster_label == "Cluster outside":
                        cluster_id = "outside"

            if cluster_id is not None and cluster_id in self.samples:
                if cluster_id == "outside":
                    self.samples[cluster_id] = [p for p in self.samples[cluster_id]
                                                if p != point_geom]
                else:
                    self.samples[cluster_id] = [p for p in self.samples[cluster_id]
                                                if p != point_geom]

            self.temp_layer.dataProvider().deleteFeatures([nearest_feature.id()])
            self.temp_layer.updateExtents()
            self.renumber_samples()

    # Renumbers samples after additions or removals
    def renumber_samples(self):
        updates = {}
        new_id = 1

        for cluster_id, points in self.samples.items():
            for point in points:
                request = QgsFeatureRequest()
                request.setFilterRect(QgsGeometry.fromPointXY(point).boundingBox())
                for feature in self.temp_layer.getFeatures(request):
                    feat_geom = feature.geometry().asPoint()
                    if feat_geom == point:
                        updates[feature.id()] = {
                            self.temp_layer.fields().lookupField('ID'): new_id,
                            self.temp_layer.fields().lookupField('Samples'): f"{self.label_root}{new_id}",
                            self.temp_layer.fields().lookupField('Cluster'): f"Cluster {cluster_id}" if isinstance(cluster_id, int) else "Cluster outside",
                            self.temp_layer.fields().lookupField('X'): point.x(),
                            self.temp_layer.fields().lookupField('Y'): point.y()
                        }
                        new_id += 1

        self.temp_layer.dataProvider().changeAttributeValues(updates)
        self.temp_layer.triggerRepaint()

    # Resets the sampling process and removes layers
    def reset(self):
        if self.temp_layer:
            QgsProject.instance().removeMapLayer(self.temp_layer)
        self.samples = {}
        self.temp_layer = None
        if self.worker:
            self.worker.stop()
            self.worker = None

    # Start button clicked - attempts to generate the samples
    def on_pushButtonclusterrandomstart_clicked(self):
        try:
            if not self.sampling_area:
                QMessageBox.warning(self.ui, "Error", "Please select a sampling area first.")
                return

            if self.ui.radiobuttonmanual.isChecked() and not self.selected_clusters:
                QMessageBox.warning(self.ui, "Error", "Please validate cluster selection first.")
                return

            if self.ui.radiobuttonrandom.isChecked() and self.ui.spinboxrandonclusterid.value() <= 0:
                QMessageBox.warning(self.ui, "Error", "Please specify number of clusters to sample.")
                return

            feature_count = self.sampling_area.featureCount()
            if feature_count == 1:
                QMessageBox.warning(self.ui, "Warning", "The loaded shapefile contains only one area. Cluster sampling requires multiple clusters for optimal use.")

            if not self.samples:
                self.update_exclusion_zones()
                self.set_parameters()
                self.select_clusters()

                if self.generate_samples():
                    samples_per_cluster = self.calculate_samples_per_cluster()
                    message = "Cluster | Expected/Generated\n"
                    message += "-" * 26 + "\n"

                    total_expected = 0
                    total_generated = 0

                    # Show cluster-based summary
                    for cluster_id in sorted(samples_per_cluster.keys()):
                        expected = samples_per_cluster[cluster_id]
                        generated = len(self.samples.get(cluster_id, []))
                        warning = " ⚠️" if generated < expected else ""
                        message += f"{cluster_id:<7} | {expected}/{generated}{warning}\n"
                        total_expected += expected
                        total_generated += generated

                    message += "-" * 26 + "\n"
                    message += f"Total   | {total_expected}/{total_generated}"

                    QMessageBox.information(self.ui, "Generation Complete", message)
            else:
                QMessageBox.information(self.ui, "Info", "Samples already exist. Use 'Reset' button to generate a new set.")

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error generating samples: {str(e)}")

    # Reset button clicked - regenerates the samples
    def on_pushButtonclusterrandomreset_clicked(self):
        self.reset()
        self.update_exclusion_zones()
        self.set_parameters()
        self.select_clusters()
        success = self.generate_samples()
        if success:
            samples_per_cluster = self.calculate_samples_per_cluster()
            message = "Cluster | Expected/Generated\n"
            message += "-" * 26 + "\n"

            total_expected = 0
            total_generated = 0

            for cluster_id in sorted(samples_per_cluster.keys()):
                expected = samples_per_cluster[cluster_id]
                generated = len(self.samples.get(cluster_id, []))
                warning = " ⚠️" if generated < expected else ""
                message += f"{cluster_id:<7} | {expected}/{generated}{warning}\n"
                total_expected += expected
                total_generated += generated

            message += "-" * 26 + "\n"
            message += f"Total   | {total_expected}/{total_generated}"

            QMessageBox.information(self.ui, "Reset Complete", message)

    # Save button clicked - exports the samples to a shapefile
    def on_pushButtonclusterrandomsave_clicked(self):
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
                    QLineEdit.Normal, "cluster_random_samples"
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

    # Helper method to save the samples to disk
    def save_samples(self, output_dir, filename):
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

            # Check if the write operation succeeded
            if error[0] == QgsVectorFileWriter.NoError:
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

                    # Remove temp layer and clear samples
                    if self.temp_layer:
                        QgsProject.instance().removeMapLayer(self.temp_layer.id())
                        self.temp_layer = None

                    if self.map_tool:
                        self.iface.mapCanvas().unsetMapTool(self.map_tool)
                        self.map_tool = None

                    self.samples = {}

                    # Switch back to default pan tool
                    self.iface.actionPan().trigger()
                    
                    self.iface.mapCanvas().refresh()
                    return True

                return False

            return False

        except Exception as e:
            print(f"Error in save_samples: {str(e)}")
            QMessageBox.critical(self.ui, "Error", f"Error saving samples: {str(e)}")
            return False

    # Enables manual selection of cluster IDs
    def on_manual_selection_toggled(self, checked):
        if not self.is_random_active:
            return
        self.ui.lineeditclusterid.setEnabled(checked)
        self.ui.pushbuttonvalidateclusterid.setEnabled(checked)
        self.ui.spinboxrandonclusterid.setEnabled(False)
        if checked:
            self.selected_clusters = []

    # Enables random selection of cluster IDs
    def on_random_selection_toggled(self, checked):
        if not self.is_random_active:
            return
        self.ui.lineeditclusterid.setEnabled(False)
        self.ui.pushbuttonvalidateclusterid.setEnabled(False)
        self.ui.spinboxrandonclusterid.setEnabled(checked)
        if checked:
            self.selected_clusters = []

    # Validates the cluster IDs in manual mode
    def validate_cluster_selection(self):
        if not self.is_random_active:
            return

        if not self.sampling_area:
            QMessageBox.warning(self.ui, "Error", "Please select a sampling area first.")
            return

        cluster_text = self.ui.lineeditclusterid.text().strip()
        if not cluster_text:
            QMessageBox.warning(self.ui, "Error", "Please enter cluster IDs.")
            return

        try:
            cluster_ids = [int(x.strip()) for x in cluster_text.split(',')]
            total_clusters = self.sampling_area.featureCount()

            invalid_ids = [cid for cid in cluster_ids if cid < 1 or cid > total_clusters]
            if invalid_ids:
                QMessageBox.warning(
                    self.ui,
                    "Invalid Clusters",
                    f"Invalid cluster IDs: {invalid_ids}\nValid range: 1 to {total_clusters}"
                )
                return

            self.selected_clusters = cluster_ids
            QMessageBox.information(
                self.ui,
                "Success",
                f"Selected clusters validated: {self.selected_clusters}"
            )
        except ValueError:
            QMessageBox.warning(
                self.ui,
                "Error",
                "Invalid format. Please enter numbers separated by commas (e.g., 1,3,5)"
            )


# Custom map tool to add or remove samples with mouse clicks
class ClusterRandomSamplingMapTool(QgsMapTool):
    def __init__(self, canvas, sampling):
        super().__init__(canvas)
        self.sampling = sampling  # Reference to the ClusterRandomSampling instance

    # Handles mouse release events to add (left-click) or remove (right-click) samples
    def canvasReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.sampling.add_sample(self.toMapCoordinates(event.pos()))
        elif event.button() == Qt.RightButton:
            self.sampling.remove_sample(self.toMapCoordinates(event.pos()))
