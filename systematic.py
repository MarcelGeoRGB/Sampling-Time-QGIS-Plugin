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

class SystematicSampling:
    # This class handles the systematic sampling process, including grid generation, rotation, and filtering.
    def __init__(self, iface, dialog):
        # Initialize the class with references to QGIS interface and the plugin dialog.
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

        # Connect state change signals for checkboxes to specific methods.
        self.dialog.checkBoxoutsidesampling_systematic.stateChanged.connect(
            self.on_checkBoxoutsidesampling_systematic_stateChanged
        )

        self.dialog.checkBoxaddsamplessystematically.stateChanged.connect(
            self.on_checkBoxaddsamplessystematically_stateChanged
        )
        self.on_checkBoxaddsamplessystematically_stateChanged(
            self.dialog.checkBoxaddsamplessystematically.checkState()
        )

        # Connect removal of layer in QGIS to a custom method.
        QgsProject.instance().layerWillBeRemoved.connect(self.on_layer_removed)

    def on_checkBoxaddsamplessystematically_stateChanged(self, state):
        # Enable or disable widgets based on the checkbox state for systematic sampling.
        enable_widgets = (state == Qt.Checked)
        self.dialog.spinBoxanglesystematically.setEnabled(enable_widgets)
        self.dialog.pushButtonregularsystematicstart.setEnabled(enable_widgets)
        self.dialog.pushButtonregularsystematicsave.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistancexsamples.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistanceysamples.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistanceperimetersamplearea.setEnabled(enable_widgets)
        self.dialog.doubleSpinBoxdistanceperimeterexclusionarea.setEnabled(enable_widgets)
        self.dialog.checkBoxoutsidesampling_zigzagsystematic.setEnabled(enable_widgets)
        self.dialog.checkBoxoutsidesampling_systematic.setEnabled(enable_widgets)

        # If widgets are enabled, display instructions to guide the user.
        if enable_widgets:
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

    def on_checkBoxoutsidesampling_systematic_stateChanged(self, state):
        # This method sets whether samples are allowed to be outside the main sampling area.
        self.allow_outside_sampling = (state == Qt.Checked)

    def on_layer_removed(self, layerId):
        # When a temporary layer is removed from the project, clear any rubber bands or markers.
        if self.temp_layer is not None and layerId == self.temp_layer.id():
            if self.rubber_band:
                self.canvas.scene().removeItem(self.rubber_band)
                self.rubber_band = None

            for marker in self.sample_markers:
                self.canvas.scene().removeItem(marker)
            self.sample_markers.clear()

            self.temp_layer = None

            self.canvas.refresh()

    def rotate_point(self, point, angle_degrees, center):
        # Rotate a given point around a center by the specified angle (in degrees).
        math_angle = (90 - angle_degrees) % 180
        angle_rad = math.radians(math_angle)
        x_shifted = point.x() - center.x()
        y_shifted = point.y() - center.y()
        x_new = x_shifted * math.cos(angle_rad) - y_shifted * math.sin(angle_rad) + center.x()
        y_new = x_shifted * math.sin(angle_rad) + y_shifted * math.cos(angle_rad) + center.y()
        return QgsPointXY(x_new, y_new)

    def set_sampling_area(self, layer):
        # Set the main sampling area layer.
        self.sampling_area = layer

    def set_exclusion_zones(self, exclusion_layers):
        # Set the exclusion zone layers.
        self.exclusion_zones = exclusion_layers

    def set_parameters(self, spacing_x, spacing_y, label_root, perimeter_buffer_sample_area, perimeter_buffer_exclusion_area):
        # Define parameters for spacing, labeling, and buffering.
        self.spacing_x = spacing_x
        self.spacing_y = spacing_y
        self.label_root = label_root
        self.perimeter_buffer_sample_area = perimeter_buffer_sample_area
        self.perimeter_buffer_exclusion_area = perimeter_buffer_exclusion_area
        self.apply_zigzag = self.dialog.checkBoxoutsidesampling_zigzagsystematic.isChecked()
        self.allow_outside_sampling = self.dialog.checkBoxoutsidesampling_systematic.isChecked()

    def start_sampling(self):
        # Generate the systematic grid when the user starts the process.
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

            # Create a temporary in-memory point layer to hold samples before final save.
            self.temp_layer = QgsVectorLayer("Point?crs=" + self.sampling_area.crs().authid(), "Temporary Systematic Samples", "memory")
            self.temp_layer.dataProvider().addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Samples", QVariant.String),
                QgsField("X coordinates", QVariant.Double),
                QgsField("Y coordinates", QVariant.Double)
            ])
            self.temp_layer.updateFields()

            progress.setValue(40)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            # Generate the grid of points.
            self.generate_initial_grid()

            progress.setValue(60)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            # Rotate the grid by the angle specified in the spinBox.
            angle = self.dialog.spinBoxanglesystematically.value()

            combined_geom = self.get_combined_geometry()
            if not combined_geom:
                QMessageBox.critical(self.dialog, "Error", "Failed to calculate combined geometry of the sampling area.")
                return

            progress.setValue(80)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            # Find the centroid to use as the rotation center.
            centroid_geom = combined_geom.centroid()
            if centroid_geom is None or centroid_geom.isEmpty():
                QMessageBox.critical(self.dialog, "Error", "Failed to calculate centroid of the sampling area.")
                return
            centroid = centroid_geom.asPoint()

            self.samples = [self.rotate_point(p, angle, centroid) for p in self.samples]

            # Update the rubber band to show the initial sampling grid.
            self.update_rubber_band()

            progress.setValue(100)
            QApplication.processEvents()

            # Enable the custom map tool to move the grid.
            self.grid_tool = GridMoveTool(self.iface, self)
            self.canvas.setMapTool(self.grid_tool)

            progress.close()
            QMessageBox.information(self.dialog, "Move Grid", "Click and drag to move the grid. Press 'Enter' to confirm the position.")

        except Exception as e:
            progress.close()
            QMessageBox.critical(self.dialog, "Error", f"Error starting sampling: {str(e)}")

    def get_combined_geometry(self):
        # Combine all features in the sampling area into a single geometry.
        features = self.sampling_area.getFeatures()
        geoms = [f.geometry() for f in features]
        if not geoms:
            return None
        combined_geom = QgsGeometry.unaryUnion(geoms)
        return combined_geom

    def generate_initial_grid(self):
        # Create an initial grid of points covering the sampling area with some buffer.
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

        # Determine maximum distance from the centroid to buffer the geometry.
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

        # Create a circular geometry around the centroid to define the grid extent.
        circular_geom = QgsGeometry.fromPointXY(centroid).buffer(radius, 50)

        grid_extent = circular_geom.boundingBox()
        x_min = grid_extent.xMinimum()
        x_max = grid_extent.xMaximum()
        y_min = grid_extent.yMinimum()
        y_max = grid_extent.yMaximum()

        self.samples = []
        row_count = 0

        # Populate the grid with points spaced by spacing_x and spacing_y.
        y = y_max
        while y >= y_min:
            x = x_min

            offset = 0
            # If zigzag is enabled, offset every other row by half the X spacing.
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

    def create_feature(self, id_num, point):
        # Create a new feature for a single sample point with specified attributes.
        feature = QgsFeature(self.temp_layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        feature.setAttributes([
            id_num,
            f"{self.label_root}{id_num}",
            point.x(),
            point.y()
        ])
        return feature

    def update_rubber_band(self):
        # Update the rubber band on the canvas to visualize the current grid.
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
        # Move all points in the grid by dx, dy.
        self.samples = [QgsPointXY(p.x() + dx, p.y() + dy) for p in self.samples]
        self.update_rubber_band()

    def update_sample_markers(self):
        # Refresh the markers on the canvas to represent individual sample points.
        if not self.canvas:
            return

        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
            self.rubber_band = None

        for marker in self.sample_markers:
            self.canvas.scene().removeItem(marker)
        self.sample_markers = []

        for point in self.samples:
            marker = QgsVertexMarker(self.canvas)
            marker.setCenter(point)
            marker.setColor(QColor(0, 255, 255))
            marker.setFillColor(QColor(0, 255, 255, 255))
            marker.setIconSize(5)
            marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
            marker.setPenWidth(1)
            self.sample_markers.append(marker)

        if self.temp_layer:
            QgsProject.instance().removeMapLayer(self.temp_layer)
        
        # Create a new temporary layer and add features corresponding to current sample points.
        self.temp_layer = QgsVectorLayer("Point?crs=" + self.sampling_area.crs().authid(), "Temporary Systematic Samples", "memory")
        self.temp_layer.dataProvider().addAttributes([
            QgsField("ID", QVariant.Int),
            QgsField("Samples", QVariant.String),
            QgsField("X coordinates", QVariant.Double),
            QgsField("Y coordinates", QVariant.Double)
        ])
        self.temp_layer.updateFields()

        features = []
        for i, point in enumerate(self.samples, 1):
            feat = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPointXY(point))
            feat.setAttributes([i, f"{self.label_root}{i}", point.x(), point.y()])
            features.append(feat)
        
        self.temp_layer.dataProvider().addFeatures(features)
        
        symbol = QgsSymbol.defaultSymbol(self.temp_layer.geometryType())
        symbol.setColor(QColor(0, 255, 255))
        symbol.setSize(2)
        renderer = QgsSingleSymbolRenderer(symbol)
        self.temp_layer.setRenderer(renderer)
        
        QgsProject.instance().addMapLayer(self.temp_layer)
        self.canvas.refresh()

    def filter_samples(self):
        # Filter out samples that are too close to the perimeter or within exclusion zones.
        combined_geom = self.get_combined_geometry()
        if not combined_geom:
            QMessageBox.critical(self.dialog, "Error", "Combined geometry could not be calculated.")
            return

        area_buffered = combined_geom.buffer(-self.perimeter_buffer_sample_area, 5)

        exclusion_geometries = []
        for zone in self.exclusion_zones:
            for feature in zone.getFeatures():
                geom = feature.geometry()
                if self.perimeter_buffer_exclusion_area > 0:
                    geom = geom.buffer(self.perimeter_buffer_exclusion_area, 5)
                exclusion_geometries.append(geom)

        valid_samples = []
        for point in self.samples:
            point_geom = QgsGeometry.fromPointXY(point)
            # Check if the point is inside the buffered sampling area.
            if area_buffered.contains(point_geom):
                # Check if the point is not inside any exclusion geometry.
                if all(not exclusion_geom.contains(point_geom) for exclusion_geom in exclusion_geometries):
                    valid_samples.append(point)

        self.samples = valid_samples
        self.update_sample_markers()

    def remove_sample(self, point):
        # Remove the sample closest to the point, if within half of the X spacing distance.
        if not self.samples:
            return
        closest_point = min(self.samples, key=lambda p: p.distance(point))
        if closest_point.distance(point) < self.spacing_x / 2:
            self.samples.remove(closest_point)
            self.update_sample_markers()

    def add_sample(self, point):
        # Add a sample if it passes validation checks (exclusion zones, perimeter buffers, etc.).
        if self.is_point_valid(point):
            self.samples.append(point)
            self.update_sample_markers()

    def is_point_valid(self, point):
        # Validate if the sample is within allowed area and not in exclusion zones.
        point_geom = QgsGeometry.fromPointXY(point)
        combined_geom = self.get_combined_geometry()
        if not combined_geom:
            QMessageBox.critical(self.dialog, "Error", "Combined geometry could not be calculated.")
            return False

        if not combined_geom.contains(point_geom):
            # If outside sampling area, check if outside sampling is allowed.
            if not self.allow_outside_sampling:
                QMessageBox.warning(self.dialog, "Invalid Sample Location", "The sample point is outside the sampling area.")
                return False
        elif self.perimeter_buffer_sample_area > 0:
            # Check buffer distance from the perimeter.
            area_buffered = combined_geom.buffer(-self.perimeter_buffer_sample_area, 5)
            if not area_buffered.contains(point_geom):
                QMessageBox.warning(
                    self.dialog, 
                    "Too Close to Boundary", 
                    f"The sample is too close to the perimeter. Minimum distance is {self.perimeter_buffer_sample_area} meters."
                )
                return False

        for zone in self.exclusion_zones:
            for feature in zone.getFeatures():
                exclusion_geom = feature.geometry()
                if exclusion_geom.contains(point_geom):
                    QMessageBox.warning(self.dialog, "Invalid Location", "The sample point is within an exclusion zone.")
                    return False
                if self.perimeter_buffer_exclusion_area > 0:
                    exclusion_buffered = exclusion_geom.buffer(self.perimeter_buffer_exclusion_area, 5)
                    if exclusion_buffered.contains(point_geom):
                        QMessageBox.warning(
                            self.dialog, 
                            "Too Close to Exclusion Zone", 
                            f"The sample is too close to the exclusion zone. Minimum distance is {self.perimeter_buffer_exclusion_area} meters."
                        )
                        return False

        return True

    def save_samples(self, output_dir, filename):
        # Export the current samples to a shapefile.
        try:
            if not self.samples:
                QMessageBox.warning(self.dialog, "Error", "No samples to save.")
                return False

            output_layer = QgsVectorLayer("Point?crs=" + self.sampling_area.crs().authid(), filename, "memory")
            output_layer.dataProvider().addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Samples", QVariant.String),
                QgsField("X coordinates", QVariant.Double),
                QgsField("Y coordinates", QVariant.Double)
            ])
            output_layer.updateFields()

            features = []
            for i, point in enumerate(self.samples, 1):
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPointXY(point))
                feat.setAttributes([i, f"{self.label_root}{i}", point.x(), point.y()])
                features.append(feat)
            output_layer.dataProvider().addFeatures(features)

            output_path = os.path.join(output_dir, f"{filename}.shp")
            QgsVectorFileWriter.writeAsVectorFormat(
                output_layer, output_path, "UTF-8", self.sampling_area.crs(), "ESRI Shapefile"
            )

            saved_layer = QgsVectorLayer(output_path, filename, "ogr")
            if not saved_layer.isValid():
                QMessageBox.critical(self.dialog, "Error", "Failed to create the systematic sampling shapefile.")
                return False

            # Optionally apply an SVG symbol if one is selected in the dialog.
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

    def renumber_samples(self):
        # Renumber features in the temporary layer to maintain sequential IDs and labels.
        for i, feature in enumerate(self.temp_layer.getFeatures(), 1):
            self.temp_layer.dataProvider().changeAttributeValue(feature.id(), 
                self.temp_layer.fields().indexOf('ID'), i)
            self.temp_layer.dataProvider().changeAttributeValue(feature.id(), 
                self.temp_layer.fields().indexOf('Samples'), f"{self.label_root}{i}")


