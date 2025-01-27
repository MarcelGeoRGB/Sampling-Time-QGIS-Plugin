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
 *   along with Sampling Time Plugin. If not, see                          *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 ***************************************************************************/
"""

import os
import math
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

class StratifiedSystematicSampling:
    """
    This class manages stratified systematic sampling operations:
    - Initializes basic parameters and widgets
    - Generates, rotates, and moves a grid
    - Applies filters to samples inside/outside strata and exclusion zones
    - Saves results to a shapefile
    """
    def __init__(self, iface, dialog):
        # Store interface, dialog, and canvas
        self.iface = iface
        self.dialog = dialog
        self.canvas = iface.mapCanvas() if iface else None
        # Layer properties
        self.sampling_area = None
        self.exclusion_zones = []
        self.temp_layer = None
        # Sampling parameters
        self.sample_count = 0
        self.spacing_x = 0
        self.spacing_y = 0
        self.label_root = ""
        self.samples = []
        self.grid_tool = None
        self.rubber_band = None
        self.perimeter_buffer_sample_area = 0
        self.perimeter_buffer_exclusion_area = 0
        # Geometry and distance calculations
        self.distance_area = QgsDistanceArea()
        # Markers for quick visualization
        self.sample_markers = []
        # Additional options
        self.apply_zigzag = False
        self.allow_outside_sampling = False
        self.is_systematic_active = False

        # Disable relevant widgets at the start
        self.dialog.spinBoxanglestratifiedsystematically.setEnabled(False)
        self.dialog.pushButtonstratifiedsystematicstart.setEnabled(False)
        self.dialog.pushButtonstratifiedsystematicsave.setEnabled(False)
        self.dialog.doubleSpinBoxdistancestratifiedxsamples.setEnabled(False)
        self.dialog.doubleSpinBoxdistancestratifiedysamples.setEnabled(False)
        self.dialog.doubleSpinBoxdistancestratifiedperimeter.setEnabled(False)
        self.dialog.doubleSpinBoxdistancestratifiedexclusion.setEnabled(False)
        self.dialog.checkBoxstratifiedsampling_zigzagsystematic.setEnabled(False)
        self.dialog.checkBoxoutsidesampling_stratified.setEnabled(False)

        # Connect checkboxes to methods
        self.dialog.checkBoxoutsidesampling_stratified.stateChanged.connect(
            self.on_checkBoxoutsidesampling_stratified_stateChanged
        )

        self.dialog.checkBoxaddstratifiedsamplessystematically.stateChanged.connect(
            self.on_checkBoxaddstratifiedsamplessystematically_stateChanged
        )
        self.dialog.checkBoxaddstratifiedsamplesrandomly.stateChanged.connect(
            self.on_checkBoxaddstratifiedsamplesrandomly_stateChanged
        )
        # Trigger initial state
        self.on_checkBoxaddstratifiedsamplessystematically_stateChanged(
            self.dialog.checkBoxaddstratifiedsamplessystematically.checkState()
        )

        # Monitor layer removal events
        QgsProject.instance().layerWillBeRemoved.connect(self.on_layer_removed)

    def on_layer_removed(self, layer_id):
        # Clears temporary layer if removed from project
        if self.temp_layer is not None and layer_id == self.temp_layer.id():
            self.temp_layer = None

    def on_checkBoxaddstratifiedsamplesrandomly_stateChanged(self, state):
        # Ensures only one sampling method is enabled
        if state == Qt.Checked:
            if self.dialog.checkBoxaddstratifiedsamplessystematically.isChecked():
                self.dialog.checkBoxaddstratifiedsamplessystematically.setChecked(False)
                self.is_systematic_active = False

    def on_checkBoxaddstratifiedsamplessystematically_stateChanged(self, state):
        # Activates or deactivates systematic sampling widgets
        enable_widgets = (state == Qt.Checked)
        self.is_systematic_active = enable_widgets

        if enable_widgets:
            self.dialog.spinBoxanglestratifiedsystematically.setEnabled(True)
            self.dialog.pushButtonstratifiedsystematicstart.setEnabled(True)
            self.dialog.pushButtonstratifiedsystematicsave.setEnabled(True)
            self.dialog.doubleSpinBoxdistancestratifiedxsamples.setEnabled(True)
            self.dialog.doubleSpinBoxdistancestratifiedysamples.setEnabled(True)
            self.dialog.doubleSpinBoxdistancestratifiedperimeter.setEnabled(True)
            self.dialog.doubleSpinBoxdistancestratifiedexclusion.setEnabled(True)
            self.dialog.checkBoxstratifiedsampling_zigzagsystematic.setEnabled(True)
            self.dialog.checkBoxoutsidesampling_stratified.setEnabled(True)
            
            # Simple info message explaining the workflow
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
                "Workflow:\n"
                "1. Click 'Start' to generate the grid\n"
                "2. Position grid as desired and press 'Enter'\n"
                "3. Left click to add samples manually\n"
                "4. Right click to remove samples\n"
                "5. Click 'Save' to create the final shapefile"
            )
        else:
            # Disable everything if checkbox is unchecked
            self.dialog.spinBoxanglestratifiedsystematically.setEnabled(False)
            self.dialog.pushButtonstratifiedsystematicstart.setEnabled(False)
            self.dialog.pushButtonstratifiedsystematicsave.setEnabled(False)
            self.dialog.doubleSpinBoxdistancestratifiedxsamples.setEnabled(False)
            self.dialog.doubleSpinBoxdistancestratifiedysamples.setEnabled(False)
            self.dialog.doubleSpinBoxdistancestratifiedperimeter.setEnabled(False)
            self.dialog.doubleSpinBoxdistancestratifiedexclusion.setEnabled(False)
            self.dialog.checkBoxstratifiedsampling_zigzagsystematic.setEnabled(False)
            self.dialog.checkBoxoutsidesampling_stratified.setEnabled(False)
            
            # Reset sample collection
            self.samples = []
            if self.rubber_band:
                self.rubber_band.reset()
        
    def on_checkBoxoutsidesampling_stratified_stateChanged(self, state):
        # Toggles permission for samples outside sampling area
        self.allow_outside_sampling = (state == Qt.Checked)

    def rotate_point(self, point, angle_degrees, center):
        # Rotates a point around a center by a given angle
        math_angle = (90 - angle_degrees) % 180
        angle_rad = math.radians(math_angle)
        x_shifted = point.x() - center.x()
        y_shifted = point.y() - center.y()
        x_new = x_shifted * math.cos(angle_rad) - y_shifted * math.sin(angle_rad) + center.x()
        y_new = x_shifted * math.sin(angle_rad) + y_shifted * math.cos(angle_rad) + center.y()
        return QgsPointXY(x_new, y_new)

    def set_sampling_area(self, layer):
        # Defines the main sampling area
        self.sampling_area = layer

    def set_exclusion_zones(self, exclusion_layers):
        # Defines layers to exclude from valid samples
        self.exclusion_zones = exclusion_layers

    def set_parameters(self, spacing_x, spacing_y, label_root, perimeter_buffer_sample_area, perimeter_buffer_exclusion_area):
        # Set spacing, labeling, and buffer distances
        self.spacing_x = spacing_x
        self.spacing_y = spacing_y
        self.label_root = label_root
        self.perimeter_buffer_sample_area = perimeter_buffer_sample_area
        self.perimeter_buffer_exclusion_area = perimeter_buffer_exclusion_area
        # Zigzag and outside sampling options
        self.apply_zigzag = self.dialog.checkBoxstratifiedsampling_zigzagsystematic.isChecked()
        self.allow_outside_sampling = self.dialog.checkBoxoutsidesampling_stratified.isChecked()

    def get_combined_geometry(self):
        # Merges all features in the sampling layer
        features = self.sampling_area.getFeatures()
        geoms = [f.geometry() for f in features]
        if not geoms:
            return None
        combined_geom = QgsGeometry.unaryUnion(geoms)
        return combined_geom

    def generate_initial_grid(self):
        # Creates an initial systematic grid based on spacing and area extent
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
        # Collect vertices from geometry for radius calculation
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

        # Find the farthest distance from centroid
        for vertex in vertices:
            distance = centroid.distance(vertex)
            if distance > max_distance:
                max_distance = distance

        radius = max_distance
        # Build a circle around centroid to define grid extent
        circular_geom = QgsGeometry.fromPointXY(centroid).buffer(radius, 50)

        grid_extent = circular_geom.boundingBox()
        x_min = grid_extent.xMinimum()
        x_max = grid_extent.xMaximum()
        y_min = grid_extent.yMinimum()
        y_max = grid_extent.yMaximum()

        self.samples = []
        row_count = 0

        # Fill points in rows using user spacing
        y = y_max
        while y >= y_min:
            x = x_min

            offset = 0
            # Zigzag offset for every other row
            if self.apply_zigzag and row_count % 2 != 0:
                offset = self.spacing_x / 2

            while x <= x_max:
                point = QgsPointXY(x + offset, y)
                point_geom = QgsGeometry.fromPointXY(point)
                # Only add if inside circle
                if circular_geom.contains(point_geom):
                    self.samples.append(point)
                x += self.spacing_x
            y -= self.spacing_y
            row_count += 1

    def create_feature(self, id_num, point, strata_id):
        # Creates a feature for the memory layer with attributes
        feature = QgsFeature(self.temp_layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        feature.setAttributes([
            id_num,
            f"Stratum {strata_id}",
            f"{self.label_root}{id_num}",
            point.x(),
            point.y()
        ])
        return feature

    def update_rubber_band(self):
        # Updates on-screen representation of the grid in memory
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
        # Shifts the entire grid by dx, dy
        self.samples = [QgsPointXY(p.x() + dx, p.y() + dy) for p in self.samples]
        self.update_rubber_band()

    def update_sample_markers(self):
        # Creates or updates a temporary memory layer and markers for samples
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

        self.temp_layer = QgsVectorLayer("Point?crs=" + self.sampling_area.crs().authid(), "Temporary Stratified Systematic Samples", "memory")
        self.temp_layer.dataProvider().addAttributes([
            QgsField("ID", QVariant.Int),
            QgsField("Strata", QVariant.String),
            QgsField("Samples", QVariant.String),
            QgsField("X coordinates", QVariant.Double),
            QgsField("Y coordinates", QVariant.Double)
        ])
        self.temp_layer.updateFields()

        features = []
        current_id = 1
        # Assign features to strata if inside geometry or allowed outside
        for point in self.samples:
            point_geom = QgsGeometry.fromPointXY(point)
            point_added = False
            for feature in self.sampling_area.getFeatures():
                if feature.geometry().contains(point_geom):
                    strata_id = feature.id() + 1
                    feat = self.create_feature(current_id, point, strata_id)
                    features.append(feat)
                    current_id += 1
                    point_added = True
                    break
            if not point_added and self.allow_outside_sampling:
                feat = self.create_feature(current_id, point, "outside")
                features.append(feat)
                current_id += 1

        self.temp_layer.dataProvider().addFeatures(features)

        # Assign simple visualization style
        symbol = QgsSymbol.defaultSymbol(self.temp_layer.geometryType())
        symbol.setColor(QColor(0, 255, 255))
        symbol.setSize(2)
        renderer = QgsSingleSymbolRenderer(symbol)
        self.temp_layer.setRenderer(renderer)

        QgsProject.instance().addMapLayer(self.temp_layer)
        self.canvas.refresh()

    def filter_samples(self):
        # Removes samples that do not meet perimeter buffer and exclusion criteria
        valid_samples = []
        samples_per_strata = {}
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
                strata_geom = feature.geometry()
                strata_id = feature.id() + 1

                # Check if point is within stratum geometry
                if strata_geom.contains(point_geom):
                    # Check perimeter buffer
                    if self.perimeter_buffer_sample_area > 0:
                        buffered = strata_geom.buffer(-self.perimeter_buffer_sample_area, 5)
                        if not buffered.contains(point_geom):
                            continue

                    # Check exclusion zones
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
                        if strata_id not in samples_per_strata:
                            samples_per_strata[strata_id] = 0
                        samples_per_strata[strata_id] += 1
                        total_samples += 1

        progress.close()

        self.samples = valid_samples
        self.update_sample_markers()

        # Final report of how many samples per stratum
        message = "Samples generated per stratum:\n"
        message += "-" * 30 + "\n"
        for strata_id, count in sorted(samples_per_strata.items()):
            message += f"Stratum {strata_id}: {count} samples\n"
        message += "-" * 30 + "\n"
        message += f"Total samples: {total_samples}"

        QMessageBox.information(self.dialog, "Sampling Complete", message)

    def remove_sample(self, point):
        # Removes a sample closest to the clicked point
        if not self.samples:
            return
        closest_point = min(self.samples, key=lambda p: p.distance(point))
        if closest_point.distance(point) < self.spacing_x / 2:
            self.samples.remove(closest_point)
            self.update_sample_markers()

    def add_sample(self, point):
        # Adds a sample if valid with given constraints
        if self.temp_layer is None:
            self.update_sample_markers()

        if self.is_point_valid(point):
            self.samples.append(point)
            self.update_sample_markers()

    def is_point_valid(self, point):
        # Checks if a point is inside strata and outside exclusion zones
        point_geom = QgsGeometry.fromPointXY(point)
        valid_strata = False

        for feature in self.sampling_area.getFeatures():
            strata_geom = feature.geometry()
            if strata_geom.contains(point_geom):
                valid_strata = True
                if self.perimeter_buffer_sample_area > 0:
                    buffered = strata_geom.buffer(-self.perimeter_buffer_sample_area, 5)
                    if not buffered.contains(point_geom):
                        QMessageBox.warning(
                            self.dialog,
                            "Invalid Location",
                            f"Point too close to stratum perimeter (min: {self.perimeter_buffer_sample_area}m)"
                        )
                        return False
                break

        if not valid_strata and not self.allow_outside_sampling:
            QMessageBox.warning(self.dialog, "Invalid Location", "Point must be inside a stratum")
            return False

        # Check exclusion zones
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
        # Initiates systematic sampling: builds grid and allows repositioning
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

        try:
            self.dialog.showMinimized()

            # Create a temporary layer
            self.temp_layer = QgsVectorLayer(
                "Point?crs=" + self.sampling_area.crs().authid(),
                "Temporary Stratified Systematic Samples",
                "memory"
            )
            self.temp_layer.dataProvider().addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Strata", QVariant.String),
                QgsField("Samples", QVariant.String),
                QgsField("X coordinates", QVariant.Double),
                QgsField("Y coordinates", QVariant.Double)
            ])
            self.temp_layer.updateFields()

            # Create the initial grid
            self.generate_initial_grid()

            angle = self.dialog.spinBoxanglestratifiedsystematically.value()

            combined_geom = self.get_combined_geometry()
            if not combined_geom:
                QMessageBox.critical(self.dialog, "Error", "Failed to calculate combined geometry of the sampling area.")
                return

            centroid_geom = combined_geom.centroid()
            if centroid_geom is None or centroid_geom.isEmpty():
                QMessageBox.critical(self.dialog, "Error", "Failed to calculate centroid of the sampling area.")
                return
            centroid = centroid_geom.asPoint()

            # Rotate entire grid by chosen angle
            self.samples = [self.rotate_point(p, angle, centroid) for p in self.samples]

            self.update_rubber_band()

            # Use a custom tool for moving the grid
            self.grid_tool = GridMoveTool(self.iface, self)
            self.canvas.setMapTool(self.grid_tool)

            QMessageBox.information(
                self.dialog,
                "Move Grid",
                "Click and drag to move the grid. Press 'Enter' to confirm the position."
            )

        except Exception as e:
            QMessageBox.critical(self.dialog, "Error", f"Error starting sampling: {str(e)}")

    def save_samples(self, output_dir, filename):
        # Saves final samples to a shapefile
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
                QgsField("Strata", QVariant.String),
                QgsField("Samples", QVariant.String),
                QgsField("X coordinates", QVariant.Double),
                QgsField("Y coordinates", QVariant.Double)
            ])
            output_layer.updateFields()

            features = []
            current_id = 1
            # Assign points to appropriate strata or outside
            for point in self.samples:
                point_geom = QgsGeometry.fromPointXY(point)
                point_added = False
                for feature in self.sampling_area.getFeatures():
                    if feature.geometry().contains(point_geom):
                        strata_id = feature.id() + 1
                        feat = self.create_feature(current_id, point, strata_id)
                        features.append(feat)
                        current_id += 1
                        point_added = True
                        break
                if not point_added and self.allow_outside_sampling:
                    feat = self.create_feature(current_id, point, "outside")
                    features.append(feat)
                    current_id += 1

            output_layer.dataProvider().addFeatures(features)

            # Define output path and write shapefile
            output_path = os.path.join(output_dir, f"{filename}.shp")
            QgsVectorFileWriter.writeAsVectorFormat(
                output_layer,
                output_path,
                "UTF-8",
                self.sampling_area.crs(),
                "ESRI Shapefile"
            )

            # Load the saved layer into the project
            saved_layer = QgsVectorLayer(output_path, filename, "ogr")
            if not saved_layer.isValid():
                QMessageBox.critical(
                    self.dialog,
                    "Error",
                    "Failed to create the systematic sampling shapefile."
                )
                return False

            # Apply chosen symbol if defined
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

            # Cleanup temporary items
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


class GridMoveTool(QgsMapTool):
    """
    This custom map tool allows the user to:
    - Drag and move the entire grid
    - Press 'Enter' to confirm final position
    - Left-click to add a sample
    - Right-click to remove a sample
    """
    def __init__(self, iface, sampler):
        self.iface = iface
        self.sampler = sampler
        super().__init__(self.iface.mapCanvas())
        self.dragging = False
        self.last_point = None
        self.edit_mode = False

    def canvasReleaseEvent(self, event):
        # Handles mouse release events for adding/removing samples
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
        # Initiates grid dragging on left click
        if not self.edit_mode and event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_point = self.toMapCoordinates(event.pos())

    def canvasMoveEvent(self, event):
        # Moves the grid while dragging the mouse
        if self.dragging and self.last_point:
            current_point = self.toMapCoordinates(event.pos())
            dx = current_point.x() - self.last_point.x()
            dy = current_point.y() - self.last_point.y()
            self.sampler.move_grid(dx, dy)
            self.last_point = current_point

    def keyPressEvent(self, event):
        # Finalizes grid position on Enter/Return, enabling edit mode
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            try:
                self.sampler.filter_samples()

                QMessageBox.information(
                    self.sampler.dialog,
                    "Grid Positioned",
                    "Grid set. Left-click to add samples, right-click to remove them. "
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
        # Sets the cursor to a crosshair
        self.canvas().setCursor(Qt.CrossCursor)

    def deactivate(self):
        # No special deactivation behavior
        pass
