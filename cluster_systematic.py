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

# These imports provide necessary classes and functions for QGIS operations
import os
import math
import random
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog, QInputDialog, QProgressDialog, QApplication
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
    QgsPointXY, QgsField, QgsSymbol, QgsSingleSymbolRenderer,
    QgsVectorFileWriter, QgsSvgMarkerSymbolLayer, QgsWkbTypes,
    QgsFeatureRequest, QgsSpatialIndex, QgsRectangle, QgsDistanceArea
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker
from qgis.PyQt.QtGui import QColor

class ClusterSystematicSampling:
    # This class manages cluster-based systematic sampling methods and GUI interactions

    def __init__(self, iface, dialog):
        # Constructor to initialize references to the QGIS interface, dialog, and parameters
        self.iface = iface
        self.dialog = dialog
        self.canvas = iface.mapCanvas() if iface else None
        self.sampling_area = None
        self.exclusion_zones = []
        self.temp_layer = None
        self.sample_count = 0
        self.spacing_x = 0
        self.spacing_y = 0
        self.label_root = ""
        self.samples = []
        self.grid_tool = None
        self.rubber_band = None
        self.perimeter_buffer_sample_area = 0
        self.perimeter_buffer_exclusion_area = 0
        self.distance_area = QgsDistanceArea()
        self.sample_markers = []
        self.apply_zigzag = False
        self.allow_outside_sampling = False
        self.selected_clusters = []
        self.is_systematic_active = False
        self.systematic_signals_connected = False

        # Connecting checkbox signals to handle sampling outside, cluster creation, etc.
        self.dialog.checkBoxoutsidesamplingcluster.stateChanged.connect(
            self.on_checkBoxoutsidesamplingcluster_stateChanged
        )

        self.dialog.checkBoxaddclustersamplessystematically.stateChanged.connect(
            self.on_checkBoxaddclustersamplessystematically_stateChanged
        )

        self.dialog.checkBoxaddclustersamplesrandomly.stateChanged.connect(
            self.on_checkBoxaddclustersamplesrandomly_stateChanged
        )

        self.dialog.comboBoxshpsampling.currentIndexChanged.connect(
            self.on_comboBoxshpsampling_currentIndexChanged
        )

        # Disabling some GUI components by default
        self.dialog.radiobuttonmanual.setEnabled(False)
        self.dialog.radiobuttonrandom.setEnabled(False)
        self.dialog.label_51.setEnabled(False)
        self.dialog.label_52.setEnabled(False)
        self.dialog.lineeditclusterid.setEnabled(False)
        self.dialog.pushbuttonvalidateclusterid.setEnabled(False)
        self.dialog.spinboxrandonclusterid.setEnabled(False)

        self.dialog.spinBoxangleclustersystematically.setEnabled(False)
        self.dialog.pushButtonclustersystematicstart.setEnabled(False)
        self.dialog.pushButtonclustersystematicsave.setEnabled(False)
        self.dialog.doubleSpinBoxdistanceclusterxsamples.setEnabled(False)
        self.dialog.doubleSpinBoxdistanceclusterysamples.setEnabled(False)
        self.dialog.doubleSpinBoxdistanceclusterperimeter.setEnabled(False)
        self.dialog.doubleSpinBoxdistanceclusterexclusion.setEnabled(False)
        self.dialog.checkBoxclustersampling_zigzagcluster.setEnabled(False)
        self.dialog.checkBoxoutsidesamplingcluster.setEnabled(False)

        # Initial call to manage UI based on checkbox state
        self.on_checkBoxaddclustersamplessystematically_stateChanged(
            self.dialog.checkBoxaddclustersamplessystematically.checkState()
        )

        # Connecting signal when a layer is removed from the project
        QgsProject.instance().layerWillBeRemoved.connect(self.on_layer_removed)

    def on_layer_removed(self, layer_id):
        # Resets temporary layer reference if the layer is removed
        if self.temp_layer is not None and layer_id == self.temp_layer.id():
            self.temp_layer = None

    def on_checkBoxaddclustersamplessystematically_stateChanged(self, state):
        # Activates or deactivates GUI elements for systematic sampling based on checkbox
        enable_widgets = (state == Qt.Checked)
        self.is_systematic_active = enable_widgets

        if enable_widgets:
            self.dialog.checkBoxaddclustersamplesrandomly.setChecked(False)
            self.dialog.radiobuttonmanual.setEnabled(True)
            self.dialog.radiobuttonrandom.setEnabled(True)
            self.dialog.label_51.setEnabled(True)
            self.dialog.label_52.setEnabled(True)

            if self.dialog.radiobuttonmanual.isChecked():
                self.dialog.lineeditclusterid.setEnabled(True)
                self.dialog.pushbuttonvalidateclusterid.setEnabled(True)
                self.dialog.spinboxrandonclusterid.setEnabled(False)
            elif self.dialog.radiobuttonrandom.isChecked():
                self.dialog.lineeditclusterid.setEnabled(False)
                self.dialog.pushbuttonvalidateclusterid.setEnabled(False)
                self.dialog.spinboxrandonclusterid.setEnabled(True)
            
            # Display a message box with user instructions
            QMessageBox.information(
                self.dialog,
                "Instructions",
                "Required settings:\n"
                "- Enter spacing values for X and Y axes\n\n"
                "Optional settings:\n"
                "- Set minimum distances from sampling area perimeter\n"
                "- Set minimum distances from exclusion zones\n"
                "- Set azimuth angle for grid rotation\n"
                "- Enable zigzag pattern in sampling\n"
                "- Allow sampling outside the perimeter\n\n"
                "- Cluster Selection Mode:\n"
                "  - 'Manual Selection': enter cluster IDs and click 'Validate ID' to confirm\n"
                "  - 'Random Selection': specify the number of clusters to sample randomly\n"
                "  - If neither is selected, sampling is performed across all clusters\n\n"
                "Workflow:\n"
                "1. Click 'Start' to generate the grid\n"
                "2. Position grid as desired and press 'Enter'\n"
                "3. Left click to add samples manually\n"
                "4. Right click to remove samples\n"
                "5. Click 'Save' to create the final shapefile"
            )

        if enable_widgets and not self.systematic_signals_connected:
            self.connect_systematic_signals()
        elif not enable_widgets and self.systematic_signals_connected:
            self.disconnect_systematic_signals()
        
        # Enabling or disabling widgets
        self.dialog.spinBoxangleclustersystematically.setEnabled(enable_widgets)
        self.dialog.pushButtonclustersystematicstart.setEnabled(enable_widgets)
        self.dialog.pushButtonclustersystematicsave.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistanceclusterxsamples.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistanceclusterysamples.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistanceclusterperimeter.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistanceclusterexclusion.setEnabled(enable_widgets)
        self.dialog.checkBoxclustersampling_zigzagcluster.setEnabled(enable_widgets)
        self.dialog.checkBoxoutsidesamplingcluster.setEnabled(enable_widgets)
        
        # Resetting states if unchecked
        if not enable_widgets:
            self.dialog.radiobuttonmanual.setChecked(False)
            self.dialog.radiobuttonrandom.setChecked(False)
            self.dialog.lineeditclusterid.clear()
            self.dialog.spinboxrandonclusterid.setValue(0)
            self.selected_clusters = []

    def on_checkBoxaddclustersamplesrandomly_stateChanged(self, state):
        # Manages state of random sampling checkbox
        if state == Qt.Checked:
            self.dialog.checkBoxaddclustersamplessystematically.setChecked(False)
            if self.systematic_signals_connected:
                self.disconnect_systematic_signals()

    def connect_systematic_signals(self):
        # Connects signals used for systematic sampling controls
        if not self.systematic_signals_connected:
            self.dialog.radiobuttonmanual.toggled.connect(self.on_manual_selection_toggled)
            self.dialog.radiobuttonrandom.toggled.connect(self.on_random_selection_toggled)
            self.dialog.lineeditclusterid.textChanged.connect(self.on_cluster_text_changed)
            self.systematic_signals_connected = True

    def disconnect_systematic_signals(self):
        # Disconnects signals used for systematic sampling controls
        if self.systematic_signals_connected:
            self.dialog.radiobuttonmanual.toggled.disconnect(self.on_manual_selection_toggled)
            self.dialog.radiobuttonrandom.toggled.disconnect(self.on_random_selection_toggled)
            self.dialog.lineeditclusterid.textChanged.disconnect(self.on_cluster_text_changed)
            self.systematic_signals_connected = False

    def on_comboBoxshpsampling_currentIndexChanged(self, index):
        # Updates the currently selected sampling area layer
        if index >= 0:
            layer_name = self.dialog.comboBoxshpsampling.currentText().split(" [")[0]
            layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == layer_name:
                    layer = lyr
                    break

            if layer and isinstance(layer, QgsVectorLayer):
                self.sampling_area = layer

    def on_checkBoxoutsidesamplingcluster_stateChanged(self, state):
        # Toggles allowing samples outside the cluster boundary
        self.allow_outside_sampling = (state == Qt.Checked)

    def on_manual_selection_toggled(self, checked):
        # Enables manual entry of cluster IDs if manual selection is checked
        if not self.is_systematic_active:
            return
        if self.dialog.checkBoxaddclustersamplessystematically.isChecked():
            self.dialog.lineeditclusterid.setEnabled(checked)
            self.dialog.pushbuttonvalidateclusterid.setEnabled(checked)
            self.dialog.spinboxrandonclusterid.setEnabled(False)
            if checked:
                self.selected_clusters = []
                self.dialog.lineeditclusterid.clear()

    def on_random_selection_toggled(self, checked):
        # Toggles random selection and its related widgets
        if not self.is_systematic_active:
            return
        if self.dialog.checkBoxaddclustersamplessystematically.isChecked():
            self.dialog.lineeditclusterid.setEnabled(False)
            self.dialog.pushbuttonvalidateclusterid.setEnabled(False)
            self.dialog.spinboxrandonclusterid.setEnabled(checked)
            if checked:
                self.selected_clusters = []
                self.process_random_selection()

    def on_cluster_text_changed(self):
        # Processes changes in the manual cluster ID text box
        if not self.is_systematic_active:
            return
        if self.dialog.radiobuttonmanual.isChecked():
            self.process_manual_selection()

    def validate_cluster_selection(self):
        # Validates the manually entered cluster IDs
        if not self.is_systematic_active:
            return
            
        if not self.sampling_area:
            QMessageBox.warning(self.dialog, "Error", "Please select a sampling area first.")
            return

        cluster_text = self.dialog.lineeditclusterid.text().strip()
        if not cluster_text:
            QMessageBox.warning(self.dialog, "Error", "Please enter cluster IDs.")
            return

        try:
            cluster_ids = [int(x.strip()) for x in cluster_text.split(',')]
            total_clusters = self.sampling_area.featureCount()

            invalid_ids = [cid for cid in cluster_ids if cid < 1 or cid > total_clusters]
            if invalid_ids:
                QMessageBox.warning(
                    self.dialog,
                    "Invalid Clusters",
                    f"Invalid cluster IDs: {invalid_ids}\nValid range: 1 to {total_clusters}"
                )
                return

            self.selected_clusters = cluster_ids
            QMessageBox.information(
                self.dialog,
                "Success",
                f"Selected clusters validated: {self.selected_clusters}"
            )         
        except ValueError:
            QMessageBox.warning(
                self.dialog,
                "Error",
                "Invalid format. Please enter numbers separated by commas (e.g., 1,3,5)"
            )

    def process_manual_selection(self):
        # Automatically updates the selected clusters based on manual entry
        if not self.sampling_area:
            return

        cluster_text = self.dialog.lineeditclusterid.text().strip()
        if not cluster_text:
            self.selected_clusters = []
            return

        try:
            cluster_ids = [int(x.strip()) for x in cluster_text.split(',')]
            total_clusters = self.sampling_area.featureCount()
            valid_ids = [cid for cid in cluster_ids if 1 <= cid <= total_clusters]
            self.selected_clusters = valid_ids
        except ValueError:
            self.selected_clusters = []

    def process_random_selection(self):
        # Randomly selects a specified number of clusters from the total
        if not self.sampling_area:
            return

        num_clusters = self.dialog.spinboxrandonclusterid.value()
        if num_clusters <= 0:
            self.selected_clusters = []
            return

        total_clusters = self.sampling_area.featureCount()
        self.selected_clusters = random.sample(range(1, total_clusters + 1), 
                                             min(num_clusters, total_clusters))

    def rotate_point(self, point, angle_degrees, center):
        # Rotates a given point around a center using an angle in degrees
        math_angle = (90 - angle_degrees) % 180
        angle_rad = math.radians(math_angle)
        x_shifted = point.x() - center.x()
        y_shifted = point.y() - center.y()
        x_new = x_shifted * math.cos(angle_rad) - y_shifted * math.sin(angle_rad) + center.x()
        y_new = x_shifted * math.sin(angle_rad) + y_shifted * math.cos(angle_rad) + center.y()
        return QgsPointXY(x_new, y_new)

    def set_sampling_area(self, layer):
        # Sets the sampling area layer to be used for sampling
        self.sampling_area = layer

    def set_exclusion_zones(self, exclusion_layers):
        # Sets the layers that define exclusion zones
        self.exclusion_zones = exclusion_layers

    def set_parameters(self, spacing_x, spacing_y, label_root, perimeter_buffer_sample_area, perimeter_buffer_exclusion_area):
        # Configures parameters for spacing, labeling, and buffers
        self.spacing_x = spacing_x
        self.spacing_y = spacing_y
        self.label_root = label_root
        self.perimeter_buffer_sample_area = perimeter_buffer_sample_area
        self.perimeter_buffer_exclusion_area = perimeter_buffer_exclusion_area
        self.apply_zigzag = self.dialog.checkBoxclustersampling_zigzagcluster.isChecked()
        self.allow_outside_sampling = self.dialog.checkBoxoutsidesamplingcluster.isChecked()

    def get_combined_geometry(self):
        # Merges geometries of the sampling area features into one
        features = self.sampling_area.getFeatures()
        geoms = [f.geometry() for f in features]
        if not geoms:
            return None
        combined_geom = QgsGeometry.unaryUnion(geoms)
        return combined_geom

    def generate_initial_grid(self):
        # Creates an initial grid of sample points covering a buffered area around the sampling region
        if not self.sampling_area:
            QMessageBox.warning(self.dialog, "Error", "Please select a sampling area first.")
            return

        if self.dialog.radiobuttonmanual.isChecked():
            cluster_text = self.dialog.lineeditclusterid.text().strip()
            if not cluster_text:
                QMessageBox.warning(self.dialog, "Error", "Please enter cluster IDs.")
                return
            
            if not self.selected_clusters:
                QMessageBox.warning(self.dialog, "Error", 
                                  "Please validate your cluster selection first.")
                return
                
        elif self.dialog.radiobuttonrandom.isChecked():
            num_clusters = self.dialog.spinboxrandonclusterid.value()
            if num_clusters <= 0:
                QMessageBox.warning(self.dialog, "Error", 
                                  "Please specify number of clusters to sample.")
                return
            self.process_random_selection()

        extent = self.sampling_area.extent()
        width = extent.width()
        height = extent.height()
        max_dimension = max(width, height)
        buffer_distance = max_dimension * 0.2

        combined_geom = self.get_combined_geometry()
        if not combined_geom:
            QMessageBox.critical(self.dialog, "Error", "Failed to calculate combined geometry for buffering.")
            return
        buffered_geom = combined_geom.buffer(buffer_distance, 50)

        centroid_geom = buffered_geom.centroid()
        if centroid_geom is None or centroid_geom.isEmpty():
            QMessageBox.critical(self.dialog, "Error", "Failed to calculate centroid for circular buffer.")
            return
        centroid = centroid_geom.asPoint()

        max_distance = 0
        vertices = []
        if buffered_geom.type() == QgsWkbTypes.PolygonGeometry:
            if buffered_geom.isMultipart():
                polygons = buffered_geom.asMultiPolygon()
            else:
                polygons = [buffered_geom.asPolygon()]
            for polygon in polygons:
                for ring in polygon:
                    vertices.extend(ring)
        elif buffered_geom.type() == QgsWkbTypes.LineGeometry:
            if buffered_geom.isMultipart():
                lines = buffered_geom.asMultiPolyline()
            else:
                lines = [buffered_geom.asPolyline()]
            for line in lines:
                vertices.extend(line)
        else:
            vertices = [centroid]

        for vertex in vertices:
            distance = centroid.distance(vertex)
            if distance > max_distance:
                max_distance = distance

        radius = max_distance

        circular_geom = QgsGeometry.fromPointXY(centroid).buffer(radius, 50)

        grid_extent = circular_geom.boundingBox()
        x_min = grid_extent.xMinimum()
        x_max = grid_extent.xMaximum()
        y_min = grid_extent.yMinimum()
        y_max = grid_extent.yMaximum()

        self.samples = []
        row_count = 0

        y = y_max
        while y >= y_min:
            x = x_min

            offset = 0
            if self.apply_zigzag and row_count % 2 != 0:
                offset = self.spacing_x / 2

            while x <= x_max:
                point = QgsPointXY(x + offset, y)
                point_geom = QgsGeometry.fromPointXY(point)
                if circular_geom.contains(point_geom):
                    self.samples.append(point)
                x += self.spacing_x
            y -= self.spacing_y
            row_count += 1

    def create_feature(self, id_num, point, cluster_id):
        # Generates a QgsFeature with given attributes for a point in a cluster
        feature = QgsFeature(self.temp_layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        feature.setAttributes([
            id_num,
            f"Cluster {cluster_id}",
            f"{self.label_root}{id_num}",
            point.x(),
            point.y()
        ])
        return feature

    def update_rubber_band(self):
        # Updates the rubber band display to show sample points on the map canvas
        if not self.canvas:
            return

        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.rubber_band.setColor(QColor(0, 255, 255))
        self.rubber_band.setFillColor(QColor(0, 255, 255, 255))
        self.rubber_band.setIcon(QgsRubberBand.ICON_CIRCLE)
        self.rubber_band.setIconSize(7)
        for point in self.samples:
            self.rubber_band.addPoint(point)

    def move_grid(self, dx, dy):
        # Moves the entire grid by offset (dx, dy)
        self.samples = [QgsPointXY(p.x() + dx, p.y() + dy) for p in self.samples]
        self.update_rubber_band()

    def update_sample_markers(self):
        # Updates the layer and symbol for sample points after movement or editing
        if not self.canvas:
            return

        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
            self.rubber_band = None

        for marker in self.sample_markers:
            self.canvas.scene().removeItem(marker)
        self.sample_markers = []

        if self.temp_layer:
            QgsProject.instance().removeMapLayer(self.temp_layer)

        self.temp_layer = QgsVectorLayer("Point?crs=" + self.sampling_area.crs().authid(), "Temporary Cluster Systematic Samples", "memory")
        self.temp_layer.dataProvider().addAttributes([
            QgsField("ID", QVariant.Int),
            QgsField("Cluster", QVariant.String),
            QgsField("Samples", QVariant.String),
            QgsField("X coordinates", QVariant.Double),
            QgsField("Y coordinates", QVariant.Double)
        ])
        self.temp_layer.updateFields()

        features = []
        current_id = 1
        for point in self.samples:
            point_geom = QgsGeometry.fromPointXY(point)
            point_added = False
            for feature in self.sampling_area.getFeatures():
                if feature.geometry().contains(point_geom):
                    cluster_id = feature.id() + 1
                    feat = self.create_feature(current_id, point, cluster_id)
                    features.append(feat)
                    current_id += 1
                    point_added = True
                    break
            if not point_added and self.allow_outside_sampling:
                feat = self.create_feature(current_id, point, "outside")
                features.append(feat)
                current_id += 1

        self.temp_layer.dataProvider().addFeatures(features)

        symbol = QgsSymbol.defaultSymbol(self.temp_layer.geometryType())
        symbol.setColor(QColor(0, 255, 255))
        symbol.setSize(2)
        renderer = QgsSingleSymbolRenderer(symbol)
        self.temp_layer.setRenderer(renderer)

        QgsProject.instance().addMapLayer(self.temp_layer)
        self.canvas.refresh()

    def filter_samples(self):
        # Filters the grid points, ensuring they meet cluster and exclusion criteria
        valid_samples = []
        samples_per_cluster = {}
        total_samples = 0

        progress = QProgressDialog("Processing samples...", "Cancel", 0, len(self.samples), self.dialog)
        progress.setWindowTitle("Progress")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        for i, point in enumerate(self.samples):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            QApplication.processEvents()

            point_geom = QgsGeometry.fromPointXY(point)
            
            for feature in self.sampling_area.getFeatures():
                cluster_id = feature.id() + 1
                
                if self.selected_clusters and cluster_id not in self.selected_clusters:
                    continue

                cluster_geom = feature.geometry()

                if cluster_geom.contains(point_geom):
                    if self.perimeter_buffer_sample_area > 0:
                        buffered = cluster_geom.buffer(-self.perimeter_buffer_sample_area, 5)
                        if not buffered.contains(point_geom):
                            continue

                    valid_for_exclusion = True
                    for zone in self.exclusion_zones:
                        for excl_feature in zone.getFeatures():
                            excl_geom = excl_feature.geometry()
                            if self.perimeter_buffer_exclusion_area > 0:
                                excl_geom = excl_geom.buffer(self.perimeter_buffer_exclusion_area, 5)
                            if excl_geom.contains(point_geom):
                                valid_for_exclusion = False
                                break
                        if not valid_for_exclusion:
                            break

                    if valid_for_exclusion:
                        valid_samples.append(point)
                        if cluster_id not in samples_per_cluster:
                            samples_per_cluster[cluster_id] = 0
                        samples_per_cluster[cluster_id] += 1
                        total_samples += 1

        progress.close()
        self.samples = valid_samples
        self.update_sample_markers()

        message = "Samples generated per cluster:\n"
        message += "-" * 30 + "\n"
        for cluster_id, count in sorted(samples_per_cluster.items()):
            message += f"Cluster {cluster_id}: {count} samples\n"
        message += "-" * 30 + "\n"
        message += f"Total samples: {total_samples}"

        QMessageBox.information(self.dialog, "Sampling Complete", message)

    def remove_sample(self, point):
        # Removes the sample point nearest to a given location
        if not self.samples:
            return
        closest_point = min(self.samples, key=lambda p: p.distance(point))
        if closest_point.distance(point) < self.spacing_x / 2:
            self.samples.remove(closest_point)
            self.update_sample_markers()

    def add_sample(self, point):
        # Adds a new sample point if it meets the validity checks
        if self.temp_layer is None:
            self.update_sample_markers()

        if self.is_point_valid(point):
            self.samples.append(point)
            self.update_sample_markers()

    def is_point_valid(self, point):
        # Validates if a point is inside the cluster area and not in exclusion zones
        point_geom = QgsGeometry.fromPointXY(point)
        valid_cluster = False

        for feature in self.sampling_area.getFeatures():
            cluster_geom = feature.geometry()
            if cluster_geom.contains(point_geom):
                valid_cluster = True
                if self.perimeter_buffer_sample_area > 0:
                    buffered = cluster_geom.buffer(-self.perimeter_buffer_sample_area, 5)
                    if not buffered.contains(point_geom):
                        QMessageBox.warning(
                            self.dialog,
                            "Invalid Location",
                            f"Point too close to cluster perimeter (min: {self.perimeter_buffer_sample_area}m)"
                        )
                        return False
                break

        if not valid_cluster and not self.allow_outside_sampling:
            QMessageBox.warning(self.dialog, "Invalid Location", "Point must be inside a cluster")
            return False

        for zone in self.exclusion_zones:
            for feature in zone.getFeatures():
                exclusion_geom = feature.geometry()
                if self.perimeter_buffer_exclusion_area > 0:
                    exclusion_geom = exclusion_geom.buffer(self.perimeter_buffer_exclusion_area, 5)
                if exclusion_geom.contains(point_geom):
                    QMessageBox.warning(
                        self.dialog,
                        "Invalid Location",
                        f"Point too close to exclusion zone (min: {self.perimeter_buffer_exclusion_area}m)"
                    )
                    return False

        return True

    def start_sampling(self):
        # Initiates the systematic sampling process and displays the grid for positioning
        if not self.canvas:
            QMessageBox.warning(self.dialog, "Error", "Map canvas not available.")
            return

        if self.spacing_x <= 0 or self.spacing_y <= 0:
            QMessageBox.warning(
                self.dialog,
                "Invalid Spacing",
                "Please enter positive X and Y spacing values before generating samples."
            )
            return

        progress = QProgressDialog("Generating systematic grid...", "Cancel", 0, 100, self.dialog)
        progress.setWindowTitle("Progress")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        try:
            self.dialog.showMinimized()

            progress.setValue(20)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            self.temp_layer = QgsVectorLayer(
                "Point?crs=" + self.sampling_area.crs().authid(),
                "Temporary Cluster Systematic Samples",
                "memory"
            )
            self.temp_layer.dataProvider().addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Cluster", QVariant.String),
                QgsField("Samples", QVariant.String),
                QgsField("X coordinates", QVariant.Double),
                QgsField("Y coordinates", QVariant.Double)
            ])
            self.temp_layer.updateFields()

            progress.setValue(40)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            self.generate_initial_grid()

            progress.setValue(60)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            angle = self.dialog.spinBoxangleclustersystematically.value()

            combined_geom = self.get_combined_geometry()
            if not combined_geom:
                QMessageBox.critical(self.dialog, "Error", "Failed to calculate combined geometry of the sampling area.")
                return

            progress.setValue(80)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            centroid_geom = combined_geom.centroid()
            if centroid_geom is None or centroid_geom.isEmpty():
                QMessageBox.critical(self.dialog, "Error", "Failed to calculate centroid of the sampling area.")
                return
            centroid = centroid_geom.asPoint()

            # Rotates all samples around the centroid by the user-defined angle
            self.samples = [self.rotate_point(p, angle, centroid) for p in self.samples]

            self.update_rubber_band()

            progress.setValue(100)
            QApplication.processEvents()

            # Sets the map tool to allow the user to move and position the grid
            self.grid_tool = ClusterSystematicSamplingMapTool(self.iface, self)
            self.canvas.setMapTool(self.grid_tool)

            progress.close()
            QMessageBox.information(
                self.dialog,
                "Move Grid",
                "Click and drag to move the grid. Press 'Enter' to confirm the position."
            )

        except Exception as e:
            progress.close()
            QMessageBox.critical(self.dialog, "Error", f"Error starting sampling: {str(e)}")

    def save_samples(self, output_dir, filename):
        # Saves the filtered or manually adjusted sample points as a new shapefile
        try:
            if not self.samples:
                QMessageBox.warning(self.dialog, "Error", "No samples to save.")
                return False

            output_layer = QgsVectorLayer(
                "Point?crs=" + self.sampling_area.crs().authid(),
                filename,
                "memory"
            )
            output_layer.dataProvider().addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Cluster", QVariant.String),
                QgsField("Samples", QVariant.String),
                QgsField("X coordinates", QVariant.Double),
                QgsField("Y coordinates", QVariant.Double)
            ])
            output_layer.updateFields()

            features = []
            current_id = 1
            for point in self.samples:
                point_geom = QgsGeometry.fromPointXY(point)
                point_added = False
                for feature in self.sampling_area.getFeatures():
                    if feature.geometry().contains(point_geom):
                        cluster_id = feature.id() + 1
                        feat = self.create_feature(current_id, point, cluster_id)
                        features.append(feat)
                        current_id += 1
                        point_added = True
                        break
                if not point_added and self.allow_outside_sampling:
                    feat = self.create_feature(current_id, point, "outside")
                    features.append(feat)
                    current_id += 1

            output_layer.dataProvider().addFeatures(features)

            output_path = os.path.join(output_dir, f"{filename}.shp")
            QgsVectorFileWriter.writeAsVectorFormat(
                output_layer,
                output_path,
                "UTF-8",
                self.sampling_area.crs(),
                "ESRI Shapefile"
            )

            saved_layer = QgsVectorLayer(output_path, filename, "ogr")
            if not saved_layer.isValid():
                QMessageBox.critical(
                    self.dialog,
                    "Error",
                    "Failed to create the cluster systematic sampling shapefile."
                )
                return False

            # Applies a symbol if available in the dialog's module; otherwise sets default
            symbol_path = getattr(self.dialog.layer_module, 'selected_symbol_editable', None)
            if symbol_path:
                symbol = QgsSymbol.defaultSymbol(saved_layer.geometryType())
                svg_symbol_layer = QgsSvgMarkerSymbolLayer(symbol_path)
                symbol.changeSymbolLayer(0, svg_symbol_layer)
                renderer = QgsSingleSymbolRenderer(symbol)
                saved_layer.setRenderer(renderer)
            else:
                symbol = QgsSymbol.defaultSymbol(saved_layer.geometryType())
                saved_layer.setRenderer(QgsSingleSymbolRenderer(symbol))

            QgsProject.instance().addMapLayer(saved_layer)

            if self.temp_layer:
                QgsProject.instance().removeMapLayer(self.temp_layer.id())
                self.temp_layer = None

            if self.canvas:
                for marker in self.sample_markers:
                    self.canvas.scene().removeItem(marker)
                self.sample_markers = []

            self.iface.actionPan().trigger()

            QMessageBox.information(self.dialog, "Success", "Samples have been saved successfully.")
            return True

        except Exception as e:
            QMessageBox.critical(self.dialog, "Error", f"Error saving samples: {str(e)}")
            return False