class GridMoveTool(QgsMapTool):
    # Custom map tool allowing the user to drag the grid or add/remove samples before finalizing.
    def __init__(self, iface, sampler):
        self.iface = iface
        self.sampler = sampler
        super().__init__(self.iface.mapCanvas())
        self.dragging = False
        self.last_point = None
        self.edit_mode = False

    def canvasReleaseEvent(self, event):
        # Handle mouse release events to add or remove samples in edit mode.
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
        # Initiate drag when the user clicks on the map (only if not in edit mode).
        if not self.edit_mode and event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_point = self.toMapCoordinates(event.pos())

    def canvasMoveEvent(self, event):
        # While dragging, move the grid on the canvas.
        if self.dragging and self.last_point:
            current_point = self.toMapCoordinates(event.pos())
            dx = current_point.x() - self.last_point.x()
            dy = current_point.y() - self.last_point.y()
            self.sampler.move_grid(dx, dy)
            self.last_point = current_point

    def keyPressEvent(self, event):
        # On Enter/Return, finalize grid position and filter samples.
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            progress = QProgressDialog("Finalizing grid position...", "Cancel", 0, 100, self.sampler.dialog)
            progress.setWindowTitle("Progress")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)

            try:
                progress.setValue(30)
                QApplication.processEvents()

                if progress.wasCanceled():
                    return

                progress.setValue(60)
                QApplication.processEvents()

                # Filter out invalid samples (too close to boundary or inside exclusions).
                self.sampler.filter_samples()

                progress.setValue(100)
                QApplication.processEvents()
                progress.close()

                QMessageBox.information(
                    self.sampler.dialog, 
                    "Grid Positioned", 
                    "Grid set. Left-click to add samples, right-click to remove them. Press 'Save' to generate the final shapefile."
                )
                self.edit_mode = True

            except Exception as e:
                progress.close()
                QMessageBox.critical(self.sampler.dialog, "Error", f"Error finalizing grid position: {str(e)}")

    def activate(self):
        # Set the cursor to a cross when the tool is activated.
        self.canvas().setCursor(Qt.CrossCursor)

    def deactivate(self):
        pass