class ClusterSystematicSamplingMapTool(QgsMapTool):
    # Custom map tool to allow user to move the grid, add samples, and remove samples interactively

    def __init__(self, iface, sampler):
        self.iface = iface
        self.sampler = sampler
        super().__init__(self.iface.mapCanvas())
        self.dragging = False
        self.last_point = None
        self.edit_mode = False

    def canvasReleaseEvent(self, event):
        # Handles clicks to remove or add points (right-click removes, left-click adds)
        if self.edit_mode:
            if event.button() == Qt.RightButton:
                map_point = self.toMapCoordinates(event.pos())
                self.sampler.remove_sample(map_point)
            elif event.button() == Qt.LeftButton:
                map_point = self.toMapCoordinates(event.pos())
                self.sampler.add_sample(map_point)
        elif event.button() == Qt.LeftButton:
            self.dragging = False
            self.last_point = None

    def canvasPressEvent(self, event):
        # Initiates grid dragging when the user presses the left button
        if not self.edit_mode and event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_point = self.toMapCoordinates(event.pos())

    def canvasMoveEvent(self, event):
        # Continues grid movement by tracking mouse movement
        if self.dragging and self.last_point:
            current_point = self.toMapCoordinates(event.pos())
            dx = current_point.x() - self.last_point.x()
            dy = current_point.y() - self.last_point.y()
            self.sampler.move_grid(dx, dy)
            self.last_point = current_point

    def keyPressEvent(self, event):
        # Finalizes the grid position when the user presses Enter/Return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            try:
                self.sampler.filter_samples()

                QMessageBox.information(
                    self.sampler.dialog,
                    "Grid Positioned",
                    "The grid has been set. Left-click to add samples manually, right-click to remove them. "
                    "Press 'Save' to generate the final shapefile."
                )
                self.edit_mode = True

            except Exception as e:
                QMessageBox.critical(
                    self.sampler.dialog,
                    "Error",
                    f"Error finalizing grid position: {str(e)}"
                )

    def activate(self):
        # Sets the cursor when this tool is active
        self.canvas().setCursor(Qt.CrossCursor)

    def deactivate(self):
        # Called when the tool is deactivated (no additional logic needed here)
        pass
